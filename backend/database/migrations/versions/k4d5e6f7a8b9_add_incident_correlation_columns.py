"""add parent_incident_id and correlation_score to incidents + PREDICTED status

All new columns are nullable — existing rows unaffected.

Revision ID: k4d5e6f7a8b9
Revises: j3c4d5e6f7a8
Create Date: 2026-05-01 00:06:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "k4d5e6f7a8b9"
down_revision: Union[str, None] = "j3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column("parent_incident_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_incidents_parent_incident_id",
        "incidents",
        "incidents",
        ["parent_incident_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_incidents_parent_incident_id", "incidents", ["parent_incident_id"])

    op.add_column(
        "incidents",
        sa.Column("correlation_score", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("incidents", "correlation_score")
    op.drop_index("ix_incidents_parent_incident_id", table_name="incidents")
    op.drop_constraint("fk_incidents_parent_incident_id", "incidents", type_="foreignkey")
    op.drop_column("incidents", "parent_incident_id")
