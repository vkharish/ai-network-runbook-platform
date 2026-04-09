"""add incident_number to incidents

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column("incident_number", sa.Integer(), nullable=True),
    )
    op.create_index("ix_incidents_incident_number", "incidents", ["incident_number"])

    # Back-fill existing rows with sequential numbers ordered by created_at
    op.execute("""
        UPDATE incidents
        SET incident_number = sub.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at) AS rn
            FROM incidents
        ) sub
        WHERE incidents.id = sub.id
    """)


def downgrade() -> None:
    op.drop_index("ix_incidents_incident_number", table_name="incidents")
    op.drop_column("incidents", "incident_number")
