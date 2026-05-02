"""Feedback-based RAG score adjustment.

Reads DiagnosisFeedback records to compute a per-chunk score adjustment factor.
For each chunk_id:
  - helpful ratings contribute +0.05 boost (capped at +0.20)
  - not_helpful ratings contribute -0.05 penalty (floored at -0.20)

The adjusted score is clamped to [0.0, 1.0].

Only called when FEEDBACK_ENABLED=true.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from backend.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)

_BOOST_PER_HELPFUL = 0.05
_PENALTY_PER_NOT_HELPFUL = 0.05
_MAX_BOOST = 0.20
_MAX_PENALTY = 0.20


async def build_score_adjustments(db: "AsyncSession") -> dict[str, float]:
    """
    Build a mapping of {chunk_id: score_adjustment} from recent feedback.
    Score adjustments are in range [-0.20, +0.20].
    """
    from sqlalchemy import select
    from backend.models.diagnosis_feedback_model import DiagnosisFeedback, FeedbackRating

    result = await db.execute(
        select(DiagnosisFeedback).where(DiagnosisFeedback.cited_chunk_ids.isnot(None))
    )
    feedbacks = result.scalars().all()

    helpful_counts: dict[str, int] = {}
    not_helpful_counts: dict[str, int] = {}

    for fb in feedbacks:
        chunk_ids = fb.cited_chunk_ids or []
        for cid in chunk_ids:
            if fb.rating == FeedbackRating.HELPFUL.value:
                helpful_counts[cid] = helpful_counts.get(cid, 0) + 1
            else:
                not_helpful_counts[cid] = not_helpful_counts.get(cid, 0) + 1

    adjustments: dict[str, float] = {}
    all_chunk_ids = set(helpful_counts) | set(not_helpful_counts)
    for cid in all_chunk_ids:
        boost = min(helpful_counts.get(cid, 0) * _BOOST_PER_HELPFUL, _MAX_BOOST)
        penalty = min(not_helpful_counts.get(cid, 0) * _PENALTY_PER_NOT_HELPFUL, _MAX_PENALTY)
        adjustments[cid] = round(boost - penalty, 4)

    return adjustments


def apply_feedback_scores(
    candidates: list[dict[str, Any]],
    adjustments: dict[str, float],
) -> list[dict[str, Any]]:
    """Apply pre-computed adjustments to candidate scores. Clamps to [0, 1]."""
    for c in candidates:
        chunk_id = c.get("chunk_index", "")
        adj = adjustments.get(str(chunk_id), 0.0)
        c["score"] = round(max(0.0, min(1.0, c["score"] + adj)), 4)
    return sorted(candidates, key=lambda x: x["score"], reverse=True)
