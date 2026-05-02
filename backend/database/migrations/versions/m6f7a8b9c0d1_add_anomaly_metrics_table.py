"""add anomaly_metrics table for predictive anomaly detection

All new — no existing tables touched.

Revision ID: m6f7a8b9c0d1
Revises: l5e6f7a8b9c0
Create Date: 2026-05-01 00:08:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "m6f7a8b9c0d1"
down_revision: Union[str, None] = "l5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "anomaly_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_name", sa.String(128), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("z_score", sa.Float(), nullable=True),
        sa.Column("is_anomaly", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source", sa.String(64), nullable=True),
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
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="anomaly_metrics_pkey"),
    )
    op.create_index("ix_anomaly_metrics_id", "anomaly_metrics", ["id"])
    op.create_index("ix_anomaly_metrics_device_id", "anomaly_metrics", ["device_id"])
    op.create_index("ix_anomaly_metrics_metric_name", "anomaly_metrics", ["metric_name"])
    op.create_index("ix_anomaly_metrics_is_anomaly", "anomaly_metrics", ["is_anomaly"])


def downgrade() -> None:
    op.drop_index("ix_anomaly_metrics_is_anomaly", table_name="anomaly_metrics")
    op.drop_index("ix_anomaly_metrics_metric_name", table_name="anomaly_metrics")
    op.drop_index("ix_anomaly_metrics_device_id", table_name="anomaly_metrics")
    op.drop_index("ix_anomaly_metrics_id", table_name="anomaly_metrics")
    op.drop_table("anomaly_metrics")
