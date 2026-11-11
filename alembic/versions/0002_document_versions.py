"""Track the active version for each tenant document name.

Revision ID: 0002_doc_versions
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_doc_versions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.execute(
        sa.text(
            "WITH ranked AS ("
            " SELECT id, row_number() OVER (PARTITION BY tenant_id, filename ORDER BY created_at DESC, id) AS rank "
            " FROM documents WHERE is_active"
            ") UPDATE documents SET is_active = false "
            "WHERE id IN (SELECT id FROM ranked WHERE rank > 1)"
        )
    )
    op.create_index(
        "uq_documents_active_tenant_filename",
        "documents",
        ["tenant_id", "filename"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("uq_documents_active_tenant_filename", table_name="documents")
    op.drop_column("documents", "is_active")
