"""Skill router + usage log (ADR-0023, IV-9).

Given a context string, pick the top-K skills by cosine similarity
against their embedded (title + body). Below a configurable threshold,
``select`` returns an empty list: injecting nothing is always safer
than injecting a poorly-matched skill.

Every ``select`` call writes a ``selection`` record to
``MOLTBOOK_HOME/logs/skill-usage-YYYY-MM-DD.jsonl`` so that ``skill-
reflect`` can later aggregate per-skill success / failure counts and
sample the contexts where failures occurred.

Reference: Memento-Skills (arXiv:2603.18743) — "skill as memory unit".
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional, Tuple

import numpy as np

from . import skill_frontmatter
from .embeddings import cosine, embed_texts

logger = logging.getLogger(__name__)

# Cosine threshold below which ``select`` returns no skills (no-inject
# fallback). Calibrated conservatively — nomic-embed-text puts topically
# unrelated pairs at ~0.2-0.3; 0.45 keeps out "vaguely related" noise
# without demanding near-paraphrase.
DEFAULT_THRESHOLD = 0.45
DEFAULT_TOP_K = 3

# skill-reflect aggregator thresholds (see ADR-0023).
MIN_FAILURES_FOR_REFLECT = 2
FAILURE_RATE_FOR_REFLECT = 0.3

# Truncation for the context excerpt stored in the selection log. Short
# enough to avoid becoming a second episode log; long enough to give
# reflect some signal about the situation.
CONTEXT_EXCERPT_MAX = 500

# Default window for ``load_usage`` and ``skill-reflect``.
DEFAULT_USAGE_WINDOW_DAYS = 14

Outcome = Literal["success", "failure", "partial"]


@dataclass(frozen=True)
class SkillMatch:
    """One skill picked by ``SkillRouter.select``."""

    name: str
    path: Path
    body: str
    score: float
    meta: skill_frontmatter.SkillMeta


@dataclass
class SkillUsageStats:
    """Per-skill aggregate of selection + outcome records."""

    name: str
    selections: int = 0
    successes: int = 0
    failures: int = 0
    partials: int = 0
    failure_contexts: List[str] = field(default_factory=list)

    @property
    def outcomes(self) -> int:
        return self.successes + self.failures + self.partials

    @property
    def failure_rate(self) -> float:
        total = self.outcomes
        return (self.failures / total) if total else 0.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_minute(dt: datetime) -> str:
    return dt.isoformat(timespec="minutes")


def context_hash(context: str) -> str:
    """Short hash usable as a fallback action_id (first 16 hex of sha256)."""
    payload = f"{_now().isoformat()}:{context}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _truncate_excerpt(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= CONTEXT_EXCERPT_MAX:
        return cleaned
    return cleaned[:CONTEXT_EXCERPT_MAX] + "…"


def _default_embed(texts: List[str]) -> Optional[np.ndarray]:
    return embed_texts(texts)


class SkillRouter:
    """Route context → top-K skills by cosine, with a usage log.

    The router holds no persistent state beyond an in-memory embedding
    cache keyed by ``(path, mtime)``. A file edit invalidates the entry
    on the next ``select`` — no explicit reload hook needed.
    """

    def __init__(
        self,
        skills_dir: Path,
        *,
        embed_fn: Optional[Callable[[List[str]], Optional[np.ndarray]]] = None,
        threshold: float = DEFAULT_THRESHOLD,
        log_dir: Optional[Path] = None,
    ) -> None:
        self._skills_dir = skills_dir
        self._embed_fn = embed_fn or _default_embed
        self._threshold = threshold
        self._log_dir = log_dir
        self._cache: Dict[Path, Tuple[float, np.ndarray]] = {}

    # -----------------------------------------------------------------
    # Skill loading + embedding
    # -----------------------------------------------------------------

    def _list_skill_paths(self) -> List[Path]:
        if not self._skills_dir.is_dir():
            return []
        return sorted(p for p in self._skills_dir.glob("*.md") if p.is_file())

    def _read_skill(self, path: Path) -> Optional[Tuple[skill_frontmatter.SkillMeta, str]]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to read skill %s: %s", path, exc)
            return None
        return skill_frontmatter.parse(text)

    def _embed_missing(self, paths: List[Path]) -> Dict[Path, np.ndarray]:
        """Embed any skill whose cache entry is missing or stale."""
        need: List[Path] = []
        texts: List[str] = []
        for path in paths:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            cached = self._cache.get(path)
            if cached is not None and cached[0] == mtime:
                continue
            parsed = self._read_skill(path)
            if parsed is None:
                continue
            _, body = parsed
            if not body.strip():
                continue
            need.append(path)
            texts.append(body)
        if not need:
            return {}
        vectors = self._embed_fn(texts)
        if vectors is None or len(vectors) != len(need):
            logger.warning("Skill embedding failed (got %s for %d inputs)",
                           "None" if vectors is None else len(vectors), len(need))
            return {}
        updated: Dict[Path, np.ndarray] = {}
        for path, vec in zip(need, vectors):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            arr = np.asarray(vec, dtype=np.float32)
            self._cache[path] = (mtime, arr)
            updated[path] = arr
        return updated

    def _embedding_for(self, path: Path) -> Optional[np.ndarray]:
        cached = self._cache.get(path)
        return cached[1] if cached is not None else None

    # -----------------------------------------------------------------
    # Selection
    # -----------------------------------------------------------------

    def select(
        self,
        context: str,
        *,
        top_k: int = DEFAULT_TOP_K,
        action_id: Optional[str] = None,
    ) -> List[SkillMatch]:
        """Return top-K skills above the configured cosine threshold.

        Below threshold → empty list (no-inject fallback). Always writes
        a selection record to the usage log, including when no skill
        matched, so ``skill-reflect`` can spot under-served contexts.
        """
        if not context or not context.strip():
            return []
        paths = self._list_skill_paths()
        if not paths:
            self._log_selection(action_id, context, [], top_k=top_k)
            return []

        # Refresh / populate cache for all current skills. We evict
        # entries whose file no longer exists so they don't linger.
        live_paths = set(paths)
        for stale in list(self._cache):
            if stale not in live_paths:
                del self._cache[stale]
        self._embed_missing(paths)

        ctx_vec_res = self._embed_fn([context])
        if ctx_vec_res is None or len(ctx_vec_res) == 0:
            logger.warning("Context embedding failed; returning no skills.")
            self._log_selection(action_id, context, [], top_k=top_k)
            return []
        ctx_vec = np.asarray(ctx_vec_res[0], dtype=np.float32)

        scored: List[Tuple[Path, float, skill_frontmatter.SkillMeta, str]] = []
        for path in paths:
            emb = self._embedding_for(path)
            if emb is None:
                continue
            parsed = self._read_skill(path)
            if parsed is None:
                continue
            meta, body = parsed
            if not body.strip():
                continue
            score = cosine(ctx_vec, emb)
            if score < self._threshold:
                continue
            scored.append((path, score, meta, body))

        scored.sort(
            key=lambda s: (
                s[1],
                s[2].success_count - s[2].failure_count,
            ),
            reverse=True,
        )
        top = scored[: max(0, top_k)]
        matches = [
            SkillMatch(
                name=path.name,
                path=path,
                body=body,
                score=float(score),
                meta=meta,
            )
            for path, score, meta, body in top
        ]
        self._log_selection(action_id, context, matches, top_k=top_k)
        return matches

    # -----------------------------------------------------------------
    # Usage logging
    # -----------------------------------------------------------------

    def _log_path_for(self, now: datetime) -> Optional[Path]:
        if self._log_dir is None:
            return None
        return self._log_dir / f"skill-usage-{now.strftime('%Y-%m-%d')}.jsonl"

    def _append_record(self, record: Dict[str, Any]) -> None:
        if self._log_dir is None:
            return
        path = self._log_path_for(_now())
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            old_umask = os.umask(0o177)
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            finally:
                os.umask(old_umask)
        except OSError as exc:
            logger.warning("Failed to write skill-usage log %s: %s", path, exc)

    def _log_selection(
        self,
        action_id: Optional[str],
        context: str,
        matches: List[SkillMatch],
        *,
        top_k: int,
    ) -> str:
        action_id = action_id or context_hash(context)
        record = {
            "ts": _iso_minute(_now()),
            "type": "selection",
            "action_id": action_id,
            "context_excerpt": _truncate_excerpt(context),
            "selected": [m.name for m in matches],
            "scores": [round(m.score, 4) for m in matches],
            "threshold": self._threshold,
            "top_k": top_k,
        }
        self._append_record(record)
        return action_id

    def record_outcome(
        self,
        action_id: str,
        outcome: Outcome,
        *,
        note: Optional[str] = None,
    ) -> None:
        if outcome not in ("success", "failure", "partial"):
            raise ValueError(f"unknown outcome: {outcome}")
        record: Dict[str, Any] = {
            "ts": _iso_minute(_now()),
            "type": "outcome",
            "action_id": action_id,
            "outcome": outcome,
        }
        if note:
            record["note"] = note
        self._append_record(record)

    # -----------------------------------------------------------------
    # Reading back
    # -----------------------------------------------------------------

    def load_usage(self, days: int = DEFAULT_USAGE_WINDOW_DAYS) -> List[Dict[str, Any]]:
        """Read usage records from the last ``days`` daily log files.

        Corrupt lines are skipped (defensive — this log is append-only
        but can be edited by operators). Returns records in file order,
        oldest day first.
        """
        if self._log_dir is None or not self._log_dir.is_dir():
            return []
        today = _now().date()
        records: List[Dict[str, Any]] = []
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            path = self._log_dir / f"skill-usage-{day.strftime('%Y-%m-%d')}.jsonl"
            if not path.exists():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            except OSError:
                continue
        return records


# ---------------------------------------------------------------------------
# Aggregation helpers (pure functions, used by skill-reflect)
# ---------------------------------------------------------------------------


def aggregate_usage(records: Iterable[Dict[str, Any]]) -> Dict[str, SkillUsageStats]:
    """Join selection → outcome records by ``action_id``; roll up per skill.

    A selection that has no outcome record yet contributes to
    ``selections`` only — the skill was picked but the action hadn't
    resolved by the aggregation window.
    """
    selections_by_action: Dict[str, List[str]] = {}
    contexts_by_action: Dict[str, str] = {}
    outcomes_by_action: Dict[str, Tuple[str, Optional[str]]] = {}

    for record in records:
        rtype = record.get("type")
        action_id = record.get("action_id")
        if not action_id:
            continue
        if rtype == "selection":
            skills = record.get("selected") or []
            if isinstance(skills, list):
                selections_by_action[action_id] = [str(s) for s in skills]
            excerpt = record.get("context_excerpt")
            if isinstance(excerpt, str):
                contexts_by_action[action_id] = excerpt
        elif rtype == "outcome":
            outcome = record.get("outcome")
            note = record.get("note")
            if isinstance(outcome, str):
                outcomes_by_action[action_id] = (outcome, note if isinstance(note, str) else None)

    stats: Dict[str, SkillUsageStats] = {}
    for action_id, skill_names in selections_by_action.items():
        outcome_pair = outcomes_by_action.get(action_id)
        outcome, _note = outcome_pair if outcome_pair else (None, None)
        context_excerpt = contexts_by_action.get(action_id, "")
        for name in skill_names:
            bucket = stats.setdefault(name, SkillUsageStats(name=name))
            bucket.selections += 1
            if outcome == "success":
                bucket.successes += 1
            elif outcome == "failure":
                bucket.failures += 1
                if context_excerpt:
                    bucket.failure_contexts.append(context_excerpt)
            elif outcome == "partial":
                bucket.partials += 1
                if context_excerpt:
                    bucket.failure_contexts.append(context_excerpt)
    return stats


def needs_reflection(stats: SkillUsageStats) -> bool:
    """Policy gate for ``skill-reflect``: enough failures and high rate?"""
    return (
        stats.failures >= MIN_FAILURES_FOR_REFLECT
        and stats.failure_rate >= FAILURE_RATE_FOR_REFLECT
    )
