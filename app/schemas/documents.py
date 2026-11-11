from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    filename: str
    content_type: str
    status: str
    is_active: bool
    version: int
    chunk_count: int
    created_at: datetime


class SearchRequest(BaseModel):
    tenant_id: str = Field(default="demo", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    query: str = Field(min_length=1, max_length=5000)
    limit: int = Field(default=5, ge=1, le=10)
    document_ids: list[UUID] | None = Field(default=None, max_length=100)

    model_config = ConfigDict(str_strip_whitespace=True)


class SearchHitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: str
    document_id: UUID
    filename: str
    text: str
    score: float
    page_number: int | None
    section: str | None


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHitResponse]
