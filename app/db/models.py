from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Document(Timestamped, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'processing', 'ready', 'failed')", name="ck_documents_status"),
        Index("ix_documents_tenant_status", "tenant_id", "status"),
        Index(
            "uq_documents_active_tenant_filename",
            "tenant_id",
            "filename",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Conversation(Timestamped, Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_tenant_updated", "tenant_id", "updated_at"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Message(Timestamped, Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class SupportTicket(Timestamped, Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name="ck_tickets_priority"),
        Index("ix_tickets_tenant_status", "tenant_id", "status"),
        Index("ix_tickets_tenant_external", "tenant_id", "external_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="other")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False, default="")


class MockOrder(Timestamped, Base):
    __tablename__ = "mock_orders"
    __table_args__ = (
        Index("ix_mock_orders_tenant_external", "tenant_id", "external_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    tracking_number: Mapped[str | None] = mapped_column(String(100))
    estimated_delivery: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class ApprovalRequest(Timestamped, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (Index("ix_approvals_tenant_status", "tenant_id", "status"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    workflow_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decision_note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowExecution(Timestamped, Base):
    __tablename__ = "workflow_executions"
    __table_args__ = (Index("ix_workflows_tenant_status", "tenant_id", "status"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    conversation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    current_node: Mapped[str | None] = mapped_column(String(100))
    state_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80))
