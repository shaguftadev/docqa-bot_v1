from pathlib import PurePath
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal, enforce_tenant_access, get_current_principal
from app.core.config import Settings, get_settings
from app.db.models import Document
from app.db.session import get_db
from app.documents.extractor import DocumentValidationError
from app.embeddings.provider import Embedder, get_embedder
from app.rag.qdrant_store import QdrantVectorStore, get_vector_store
from app.schemas.documents import DocumentResponse
from app.services.document_ingestion import DocumentIngestionService, IngestionFailed

router = APIRouter(prefix="/documents", tags=["documents"])
TenantForm = Annotated[
    str,
    Form(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


def get_ingestion_service(
    db: Annotated[Session, Depends(get_db)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    vector_store: Annotated[QdrantVectorStore, Depends(get_vector_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentIngestionService:
    return DocumentIngestionService(db, embedder, vector_store, settings)


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    principal: Annotated[Principal, Depends(get_current_principal)],
    file: Annotated[UploadFile, File(description="PDF, UTF-8 text, or Markdown")],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[DocumentIngestionService, Depends(get_ingestion_service)],
    tenant_id: TenantForm = "demo",
) -> DocumentResponse:
    enforce_tenant_access(principal, tenant_id)
    maximum_bytes = settings.upload_max_mb * 1024 * 1024
    content = file.file.read(maximum_bytes + 1)
    if len(content) > maximum_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds the {settings.upload_max_mb} MB upload limit")
    filename = PurePath((file.filename or "").replace("\\", "/")).name
    if not filename:
        raise HTTPException(status_code=400, detail="A filename is required")
    try:
        document = service.ingest(
            tenant_id=tenant_id,
            filename=filename,
            content_type=file.content_type or "application/octet-stream",
            content=content,
        )
    except DocumentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IngestionFailed as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return DocumentResponse.model_validate(document)


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    principal: Principal = Depends(get_current_principal),
    tenant_id: str = "demo",
    db: Session = Depends(get_db),
) -> list[DocumentResponse]:
    enforce_tenant_access(principal, tenant_id)
    if not tenant_id or len(tenant_id) > 100:
        raise HTTPException(status_code=400, detail="tenant_id must be between 1 and 100 characters")
    documents = db.scalars(
        select(Document).where(Document.tenant_id == tenant_id).order_by(Document.created_at.desc()).limit(100)
    )
    return [DocumentResponse.model_validate(document) for document in documents]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    principal: Annotated[Principal, Depends(get_current_principal)],
    document_id: UUID,
    tenant_id: str = "demo",
    db: Session = Depends(get_db),
) -> DocumentResponse:
    enforce_tenant_access(principal, tenant_id)
    document = db.scalar(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse.model_validate(document)
