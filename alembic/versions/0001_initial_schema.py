"""Create initial SupportPilot metadata tables.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversations_tenant_updated", "conversations", ["tenant_id", "updated_at"])

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'processing', 'ready', 'failed')", name="ck_documents_status"),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_tenant_status", "documents", ["tenant_id", "status"])

    op.create_table(
        "mock_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("external_id", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("tracking_number", sa.String(100)),
        sa.Column("estimated_delivery", sa.DateTime(timezone=True)),
        sa.Column("items_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_mock_orders_tenant_id", "mock_orders", ["tenant_id"])
    op.create_index("ix_mock_orders_tenant_external", "mock_orders", ["tenant_id", "external_id"], unique=True)

    op.create_table(
        "support_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("external_id", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name="ck_tickets_priority"),
    )
    op.create_index("ix_support_tickets_tenant_id", "support_tickets", ["tenant_id"])
    op.create_index("ix_tickets_tenant_status", "support_tickets", ["tenant_id", "status"])
    op.create_index("ix_tickets_tenant_external", "support_tickets", ["tenant_id", "external_id"], unique=True)

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])

    op.create_table(
        "workflow_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column("current_node", sa.String(100)),
        sa.Column("state_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_workflow_executions_tenant_id", "workflow_executions", ["tenant_id"])
    op.create_index("ix_workflow_executions_correlation_id", "workflow_executions", ["correlation_id"])
    op.create_index("ix_workflows_tenant_status", "workflow_executions", ["tenant_id", "status"])

    op.create_table(
        "approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decision_note", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflow_executions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_approval_requests_tenant_id", "approval_requests", ["tenant_id"])
    op.create_index("ix_approval_requests_workflow_id", "approval_requests", ["workflow_id"])
    op.create_index("ix_approvals_tenant_status", "approval_requests", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_table("approval_requests")
    op.drop_table("workflow_executions")
    op.drop_table("messages")
    op.drop_table("support_tickets")
    op.drop_table("mock_orders")
    op.drop_table("documents")
    op.drop_table("conversations")
