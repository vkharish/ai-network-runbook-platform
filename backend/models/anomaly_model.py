"""AnomalyMetric — time-series metric samples and detected anomalies per device.

Each row represents one metric sample for a device. The z_score column is
populated by the anomaly detector task; is_anomaly is set True when |z| > threshold.
"""

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import func

from backend.database.base import AuditBase


class AnomalyMetric(AuditBase):
    __tablename__ = "anomaly_metrics"

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    z_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    # Source of the metric: "snmp", "netconf", "simulation", etc.
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)

    device: Mapped["Device"] = relationship("Device")  # type: ignore

    def __repr__(self) -> str:
        return f"<AnomalyMetric device={self.device_id} metric={self.metric_name} z={self.z_score}>"
