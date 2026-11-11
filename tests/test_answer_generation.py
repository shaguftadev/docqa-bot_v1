from uuid import uuid4

import httpx

from app.llm.provider import AnswerProvider, AnswerProviderError, InvalidAnswerOutput
from app.llm.gemini_provider import GeminiAnswerProvider
from app.rag.qdrant_store import SearchHit
from app.schemas.answers import AnswerDraft
from app.services.answer_generation import ABSTENTION, AnswerGenerationService


def hit(chunk_id: str = "doc:0") -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        document_id=uuid4(),
        filename="policy.md",
        text="Damaged items must be reported within 7 days.",
        score=0.8,
        page_number=None,
        section="Damaged items",
    )


class FakeProvider(AnswerProvider):
    def __init__(self, draft: AnswerDraft) -> None:
        self.result = draft
        self.calls = 0

    def draft(self, question: str, evidence: list[SearchHit]) -> AnswerDraft:
        self.calls += 1
        return self.result


def test_grounded_answer_returns_only_validated_citations() -> None:
    evidence = [hit()]
    provider = FakeProvider(AnswerDraft(
        sufficient_evidence=True,
        answer="Report damage within 7 days.",
        citation_chunk_ids=["doc:0"],
    ))

    result = AnswerGenerationService(provider).answer("When report damage?", evidence)

    assert result.status == "answered"
    assert result.answer == "Report damage within 7 days."
    assert result.citations[0].chunk_id == "doc:0"


def test_empty_evidence_abstains_without_calling_provider() -> None:
    provider = FakeProvider(AnswerDraft(
        sufficient_evidence=True, answer="invented", citation_chunk_ids=["fake"]
    ))

    result = AnswerGenerationService(provider).answer("Question?", [])

    assert result.answer == ABSTENTION
    assert result.status == "insufficient_evidence"
    assert result.citations == []
    assert provider.calls == 0


def test_unknown_or_missing_citation_abstains() -> None:
    evidence = [hit()]
    for citation_ids in (["foreign:0"], []):
        provider = FakeProvider(AnswerDraft(
            sufficient_evidence=True, answer="unsupported", citation_chunk_ids=list(citation_ids)
        ))
        result = AnswerGenerationService(provider).answer("Question?", evidence)
        assert result.status == "insufficient_evidence"
        assert result.answer == ABSTENTION
        assert result.citations == []


def test_provider_insufficient_evidence_abstains() -> None:
    provider = FakeProvider(AnswerDraft(
        sufficient_evidence=False, answer="", citation_chunk_ids=[]
    ))
    result = AnswerGenerationService(provider).answer("Question?", [hit()])
    assert result.status == "insufficient_evidence"
    assert result.citations == []


def test_invalid_provider_output_abstains_but_provider_outage_propagates() -> None:
    class BrokenProvider:
        def __init__(self, error: Exception) -> None:
            self.error = error

        def draft(self, question, evidence):
            raise self.error

    abstained = AnswerGenerationService(BrokenProvider(InvalidAnswerOutput("bad JSON"))).answer("Question?", [hit()])
    assert abstained.status == "insufficient_evidence"

    try:
        AnswerGenerationService(BrokenProvider(AnswerProviderError("offline"))).answer("Question?", [hit()])
    except AnswerProviderError:
        pass
    else:
        raise AssertionError("Provider outages must propagate so the API can return 503")


def test_gemini_adapter_sends_structured_request_and_parses_response() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["api_key"] = request.headers.get("x-goog-api-key")
        seen["payload"] = request.read().decode()
        return httpx.Response(200, json={
            "candidates": [{
                "content": {"parts": [{"text": '{"sufficient_evidence":true,"answer":"Report within 7 days.","citation_chunk_ids":["doc:0"]}'}]}
            }]
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GeminiAnswerProvider("test-api-key", "gemini-3.8-flash", client=client)
    result = provider.draft("When report damage?", [hit()])

    assert "models/gemini-3.8-flash:generateContent" in seen["url"]
    assert seen["api_key"] == "test-api-key"
    assert '"responseMimeType":"application/json"' in seen["payload"]
    assert result.answer == "Report within 7 days."
    assert result.citation_chunk_ids == ["doc:0"]
