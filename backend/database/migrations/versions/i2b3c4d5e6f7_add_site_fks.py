"""add site_id FK to devices, incidents, users for multi-tenancy

All new columns are nullable — existing rows unaffected. Safe to apply
without downtime and without any data migration.

Revision ID: i2b3c4d5e6f7
Revises: h1a2b3c4d5e6
Create Date: 2026-05-01 00:04:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "i2b3c4d5e6f7"
down_revision: Union[str, None] = "h1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("devices", "incidents", "users")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table}_site_id",
            table,
            "sites",
            ["site_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(f"ix_{table}_site_id", table, ["site_id"])


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_index(f"ix_{table}_site_id", table_name=table)
        op.drop_constraint(f"fk_{table}_site_id", table, type_="foreignkey")
        op.drop_column(table, "site_id")
