"""add oidc_sub and oidc_provider to users for SSO/OIDC integration

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-01 00:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "g7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("oidc_sub", sa.String(255), nullable=True, unique=False),
    )
    op.add_column(
        "users",
        sa.Column("oidc_provider", sa.String(64), nullable=True),
    )
    op.create_index("ix_users_oidc_sub", "users", ["oidc_sub"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_oidc_sub", table_name="users")
    op.drop_column("users", "oidc_provider")
    op.drop_column("users", "oidc_sub")
