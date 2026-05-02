"""Incident Correlation — embedding cosine similarity + structural bonuses.

Only called when CORRELATION_ENABLED=true.

Algorithm:
  1. Embed the new incident's title + description.
  2. Fetch all OPEN/DIAGNOSING incidents from the last 24 hours.
  3. Compute cosine similarity between the new embedding and each candidate.
  4. Add structural bonuses: same device (+0.10), same protocol (+0.05).
  5. If best score >= threshold (default 0.75), link as child of that parent.

Returns (parent_id, score) or (None, 0.0) when no match exceeds threshold.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from backend.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)

_CORRELATION_THRESHOLD = 0.75
_DEVICE_BONUS = 0.10
_PROTOCOL_BONUS = 0.05
_LOOKBACK_HOURS = 24


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x ** 2 for x in a) ** 0.5
    mag_b = sum(x ** 2 for x in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


async def find_parent_incident(
    db: "AsyncSession",
    incident_id: uuid.UUID,
    title: str,
    description: str,
    affected_device: str | None,
    affected_protocol: str | None,
) -> tuple[uuid.UUID | None, float]:
    """
    Find the best correlated parent incident for a newly created incident.
    Returns (parent_id, score) or (None, 0.0).
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select
    from backend.models.incident_model import Incident, IncidentStatus
    from backend.rag.embedding_engine import get_embedding_engine

    cutoff = datetime.now(timezone.utc) - timedelta(hours=_LOOKBACK_HOURS)

    result = await db.execute(
        select(Incident).where(
            Incident.id != incident_id,
            Incident.status.in_([IncidentStatus.OPEN.value, IncidentStatus.DIAGNOSING.value]),
            Incident.created_at >= cutoff,
            Incident.parent_incident_id.is_(None),  # only top-level incidents as parents
        )
    )
    candidates = result.scalars().all()

    if not candidates:
        return None, 0.0

    engine = get_embedding_engine()
    new_text = f"{title} {description}"
    try:
        new_emb = engine.embed_one(new_text)
    except Exception as exc:
        log.warning("correlation_embed_failed", error=str(exc))
        return None, 0.0

    best_id: uuid.UUID | None = None
    best_score = 0.0

    for candidate in candidates:
        cand_text = f"{candidate.title} {candidate.description}"
        try:
            cand_emb = engine.embed_one(cand_text)
        except Exception:
            continue

        score = _cosine_similarity(new_emb, cand_emb)

        # Structural bonuses
        if affected_device and candidate.affected_device == affected_device:
            score = min(1.0, score + _DEVICE_BONUS)
        if affected_protocol and candidate.affected_protocol == affected_protocol:
            score = min(1.0, score + _PROTOCOL_BONUS)

        if score > best_score:
            best_score = score
            best_id = candidate.id

    if best_score >= _CORRELATION_THRESHOLD and best_id is not None:
        log.info(
            "incident_correlated",
            incident_id=str(incident_id),
            parent_id=str(best_id),
            score=round(best_score, 4),
        )
        return best_id, round(best_score, 4)

    return None, 0.0
