"""Ebbinghaus-style forgetting model for knowledge patterns (ADR-0021, IV-3).

Reference: MemoryBank (arXiv:2305.10250) — strength = exp(-Δt / S) where
S (time-constant in hours) grows with importance and access reinforcement.

Strength is computed lazily on retrieval; not persisted as state.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Half-life anchor for a mid-importance, never-accessed pattern.
# 240 hours ≈ 10 days: a pattern never touched for 10 days at importance 0.5
# and zero accesses decays to 1/e (~0.37) of its initial strength.
BASE_S_HOURS = 240.0

# Retrieval floors. See ADR-0021.
TRUST_FLOOR = 0.3
STRENGTH_FLOOR = 0.05


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO8601 timestamp; tolerate missing tz by assuming UTC."""
    if not value or value == "unknown":
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def time_constant(importance: float, access_count: int) -> float:
    """S (hours) — Ebbinghaus time-constant, reinforced by importance + accesses.

    Shape: S grows logarithmically with access_count so one reinforcement
    doubles S roughly, while the hundredth has diminishing return. Importance
    multiplies on a (0.5..1.5) range so a 0-importance pattern decays twice
    as fast as a 1.0-importance one.
    """
    imp_factor = 0.5 + max(0.0, min(1.0, importance))  # [0.5, 1.5]
    access_factor = 1.0 + math.log1p(max(0, access_count))
    return BASE_S_HOURS * imp_factor * access_factor


def compute_strength(
    pattern: Dict,
    now: Optional[datetime] = None,
) -> float:
    """Return current retrieval strength in [0.0, 1.0].

    Missing fields degrade safely: an un-migrated pattern (no
    last_accessed_at) is treated as accessed at its distilled timestamp;
    a pattern with neither gets strength 1.0 (treat as newly created).
    """
    now = now or datetime.now(timezone.utc)
    anchor = _parse_iso(pattern.get("last_accessed_at")) or _parse_iso(
        pattern.get("distilled")
    )
    if anchor is None:
        return 1.0
    delta_hours = (now - anchor).total_seconds() / 3600.0
    if delta_hours <= 0:
        return 1.0
    importance = float(pattern.get("importance", 0.5))
    access_count = int(pattern.get("access_count", 0))
    s = time_constant(importance, access_count)
    return math.exp(-delta_hours / s)


def mark_accessed(
    pattern: Dict,
    now: Optional[datetime] = None,
) -> None:
    """Mutate pattern to record one retrieval access.

    Side effect by design: KnowledgeStore is single-writer and read-on-
    retrieval bookkeeping is cheap. Callers that persist patterns should
    save after a batch of marks.
    """
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="minutes")
    pattern["last_accessed_at"] = ts
    pattern["access_count"] = int(pattern.get("access_count", 0)) + 1


def is_live(
    pattern: Dict,
    now: Optional[datetime] = None,
) -> bool:
    """True if the pattern is currently retrievable.

    Combines bitemporal (valid_until) + trust floor + strength floor. A
    pattern missing any of these fields is treated leniently (legacy).
    """
    valid_until = pattern.get("valid_until")
    if valid_until is not None:
        return False
    trust = float(pattern.get("trust_score", 1.0))
    if trust < TRUST_FLOOR:
        return False
    strength = compute_strength(pattern, now=now)
    if strength < STRENGTH_FLOOR:
        return False
    return True
