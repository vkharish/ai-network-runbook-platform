"""add auto_generated and source_incident_id to runbooks

All new columns are nullable/default — existing rows unaffected.

Revision ID: l5e6f7a8b9c0
Revises: k4d5e6f7a8b9
Create Date: 2026-05-01 00:07:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "l5e6f7a8b9c0"
down_revision: Union[str, None] = "k4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runbooks",
        sa.Column("auto_generated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "runbooks",
        sa.Column("source_incident_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_runbooks_source_incident_id",
        "runbooks",
        "incidents",
        ["source_incident_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_runbooks_source_incident_id", "runbooks", ["source_incident_id"])


def downgrade() -> None:
    op.drop_index("ix_runbooks_source_incident_id", table_name="runbooks")
    op.drop_constraint("fk_runbooks_source_incident_id", "runbooks", type_="foreignkey")
    op.drop_column("runbooks", "source_incident_id")
    op.drop_column("runbooks", "auto_generated")
