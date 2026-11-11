from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.documents import SearchHitResponse


class AgentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    tenant_id: str = Field(default="demo", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    message: str = Field(min_length=1, max_length=5000)
    order_id: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    ticket_id: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    limit: int = Field(default=5, ge=1, le=10)


class AgentResponse(BaseModel):
    intent: Literal[
        "order_status", "ticket_status", "return_refund", "product_information", "technical_issue",
        "billing", "complaint", "other",
    ]
    priority: Literal["low", "normal", "high", "urgent"]
    rationale: str
    route: Literal["knowledge_lookup", "order_lookup", "ticket_lookup", "human_review", "manual_review"]
    status: Literal[
        "answered", "insufficient_evidence", "needs_input", "tool_pending", "record_not_found",
        "escalation_required", "manual_review", "approval_pending", "approved", "rejected",
    ]
    next_action: str
    answer: str | None
    citations: list[SearchHitResponse]
    events: list[str]
    workflow_id: UUID
    approval_id: UUID | None = None
    review: dict[str, Any] | None = None


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    tenant_id: str = Field(default="demo", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    decision: Literal["approve", "reject"]
    edited_answer: str | None = Field(default=None, max_length=5000)
    decision_note: str | None = Field(default=None, max_length=2000)


class WorkflowStatusResponse(BaseModel):
    workflow_id: UUID
    tenant_id: str
    status: str
    current_node: str | None
    correlation_id: str
    state: dict[str, Any]
    approval_id: UUID | None = None
    approval_status: str | None = None
    created_at: datetime
    updated_at: datetime
