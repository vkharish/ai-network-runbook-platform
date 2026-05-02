"""add diagnosis_feedback table for feedback-loop reranking

All new — no existing tables touched. Safe to apply without downtime.

Revision ID: j3c4d5e6f7a8
Revises: i2b3c4d5e6f7
Create Date: 2026-05-01 00:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "j3c4d5e6f7a8"
down_revision: Union[str, None] = "i2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "diagnosis_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rating", sa.String(20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("cited_chunk_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="diagnosis_feedback_pkey"),
    )
    op.create_index("ix_diagnosis_feedback_id", "diagnosis_feedback", ["id"])
    op.create_index("ix_diagnosis_feedback_incident_id", "diagnosis_feedback", ["incident_id"])


def downgrade() -> None:
    op.drop_index("ix_diagnosis_feedback_incident_id", table_name="diagnosis_feedback")
    op.drop_index("ix_diagnosis_feedback_id", table_name="diagnosis_feedback")
    op.drop_table("diagnosis_feedback")
