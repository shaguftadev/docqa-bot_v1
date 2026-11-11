import json
from typing import Callable, TypedDict

from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph

from app.agent.classification import classify_message
from app.llm.provider import AnswerProvider
from app.rag.qdrant_store import SearchHit
from app.schemas.answers import AnswerResponse
from app.services.answer_generation import ABSTENTION, AnswerGenerationService


class SupportState(TypedDict):
    tenant_id: str
    message: str
    order_id: str | None
    ticket_id: str | None
    limit: int
    intent: str
    priority: str
    rationale: str
    route: str
    status: str
    next_action: str
    answer: str | None
    citations: list[dict]
    events: list[str]


AnswerProviderFactory = Callable[[], AnswerProvider]


def build_support_graph(
    knowledge_search_tool: BaseTool,
    answer_provider_factory: AnswerProviderFactory,
    order_lookup_tool: BaseTool,
    ticket_lookup_tool: BaseTool,
):
    """Build the per-request, typed support workflow with an explicit search tool."""
    def classify_node(state: SupportState) -> dict:
        classification = classify_message(state["message"])
        return {
            **classification.model_dump(),
            "events": [f"Classified as {classification.intent} ({classification.priority} priority)."],
        }

    def choose_route(state: SupportState) -> str:
        return state["route"]

    def knowledge_node(state: SupportState) -> dict:
        raw_hits = knowledge_search_tool.invoke(
            {
                "query": state["message"],
                "tenant_id": state["tenant_id"],
                "limit": state["limit"],
            }
        )
        hits = [SearchHit(**item) for item in json.loads(raw_hits)]
        if hits:
            result = AnswerGenerationService(answer_provider_factory()).answer(state["message"], hits)
        else:
            result = AnswerResponse(
                answer=ABSTENTION,
                status="insufficient_evidence",
                citations=[],
            )
        answered = result.status == "answered"
        return {
            "status": result.status,
            "answer": result.answer,
            "citations": [citation.model_dump(mode="json") for citation in result.citations],
            "next_action": "return_suggested_answer" if answered else "human_review_or_request_more_information",
            "events": state["events"] + [
                "Searched the knowledge base.",
                "Validated answer citations against retrieved chunks." if answered else "Insufficient evidence; abstained.",
            ],
        }

    def order_node(state: SupportState) -> dict:
        if not state["order_id"]:
            return {
                "status": "needs_input",
                "answer": "Please provide your order number so Support can look up its status.",
                "next_action": "ask_for_order_id",
                "events": state["events"] + ["Order lookup selected; requested the missing order identifier."],
            }
        record = json.loads(order_lookup_tool.invoke({
            "tenant_id": state["tenant_id"], "external_id": state["order_id"],
        }))
        if not record["found"]:
            return {
                "status": "record_not_found",
                "answer": "I couldn't find that order number. Check it and try again, or contact Support.",
                "next_action": "verify_order_id",
                "events": state["events"] + ["Looked up the exact order ID within the requested tenant; no record matched."],
            }
        delivery = f" Estimated delivery: {record['estimated_delivery']}." if record["estimated_delivery"] else ""
        tracking = f" Tracking number: {record['tracking_number']}." if record["tracking_number"] else ""
        return {
            "status": "answered",
            "answer": f"Order {record['external_id']} is {record['status']}.{tracking}{delivery}",
            "next_action": "return_order_status",
            "events": state["events"] + ["Retrieved the synthetic order record by exact ID and tenant."],
        }

    def ticket_node(state: SupportState) -> dict:
        if not state["ticket_id"]:
            return {
                "status": "needs_input",
                "answer": "Please provide your ticket number so Support can look up its status.",
                "next_action": "ask_for_ticket_id",
                "events": state["events"] + ["Ticket lookup selected; requested the missing ticket identifier."],
            }
        record = json.loads(ticket_lookup_tool.invoke({
            "tenant_id": state["tenant_id"], "external_id": state["ticket_id"],
        }))
        if not record["found"]:
            return {
                "status": "record_not_found",
                "answer": "I couldn't find that ticket number. Check it and try again, or contact Support.",
                "next_action": "verify_ticket_id",
                "events": state["events"] + ["Looked up the exact ticket ID within the requested tenant; no record matched."],
            }
        return {
            "status": "answered",
            "answer": f"Ticket {record['external_id']} is {record['status']} ({record['priority']} priority). Subject: {record['subject']}.",
            "next_action": "return_ticket_status",
            "events": state["events"] + ["Retrieved the synthetic ticket record by exact ID and tenant."],
        }

    def human_review_node(state: SupportState) -> dict:
        return {
            "status": "escalation_required",
            "answer": "This request needs review by a support agent.",
            "next_action": "human_review",
            "events": state["events"] + ["Sensitive complaint routed for human review."],
        }

    def manual_review_node(state: SupportState) -> dict:
        return {
            "status": "manual_review",
            "answer": "This request has been classified and needs support triage.",
            "next_action": "manual_triage",
            "events": state["events"] + ["No automated tool is enabled for this category yet."],
        }

    builder = StateGraph(SupportState)
    builder.add_node("classify", classify_node)
    builder.add_node("knowledge_lookup", knowledge_node)
    builder.add_node("order_lookup", order_node)
    builder.add_node("ticket_lookup", ticket_node)
    builder.add_node("human_review", human_review_node)
    builder.add_node("manual_review", manual_review_node)
    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        choose_route,
        {
            "knowledge_lookup": "knowledge_lookup",
            "order_lookup": "order_lookup",
            "ticket_lookup": "ticket_lookup",
            "human_review": "human_review",
            "manual_review": "manual_review",
        },
    )
    for terminal_node in ("knowledge_lookup", "order_lookup", "ticket_lookup", "human_review", "manual_review"):
        builder.add_edge(terminal_node, END)
    return builder.compile()


def initial_state(
    *, tenant_id: str, message: str, order_id: str | None, ticket_id: str | None = None, limit: int
) -> SupportState:
    """Create a fully populated graph state; request data stays separate from node output."""
    return {
        "tenant_id": tenant_id,
        "message": message,
        "order_id": order_id,
        "ticket_id": ticket_id,
        "limit": limit,
        "intent": "other",
        "priority": "low",
        "rationale": "",
        "route": "manual_review",
        "status": "manual_review",
        "next_action": "manual_triage",
        "answer": None,
        "citations": [],
        "events": [],
    }
