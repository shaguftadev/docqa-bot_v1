from typing import Literal

from pydantic import BaseModel


Intent = Literal[
    "order_status",
    "ticket_status",
    "return_refund",
    "product_information",
    "technical_issue",
    "billing",
    "complaint",
    "other",
]
Priority = Literal["low", "normal", "high", "urgent"]
Route = Literal["knowledge_lookup", "order_lookup", "ticket_lookup", "human_review", "manual_review"]


class Classification(BaseModel):
    intent: Intent
    priority: Priority
    rationale: str
    route: Route


_COMPLAINT_TERMS = (
    "complaint", "chargeback", "fraud", "lawsuit", "lawyer", "legal action",
    "unsafe", "injured", "injury", "harassment", "discrimination", "refund denied",
)
_URGENT_TERMS = (
    "chargeback", "fraud", "lawsuit", "lawyer", "legal action", "unsafe",
    "injured", "injury", "data breach", "account hacked", "security breach",
)
_ORDER_TERMS = (
    "where is my order", "track my order", "track order", "order status",
    "tracking number", "delivery status", "when will my order",
)
_TICKET_TERMS = ("ticket", "case number", "support case")
_RETURN_TERMS = (
    "return", "refund", "damaged", "defective", "replacement", "exchange",
)
_TECH_TERMS = (
    "not working", "doesn't work", "does not work", "error", "crash",
    "can't log in", "cannot log in", "login", "troubleshoot", "technical issue",
)
_BILLING_TERMS = ("billing", "invoice", "payment", "charged", "subscription", "receipt")
_PRODUCT_TERMS = ("product", "feature", "compatible", "compatibility", "specification", "warranty", "size")


def classify_message(message: str) -> Classification:
    """Classify with explicit keyword rules so route decisions are predictable."""
    normalized = " ".join(message.casefold().split())
    if any(term in normalized for term in _COMPLAINT_TERMS):
        return Classification(
            intent="complaint",
            priority="urgent" if any(term in normalized for term in _URGENT_TERMS) else "high",
            rationale="The message contains a complaint or sensitive-dispute phrase.",
            route="human_review",
        )
    if any(term in normalized for term in _ORDER_TERMS):
        return Classification(
            intent="order_status", priority="normal",
            rationale="The message asks about an order, shipment, or delivery status.",
            route="order_lookup",
        )
    if any(term in normalized for term in _TICKET_TERMS):
        return Classification(
            intent="ticket_status", priority="normal",
            rationale="The message asks about a support ticket or case.",
            route="ticket_lookup",
        )
    if any(term in normalized for term in _RETURN_TERMS):
        return Classification(
            intent="return_refund", priority="normal",
            rationale="The message asks about a return, refund, damage, or replacement policy.",
            route="knowledge_lookup",
        )
    if any(term in normalized for term in _TECH_TERMS):
        return Classification(
            intent="technical_issue", priority="normal",
            rationale="The message describes a product or account problem.",
            route="manual_review",
        )
    if any(term in normalized for term in _BILLING_TERMS):
        return Classification(
            intent="billing", priority="normal",
            rationale="The message asks about billing, payment, or an invoice.",
            route="manual_review",
        )
    if any(term in normalized for term in _PRODUCT_TERMS):
        return Classification(
            intent="product_information", priority="normal",
            rationale="The message asks for product information or specifications.",
            route="knowledge_lookup",
        )
    return Classification(
        intent="other", priority="low",
        rationale="No supported intent rule matched the message.",
        route="manual_review",
    )
