from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.workflow import build_support_graph, initial_state
from app.db.session import get_db
from app.embeddings.provider import Embedder, EmbeddingProviderError, get_embedder
from app.llm.gemini_provider import get_answer_provider
from app.llm.provider import AnswerProviderError
from app.rag.qdrant_store import QdrantVectorStore, VectorStoreError, get_vector_store
from app.schemas.agent import AgentRequest, AgentResponse
from app.tools.knowledge import build_knowledge_search_tool
from app.tools.support_records import build_order_lookup_tool, build_ticket_lookup_tool

router = APIRouter(prefix="/agent", tags=["support agent"])


@router.post("/run", response_model=AgentResponse)
def run_support_agent(
    request: AgentRequest,
    db: Annotated[Session, Depends(get_db)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    vector_store: Annotated[QdrantVectorStore, Depends(get_vector_store)],
) -> AgentResponse:
    search_tool = build_knowledge_search_tool(db, embedder, vector_store)
    graph = build_support_graph(
        search_tool,
        get_answer_provider,
        build_order_lookup_tool(db),
        build_ticket_lookup_tool(db),
    )
    state = initial_state(
        tenant_id=request.tenant_id,
        message=request.message,
        order_id=request.order_id,
        ticket_id=request.ticket_id,
        limit=request.limit,
    )
    try:
        result = graph.invoke(state)
    except VectorStoreError as exc:
        raise HTTPException(status_code=503, detail="Knowledge search is temporarily unavailable") from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=503, detail="The embedding model is temporarily unavailable") from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Document metadata is temporarily unavailable") from exc
    except AnswerProviderError as exc:
        raise HTTPException(status_code=503, detail="The answer provider is temporarily unavailable") from exc
    return AgentResponse.model_validate(result)
