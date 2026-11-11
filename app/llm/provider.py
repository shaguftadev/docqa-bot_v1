from typing import Protocol

from app.rag.qdrant_store import SearchHit
from app.schemas.answers import AnswerDraft


class AnswerProvider(Protocol):
    def draft(self, question: str, evidence: list[SearchHit]) -> AnswerDraft: ...


class AnswerProviderError(RuntimeError):
    """Raised when the configured LLM cannot provide a valid response."""


class InvalidAnswerOutput(AnswerProviderError):
    """The provider returned a response that failed local schema validation."""
