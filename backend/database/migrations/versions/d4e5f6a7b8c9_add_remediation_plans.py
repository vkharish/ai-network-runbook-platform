"""add remediation_plans table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-22 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "remediation_plans",
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_approval"),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("llm_provider", sa.String(64), nullable=False, server_default=""),
        sa.Column("executed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("executed_at", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], name="remediation_plans_incident_id_fkey", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["executed_by_id"], ["users.id"], name="remediation_plans_executed_by_id_fkey", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="remediation_plans_pkey"),
        sa.UniqueConstraint("incident_id", name="remediation_plans_incident_id_key"),
    )
    op.create_index("ix_remediation_plans_id", "remediation_plans", ["id"], unique=False)
    op.create_index("ix_remediation_plans_incident_id", "remediation_plans", ["incident_id"], unique=True)
    op.create_index("ix_remediation_plans_status", "remediation_plans", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_remediation_plans_status", table_name="remediation_plans")
    op.drop_index("ix_remediation_plans_incident_id", table_name="remediation_plans")
    op.drop_index("ix_remediation_plans_id", table_name="remediation_plans")
    op.drop_table("remediation_plans")
