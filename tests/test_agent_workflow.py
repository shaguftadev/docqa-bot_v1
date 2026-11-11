import json
from uuid import uuid4

import pytest
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import ValidationError

from app.agent.classification import classify_message
from app.agent.workflow import build_support_graph, initial_state
from app.rag.qdrant_store import SearchHit
from app.schemas.answers import AnswerDraft
from app.tools.knowledge import KnowledgeSearchToolInput, build_knowledge_search_tool


class FakeAnswerProvider:
    def draft(self, question, evidence):
        return AnswerDraft(
            sufficient_evidence=True,
            answer="Report the damage within 7 days.",
            citation_chunk_ids=[evidence[0].chunk_id],
        )


def sample_hit() -> SearchHit:
    return SearchHit(
        chunk_id="policy:0",
        document_id=uuid4(),
        filename="returns.md",
        text="Report damaged items within 7 days.",
        score=0.82,
        page_number=None,
        section="Damaged items",
    )


def make_tool(payload: list[dict]) -> StructuredTool:
    def search_knowledge_base(query: str, tenant_id: str, limit: int = 5) -> str:
        return json.dumps(payload)

    return StructuredTool.from_function(
        func=search_knowledge_base,
        name="search_knowledge_base",
        description="Find support policy evidence.",
        args_schema=KnowledgeSearchToolInput,
    )


def make_record_tool(payload: dict) -> StructuredTool:
    def lookup(tenant_id: str, external_id: str) -> str:
        return json.dumps(payload)
    return StructuredTool.from_function(
        func=lookup, name="lookup_record", description="Synthetic test lookup.",
    )


def run_graph(message: str, *, tool: StructuredTool | None = None, order_id: str | None = None,
              ticket_id: str | None = None, order_tool=None, ticket_tool=None, provider=None):
    graph = build_support_graph(
        tool or make_tool([]),
        provider or (lambda: FakeAnswerProvider()),
        order_tool or make_record_tool({"found": False}),
        ticket_tool or make_record_tool({"found": False}),
        checkpointer=InMemorySaver(),
    )
    return graph.invoke(
        initial_state(tenant_id="demo", message=message, order_id=order_id, ticket_id=ticket_id, limit=3),
        {"configurable": {"thread_id": "workflow-test"}},
    )


@pytest.mark.parametrize(
    ("message", "intent", "priority", "route"),
    [
        ("Where is my order?", "order_status", "normal", "order_lookup"),
        ("Can you check ticket TK-1001?", "ticket_status", "normal", "ticket_lookup"),
        ("How do I return a damaged item?", "return_refund", "normal", "knowledge_lookup"),
        ("I want to make a complaint about fraud", "complaint", "urgent", "human_review"),
        ("The device is not working", "technical_issue", "normal", "manual_review"),
        ("What features does this product have?", "product_information", "normal", "knowledge_lookup"),
        ("Please send me a receipt", "billing", "normal", "manual_review"),
        ("Hello", "other", "low", "manual_review"),
    ],
)
def test_deterministic_classification(message, intent, priority, route):
    result = classify_message(message)
    assert (result.intent, result.priority, result.route) == (intent, priority, route)
    assert result.rationale


def test_knowledge_route_calls_tool_and_returns_grounded_citation():
    hit = sample_hit()
    tool = make_tool([{
        "chunk_id": hit.chunk_id,
        "document_id": str(hit.document_id),
        "filename": hit.filename,
        "text": hit.text,
        "score": hit.score,
        "page_number": hit.page_number,
        "section": hit.section,
    }])

    result = run_graph("How do I return a damaged item?", tool=tool)

    assert result["status"] == "answered"
    assert result["intent"] == "return_refund"
    assert result["route"] == "knowledge_lookup"
    assert result["citations"][0]["chunk_id"] == hit.chunk_id
    assert "Searched the knowledge base." in result["events"]


def test_empty_knowledge_search_abstains_without_creating_provider():
    def should_not_create_provider():
        raise AssertionError("No provider should be needed without evidence")

    result = run_graph(
        "What is the return policy?",
        tool=make_tool([]),
        provider=should_not_create_provider,
    )

    assert result["status"] == "insufficient_evidence"
    assert result["citations"] == []
    assert "enough information" in result["answer"]


def test_order_route_requests_identifier_and_performs_lookup():
    missing = run_graph("Where is my order?")
    assert missing["status"] == "needs_input"
    assert missing["next_action"] == "ask_for_order_id"

    provided = run_graph("Where is my order?", order_id="ORD-1001")
    assert provided["status"] == "record_not_found"
    assert provided["next_action"] == "verify_order_id"


def test_order_lookup_returns_status_without_exposing_other_tenant_data():
    result = run_graph(
        "Where is my order?", order_id="ORD-1001",
        order_tool=make_record_tool({"found": True, "external_id": "ORD-1001", "status": "shipped",
                                     "tracking_number": "TRK-9001", "estimated_delivery": None, "items": []}),
    )
    assert result["status"] == "answered"
    assert "shipped" in result["answer"]
    assert "TRK-9001" in result["answer"]


def test_ticket_lookup_asks_for_id_then_returns_synthetic_status():
    missing = run_graph("What is happening with my ticket?")
    assert missing["status"] == "needs_input"
    assert missing["next_action"] == "ask_for_ticket_id"
    found = run_graph(
        "Check my ticket", ticket_id="TKT-2001",
        ticket_tool=make_record_tool({"found": True, "external_id": "TKT-2001", "status": "open",
                                      "priority": "normal", "subject": "Damaged item", "category": "returns",
                                      "details": "Synthetic"}),
    )
    assert found["status"] == "answered"
    assert "TKT-2001" in found["answer"]


def test_sensitive_complaint_routes_to_human_review():
    result = run_graph("I want to make a complaint about an unsafe product")
    assert result["route"] == "human_review"
    assert result["priority"] == "urgent"
    assert result["__interrupt__"][0].value["type"] == "human_review"


def test_interrupt_resumes_after_human_approval_with_edited_draft():
    saver = InMemorySaver()
    graph = build_support_graph(
        make_tool([]), lambda: FakeAnswerProvider(),
        make_record_tool({"found": False}), make_record_tool({"found": False}),
        checkpointer=saver,
    )
    config = {"configurable": {"thread_id": "workflow-123"}}
    paused = graph.invoke(initial_state(
        tenant_id="demo", message="I want to make a complaint about fraud",
        order_id=None, ticket_id=None, limit=3,
    ), config)
    assert paused["__interrupt__"]

    resumed = graph.invoke(Command(resume={
        "decision": "approve", "edited_answer": "A specialist will contact you shortly."
    }), config)
    assert resumed["status"] == "approved"
    assert resumed["answer"] == "A specialist will contact you shortly."
    assert resumed["next_action"] == "send_approved_reply_manually"


def test_knowledge_tool_rejects_invalid_limit_before_search():
    tool = build_knowledge_search_tool(db=None, embedder=None, vector_store=None)
    with pytest.raises(ValidationError):
        tool.invoke({"query": "return policy", "tenant_id": "demo", "limit": 11})
