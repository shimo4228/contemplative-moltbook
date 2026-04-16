"""Post-action feedback for knowledge patterns (ADR-0021, IV-10).

Records whether a retrieved pattern helped the agent's subsequent action.
Stub-level for ADR-0021: provides the write API and trust-score
adjustment; full attribution from episode outcomes depends on the skill
router log introduced in ADR-0023 and is wired up there.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Iterable, Optional

from ._io import now_iso

logger = logging.getLogger(__name__)

# How much each success/failure nudges trust_score. Small because
# attribution is noisy — one action rarely proves a pattern's worth.
TRUST_DELTA_SUCCESS = 0.02
TRUST_DELTA_FAILURE = 0.05  # asymmetric: failures hurt more than successes help


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def record_outcome(
    pattern: Dict,
    *,
    success: bool,
    now: Optional[datetime] = None,
) -> None:
    """Mutate pattern counters and nudge trust_score.

    Single-pattern version. For batch attribution (one action, N retrieved
    patterns) call ``record_outcome_batch``.
    """
    if success:
        pattern["success_count"] = int(pattern.get("success_count", 0)) + 1
        delta = TRUST_DELTA_SUCCESS
    else:
        pattern["failure_count"] = int(pattern.get("failure_count", 0)) + 1
        delta = -TRUST_DELTA_FAILURE
    current = float(pattern.get("trust_score", 0.6))
    pattern["trust_score"] = _clamp(current + delta)
    pattern["trust_updated_at"] = (
        now.isoformat(timespec="minutes") if now else now_iso()
    )


def record_outcome_batch(
    patterns: Iterable[Dict],
    *,
    success: bool,
    now: Optional[datetime] = None,
) -> int:
    """Apply ``record_outcome`` to each pattern. Returns count updated."""
    count = 0
    for pattern in patterns:
        record_outcome(pattern, success=success, now=now)
        count += 1
    return count
