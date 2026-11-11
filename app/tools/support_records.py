import json
from datetime import timezone

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MockOrder, SupportTicket


class RecordLookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tenant_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    external_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _isoformat(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def build_order_lookup_tool(db: Session) -> StructuredTool:
    """Build a read-only exact-ID order lookup scoped to one tenant."""
    def lookup_order(tenant_id: str, external_id: str) -> str:
        record = db.scalar(select(MockOrder).where(
            MockOrder.tenant_id == tenant_id,
            MockOrder.external_id == external_id,
        ))
        if record is None:
            return json.dumps({"found": False})
        return json.dumps({
            "found": True,
            "external_id": record.external_id,
            "status": record.status,
            "tracking_number": record.tracking_number,
            "estimated_delivery": _isoformat(record.estimated_delivery),
            "items": record.items_json,
        })

    return StructuredTool.from_function(
        func=lookup_order,
        name="lookup_mock_order",
        description="Read a synthetic order by exact order number, scoped to the supplied tenant.",
        args_schema=RecordLookupInput,
    )


def build_ticket_lookup_tool(db: Session) -> StructuredTool:
    """Build a read-only exact-ID ticket lookup scoped to one tenant."""
    def lookup_ticket(tenant_id: str, external_id: str) -> str:
        record = db.scalar(select(SupportTicket).where(
            SupportTicket.tenant_id == tenant_id,
            SupportTicket.external_id == external_id,
        ))
        if record is None:
            return json.dumps({"found": False})
        return json.dumps({
            "found": True,
            "external_id": record.external_id,
            "status": record.status,
            "category": record.category,
            "priority": record.priority,
            "subject": record.subject,
            "details": record.details,
        })

    return StructuredTool.from_function(
        func=lookup_ticket,
        name="lookup_mock_ticket",
        description="Read a synthetic support ticket by exact ticket number, scoped to the supplied tenant.",
        args_schema=RecordLookupInput,
    )
