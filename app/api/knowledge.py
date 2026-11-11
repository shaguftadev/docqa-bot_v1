from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.embeddings.provider import Embedder, EmbeddingProviderError, get_embedder
from app.rag.qdrant_store import QdrantVectorStore, VectorStoreError, get_vector_store
from app.schemas.documents import SearchHitResponse, SearchRequest, SearchResponse
from app.schemas.answers import AnswerRequest, AnswerResponse
from app.llm.provider import AnswerProviderError
from app.llm.gemini_provider import get_answer_provider
from app.services.answer_generation import AnswerGenerationService
from app.services.knowledge_search import KnowledgeSearchService

router = APIRouter(prefix="/knowledge", tags=["knowledge search"])


@router.post("/search", response_model=SearchResponse)
def search_knowledge(
    request: SearchRequest,
    db: Annotated[Session, Depends(get_db)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    vector_store: Annotated[QdrantVectorStore, Depends(get_vector_store)],
) -> SearchResponse:
    try:
        hits = KnowledgeSearchService(db, embedder, vector_store).search(
            tenant_id=request.tenant_id,
            query=request.query,
            limit=request.limit,
            document_ids=request.document_ids,
        )
    except VectorStoreError as exc:
        raise HTTPException(status_code=503, detail="Knowledge search is temporarily unavailable") from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=503, detail="The embedding model is temporarily unavailable") from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Document metadata is temporarily unavailable") from exc
    return SearchResponse(
        query=request.query,
        hits=[SearchHitResponse.model_validate(hit) for hit in hits],
    )


@router.post("/answer", response_model=AnswerResponse)
def answer_knowledge(
    request: AnswerRequest,
    db: Annotated[Session, Depends(get_db)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    vector_store: Annotated[QdrantVectorStore, Depends(get_vector_store)],
) -> AnswerResponse:
    try:
        evidence = KnowledgeSearchService(db, embedder, vector_store).search(
            tenant_id=request.tenant_id,
            query=request.question,
            limit=request.limit,
        )
    except VectorStoreError as exc:
        raise HTTPException(status_code=503, detail="Knowledge search is temporarily unavailable") from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=503, detail="The embedding model is temporarily unavailable") from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Document metadata is temporarily unavailable") from exc
    if not evidence:
        return AnswerGenerationService(_NoCallAnswerProvider()).answer(request.question, evidence)
    try:
        provider = get_answer_provider()
    except AnswerProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        return AnswerGenerationService(provider).answer(request.question, evidence)
    except AnswerProviderError as exc:
        raise HTTPException(status_code=503, detail="The answer provider is temporarily unavailable") from exc


class _NoCallAnswerProvider:
    """No evidence path must abstain without initializing or calling an LLM."""

    def draft(self, question, evidence):
        raise AssertionError("Provider should not be called when evidence is empty")
