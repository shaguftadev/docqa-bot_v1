from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document
from app.embeddings.provider import Embedder
from app.rag.qdrant_store import QdrantVectorStore, SearchHit


class KnowledgeSearchService:
    def __init__(self, db: Session, embedder: Embedder, vector_store: QdrantVectorStore) -> None:
        self.db = db
        self.embedder = embedder
        self.vector_store = vector_store

    def search(
        self,
        *,
        tenant_id: str,
        query: str,
        limit: int,
        document_ids: list[UUID] | None = None,
    ) -> list[SearchHit]:
        ready_ids = list(
            self.db.scalars(
                select(Document.id).where(
                    Document.tenant_id == tenant_id,
                    Document.status == "ready",
                    Document.is_active.is_(True),
                )
            )
        )
        if document_ids is not None:
            allowed_ids = set(ready_ids)
            ready_ids = [document_id for document_id in document_ids if document_id in allowed_ids]
        if not ready_ids:
            return []
        query_vector = self.embedder.embed_query(query)
        return self.vector_store.search(
            query_vector=query_vector,
            tenant_id=tenant_id,
            ready_document_ids=ready_ids,
            limit=limit,
        )
