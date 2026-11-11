from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Document
from app.documents.chunking import chunk_pages
from app.documents.extractor import extract_document
from app.embeddings.provider import Embedder
from app.rag.qdrant_store import QdrantVectorStore, VectorStoreError

logger = logging.getLogger(__name__)


class IngestionFailed(RuntimeError):
    """Raised when embedding or vector storage fails for a valid upload."""


class DocumentIngestionService:
    def __init__(self, db: Session, embedder: Embedder, vector_store: QdrantVectorStore, settings: Settings) -> None:
        self.db = db
        self.embedder = embedder
        self.vector_store = vector_store
        self.settings = settings

    def ingest(self, *, tenant_id: str, filename: str, content_type: str, content: bytes) -> Document:
        pages = extract_document(filename, content)
        chunks = chunk_pages(pages, self.settings.chunk_size, self.settings.chunk_overlap)
        if not chunks:
            raise ValueError("No readable text chunks were produced")

        checksum = hashlib.sha256(content).hexdigest()
        active_query = select(Document).where(
            Document.tenant_id == tenant_id,
            Document.filename == filename,
            Document.is_active.is_(True),
        )
        current = self.db.scalar(active_query.with_for_update())
        if current is not None and current.status == "ready" and current.checksum == checksum:
            return current
        current_version = self.db.scalar(
            select(func.max(Document.version)).where(
                Document.tenant_id == tenant_id, Document.filename == filename
            )
        ) or 0
        document = Document(
            tenant_id=tenant_id,
            filename=filename,
            content_type=content_type,
            status="processing",
            version=current_version + 1,
            is_active=False,
            checksum=checksum,
            chunk_count=0,
            metadata_json={"page_count": len({p.page_number for p in pages if p.page_number is not None}) or None},
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        document_id = document.id

        previous_document_id: UUID | None = None
        try:
            vectors = self.embedder.embed_documents([chunk.text for chunk in chunks])
            self.vector_store.ensure_collection()
            self.vector_store.upsert_document(
                document_id=document_id,
                tenant_id=tenant_id,
                filename=filename,
                content_type=content_type,
                checksum=checksum,
                chunks=chunks,
                vectors=vectors,
            )
            # Only expose the new version after its vectors are durably stored.
            current = self.db.scalar(active_query.with_for_update())
            if current is not None and current.id != document_id:
                current.is_active = False
                previous_document_id = current.id
                document.version = max(document.version, current.version + 1)
            document.is_active = True
            document.status = "ready"
            document.chunk_count = len(chunks)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            try:
                self.vector_store.delete_document(document_id, tenant_id)
            except Exception:
                logger.exception("document vector cleanup failed", extra={"document_id": str(document_id)})
            self._mark_failed(document_id, exc)
            logger.exception("document indexing failed", extra={"document_id": str(document_id)})
            if isinstance(exc, VectorStoreError):
                raise IngestionFailed("The document could not be added to the knowledge index") from exc
            raise IngestionFailed("The document could not be processed") from exc

        if previous_document_id is not None:
            try:
                self.vector_store.delete_document(previous_document_id, tenant_id)
            except Exception:
                # The old version is inactive in PostgreSQL, so retrieval cannot return it.
                # A later cleanup pass can remove these unreachable points.
                logger.exception("inactive document vector cleanup failed", extra={"document_id": str(previous_document_id)})
        logger.info(
            "document indexed",
            extra={"document_id": str(document_id), "tenant_id": tenant_id, "chunk_count": len(chunks)},
        )
        return document

    def _mark_failed(self, document_id: UUID, error: Exception) -> None:
        try:
            failed = self.db.scalar(select(Document).where(Document.id == document_id))
            if failed is not None:
                failed.status = "failed"
                failed.is_active = False
                # Keep only a short, non-sensitive failure type in persistent metadata.
                failed.error_message = type(error).__name__[:80]
                self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("document status update failed", extra={"document_id": str(document_id)})
