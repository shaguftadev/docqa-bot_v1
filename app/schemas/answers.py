from pydantic import BaseModel, ConfigDict, Field

from app.schemas.documents import SearchHitResponse


class AnswerRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    tenant_id: str = Field(default="demo", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    question: str = Field(min_length=1, max_length=5000)
    limit: int = Field(default=5, ge=1, le=10)


class AnswerResponse(BaseModel):
    answer: str
    status: str
    citations: list[SearchHitResponse]


class AnswerDraft(BaseModel):
    """Untrusted structured output from the LLM before evidence validation."""

    sufficient_evidence: bool
    answer: str
    citation_chunk_ids: list[str]
