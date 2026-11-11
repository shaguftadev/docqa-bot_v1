import json

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.embeddings.provider import Embedder
from app.rag.qdrant_store import QdrantVectorStore
from app.services.knowledge_search import KnowledgeSearchService


class KnowledgeSearchToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=5000)
    tenant_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    limit: int = Field(default=5, ge=1, le=10)


def build_knowledge_search_tool(
    db: Session,
    embedder: Embedder,
    vector_store: QdrantVectorStore,
) -> StructuredTool:
    """Build a request-scoped LangChain tool around the existing safe search service."""
    def search_knowledge_base(query: str, tenant_id: str, limit: int = 5) -> str:
        hits = KnowledgeSearchService(db, embedder, vector_store).search(
            tenant_id=tenant_id,
            query=query,
            limit=limit,
        )
        return json.dumps(
            [
                {
                    "chunk_id": hit.chunk_id,
                    "document_id": str(hit.document_id),
                    "filename": hit.filename,
                    "text": hit.text,
                    "score": hit.score,
                    "page_number": hit.page_number,
                    "section": hit.section,
                }
                for hit in hits
            ]
        )

    return StructuredTool.from_function(
        func=search_knowledge_base,
        name="search_knowledge_base",
        description="Search active support documents for evidence relevant to a customer question.",
        args_schema=KnowledgeSearchToolInput,
    )
