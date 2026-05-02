"""Predictive Anomaly Detection — z-score statistical analysis on device metrics.

Only called when PREDICTIVE_ENABLED=true.

Algorithm (per device per metric):
  1. Fetch the last N samples from anomaly_metrics.
  2. Compute mean and std-dev of the window.
  3. For each new sample, compute z-score = (value - mean) / std.
  4. If |z| >= threshold (default 3.0), mark is_anomaly=True and optionally
     create a PREDICTED incident so operators are alerted proactively.

Entry points:
  - record_metric(db, device_id, metric_name, value, source) — called by
    monitoring_task or NX-API/eAPI collectors to record a sample.
  - run_detection(db, device_id, metric_name) — called by prediction_task
    to score the latest sample and create incidents when anomalous.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from backend.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)

_Z_THRESHOLD = 3.0
_WINDOW_SIZE = 50   # samples used to compute rolling mean/std


async def record_metric(
    db: "AsyncSession",
    device_id: uuid.UUID,
    metric_name: str,
    value: float,
    source: str = "unknown",
) -> None:
    """Insert a new metric sample — does NOT compute z-score (done by run_detection)."""
    from backend.models.anomaly_model import AnomalyMetric

    sample = AnomalyMetric(
        id=uuid.uuid4(),
        device_id=device_id,
        metric_name=metric_name,
        metric_value=value,
        source=source,
    )
    db.add(sample)
    await db.commit()


async def run_detection(
    db: "AsyncSession",
    device_id: uuid.UUID,
    metric_name: str,
) -> dict:
    """
    Score the latest sample for a device+metric pair.
    Returns dict with z_score, is_anomaly, and optionally incident_id.
    """
    from sqlalchemy import select, desc
    from backend.models.anomaly_model import AnomalyMetric

    # Fetch last N+1 samples (last one is the "new" sample to score)
    result = await db.execute(
        select(AnomalyMetric)
        .where(
            AnomalyMetric.device_id == device_id,
            AnomalyMetric.metric_name == metric_name,
        )
        .order_by(desc(AnomalyMetric.created_at))
        .limit(_WINDOW_SIZE + 1)
    )
    samples = result.scalars().all()

    if len(samples) < 2:
        return {"z_score": None, "is_anomaly": False, "incident_id": None}

    # Most recent is samples[0]; window is samples[1:]
    latest = samples[0]
    window_values = [s.metric_value for s in samples[1:]]

    mean = sum(window_values) / len(window_values)
    variance = sum((v - mean) ** 2 for v in window_values) / len(window_values)
    std = variance ** 0.5

    if std == 0:
        z_score = 0.0
    else:
        z_score = (latest.metric_value - mean) / std

    is_anomaly = abs(z_score) >= _Z_THRESHOLD

    # Update the sample record
    latest.z_score = round(z_score, 4)
    latest.is_anomaly = is_anomaly
    await db.commit()

    incident_id = None
    if is_anomaly:
        incident_id = await _create_predicted_incident(db, device_id, metric_name, latest.metric_value, z_score)

    return {
        "z_score": round(z_score, 4),
        "is_anomaly": is_anomaly,
        "incident_id": str(incident_id) if incident_id else None,
    }


async def _create_predicted_incident(
    db: "AsyncSession",
    device_id: uuid.UUID,
    metric_name: str,
    value: float,
    z_score: float,
) -> uuid.UUID | None:
    """Create a PREDICTED incident when an anomaly is detected."""
    from sqlalchemy import select
    from backend.models.incident_model import Incident, IncidentStatus, IncidentSeverity
    from backend.models.device_model import Device  # type: ignore[attr-defined]

    # Fetch device hostname
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    hostname = device.hostname if device else str(device_id)

    # Avoid duplicate PREDICTED incidents for same device+metric pair
    existing = await db.execute(
        select(Incident).where(
            Incident.affected_device == hostname,
            Incident.status == IncidentStatus.PREDICTED.value,
            Incident.title.like(f"%{metric_name}%"),
        )
    )
    if existing.scalar_one_or_none():
        return None

    severity = IncidentSeverity.P2.value if abs(z_score) >= 5.0 else IncidentSeverity.P3.value

    incident = Incident(
        id=uuid.uuid4(),
        title=f"[PREDICTED] Anomalous {metric_name} on {hostname}",
        description=(
            f"Predictive anomaly detector flagged {metric_name}={value:.2f} "
            f"(z-score={z_score:.2f}, threshold=±{_Z_THRESHOLD}) on device {hostname}. "
            f"This incident was auto-created — please investigate before impact occurs."
        ),
        status=IncidentStatus.PREDICTED.value,
        severity=severity,
        affected_device=hostname,
        created_by=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # system user
    )
    db.add(incident)
    await db.commit()
    await db.refresh(incident)

    log.info(
        "predicted_incident_created",
        incident_id=str(incident.id),
        device=hostname,
        metric=metric_name,
        z_score=round(z_score, 4),
    )
    return incident.id
