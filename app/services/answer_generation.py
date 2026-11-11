from app.llm.provider import AnswerProvider, InvalidAnswerOutput
from app.rag.qdrant_store import SearchHit
from app.schemas.answers import AnswerResponse
from app.schemas.documents import SearchHitResponse

ABSTENTION = "I don't have enough information in the available documents to answer that."


class AnswerGenerationService:
    def __init__(self, provider: AnswerProvider) -> None:
        self.provider = provider

    def answer(self, question: str, evidence: list[SearchHit]) -> AnswerResponse:
        if not evidence:
            return AnswerResponse(answer=ABSTENTION, status="insufficient_evidence", citations=[])
        try:
            draft = self.provider.draft(question, evidence)
        except InvalidAnswerOutput:
            return AnswerResponse(answer=ABSTENTION, status="insufficient_evidence", citations=[])
        allowed = {hit.chunk_id: hit for hit in evidence}
        if (
            not draft.sufficient_evidence
            or not draft.answer.strip()
            or not draft.citation_chunk_ids
            or len(set(draft.citation_chunk_ids)) != len(draft.citation_chunk_ids)
            or any(chunk_id not in allowed for chunk_id in draft.citation_chunk_ids)
        ):
            return AnswerResponse(answer=ABSTENTION, status="insufficient_evidence", citations=[])
        citations = [SearchHitResponse.model_validate(allowed[chunk_id]) for chunk_id in draft.citation_chunk_ids]
        return AnswerResponse(answer=draft.answer.strip(), status="answered", citations=citations)
