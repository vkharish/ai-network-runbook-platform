"""add sites table for multi-tenant isolation

Revision ID: h1a2b3c4d5e6
Revises: g7b8c9d0e1f2
Create Date: 2026-05-01 00:03:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "h1a2b3c4d5e6"
down_revision: Union[str, None] = "g7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="sites_pkey"),
        sa.UniqueConstraint("name", name="sites_name_key"),
        sa.UniqueConstraint("slug", name="sites_slug_key"),
    )
    op.create_index("ix_sites_id", "sites", ["id"])
    op.create_index("ix_sites_name", "sites", ["name"], unique=True)
    op.create_index("ix_sites_slug", "sites", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_sites_slug", table_name="sites")
    op.drop_index("ix_sites_name", table_name="sites")
    op.drop_index("ix_sites_id", table_name="sites")
    op.drop_table("sites")
