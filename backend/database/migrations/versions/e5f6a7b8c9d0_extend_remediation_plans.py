"""extend remediation plans: approved_by_id, approved_at, execution_log, rolled_back status

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "remediation_plans",
        sa.Column("approved_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "remediation_plans",
        sa.Column("approved_at", sa.Text(), nullable=True),
    )
    op.add_column(
        "remediation_plans",
        sa.Column("execution_log", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        "fk_remediation_plans_approved_by_id",
        "remediation_plans",
        "users",
        ["approved_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_remediation_plans_approved_by_id",
        "remediation_plans",
        ["approved_by_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_remediation_plans_approved_by_id", table_name="remediation_plans")
    op.drop_constraint("fk_remediation_plans_approved_by_id", "remediation_plans", type_="foreignkey")
    op.drop_column("remediation_plans", "execution_log")
    op.drop_column("remediation_plans", "approved_at")
    op.drop_column("remediation_plans", "approved_by_id")
