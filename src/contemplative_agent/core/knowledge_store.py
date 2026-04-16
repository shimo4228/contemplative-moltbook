"""Layer 2: KnowledgeStore — distilled learned patterns as JSON."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ._io import now_iso, write_restricted
from .config import FORBIDDEN_SUBSTRING_PATTERNS
from .forgetting import compute_strength

logger = logging.getLogger(__name__)

# ADR-0021 source_type values. "unknown" is the migration default for
# legacy patterns without recorded provenance.
SOURCE_TYPES = (
    "self_reflection",
    "external_reply",
    "external_post",
    "user_input",
    "mixed",
    "unknown",
)

# ADR-0021 base trust by source. Applied at distill time; later adjusted
# by feedback.py and approval-gate hooks.
TRUST_BASE_BY_SOURCE: Dict[str, float] = {
    "self_reflection": 0.9,
    "user_input": 0.7,
    "unknown": 0.6,
    "external_reply": 0.55,
    "external_post": 0.5,
    "mixed": 0.5,  # overridden to min(inputs) when mixed sources are known
}

DEFAULT_TRUST = TRUST_BASE_BY_SOURCE["unknown"]


def effective_importance(p: dict) -> float:
    """Compute retrieval weight: importance × time decay × trust × strength.

    The legacy term ``importance × 0.95^days_elapsed`` is retained as a
    coarse aging signal; ADR-0021 augments it with trust (provenance
    quality) and strength (Ebbinghaus access-aware decay). Patterns
    missing the new fields degrade to legacy-only scoring.
    """
    base = p.get("importance", 0.5)
    distilled = p.get("distilled", "")
    if not distilled or distilled == "unknown":
        legacy = base * 0.1  # Unknown timestamp → heavy penalty
    else:
        try:
            dt = datetime.fromisoformat(distilled)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
            days = max(0.0, days)
            legacy = base * (0.95 ** days)
        except (ValueError, TypeError):
            legacy = base * 0.1

    trust = float(p.get("trust_score", 1.0))
    strength = compute_strength(p) if "last_accessed_at" in p or "access_count" in p else 1.0
    return max(0.0, min(1.0, legacy * trust * strength))


class KnowledgeStore:
    """Manages distilled learned patterns as a JSON file.

    Patterns are the only data stored here — all other data
    (agents, post topics, insights) lives in JSONL episode logs.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path
        self._learned_patterns: List[dict] = []  # [{"pattern": str, "distilled": str}]

    def has_persisted_file(self) -> bool:
        """Check whether the backing JSON file exists on disk."""
        return self._path is not None and self._path.exists()

    def add_learned_pattern(
        self,
        pattern: str,
        distilled: Optional[str] = None,
        source: Optional[str] = None,
        importance: float = 0.5,
        embedding: Optional[List[float]] = None,
        gated: Optional[bool] = None,
        provenance: Optional[Dict] = None,
        trust_score: Optional[float] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
    ) -> None:
        """Append a new learned pattern dict.

        ADR-0021 fields (provenance / trust_score / valid_from / valid_until)
        are all optional. When omitted, sensible defaults are written so the
        pattern is immediately usable: ``provenance.source_type = "unknown"``,
        ``trust_score = DEFAULT_TRUST``, ``valid_from = distilled``,
        ``valid_until = None`` (current truth). ``last_accessed_at`` /
        ``access_count`` / ``success_count`` / ``failure_count`` start at
        neutral values; strength is computed on read.

        ADR-0026: ``category`` / ``subcategory`` are no longer written.
        Routing is query-time via ``ViewRegistry``; the ``gated`` flag
        preserves the legacy noise gate.
        """
        ts = now_iso()
        distilled_value = distilled or ts
        entry: dict = {
            "pattern": pattern,
            "distilled": distilled_value,
            "importance": importance,
        }
        if source:
            entry["source"] = source
        if embedding is not None:
            entry["embedding"] = embedding
        if gated is not None:
            entry["gated"] = gated

        # ADR-0021: provenance + trust
        entry["provenance"] = provenance or {"source_type": "unknown"}
        entry["trust_score"] = (
            float(trust_score) if trust_score is not None else DEFAULT_TRUST
        )
        entry["trust_updated_at"] = ts

        # ADR-0021: bitemporal
        entry["valid_from"] = valid_from or distilled_value
        entry["valid_until"] = valid_until  # None = current truth

        # ADR-0021: forgetting + feedback (initial neutral state)
        entry["last_accessed_at"] = ts
        entry["access_count"] = 0
        entry["success_count"] = 0
        entry["failure_count"] = 0

        self._learned_patterns.append(entry)

    def get_raw_patterns(self) -> List[dict]:
        """Return a copy of pattern dicts (for analysis/dedup).

        ADR-0026: the ``category`` filter has been retired. Use a
        ``ViewRegistry`` + ``find_by_view`` for semantic routing.
        """
        return list(self._learned_patterns)

    def replace_pattern(self, old_ref: dict, new_pattern: dict) -> bool:
        """Replace a pattern by identity (``is``). Returns True if replaced.

        Used by callers that construct a new dict representing a state
        transition (e.g. bitemporal invalidation) and need to swap it in
        without mutating the existing DTO.
        """
        for i, p in enumerate(self._learned_patterns):
            if p is old_ref:
                self._learned_patterns[i] = new_pattern
                return True
        return False

    def get_learned_patterns(self) -> List[str]:
        """Return a copy of the learned patterns (text only).

        ADR-0026: the ``category`` filter has been retired.
        """
        return [p["pattern"] for p in self._learned_patterns]

    def _filter_since(self, since: str, pool: List[dict]) -> List[dict]:
        """Return dicts from pool distilled after since. Returns all on bad timestamp."""
        try:
            since_dt = datetime.fromisoformat(since)
        except (ValueError, TypeError):
            return list(pool)
        result = []
        for p in pool:
            distilled = p.get("distilled", "")
            if not distilled or distilled == "unknown":
                continue
            try:
                if datetime.fromisoformat(distilled) > since_dt:
                    result.append(p)
            except (ValueError, TypeError):
                continue
        return result

    def get_raw_patterns_since(self, since: str) -> List[dict]:
        """Return raw pattern dicts distilled after the given ISO timestamp."""
        return self._filter_since(since, self._learned_patterns)

    def add_revised_patterns(self, rows: Iterable[dict]) -> None:
        """Append pre-built pattern dicts produced by memory evolution.

        Each ``row`` is expected to already carry the full post-ADR-0021
        shape (provenance, trust_score, valid_from/valid_until,
        last_accessed_at, success/failure counts). Callers — currently
        only ``distill._process_category`` — use this to ingest the
        ``EvolutionBatch.revised_rows`` output of ``apply_revision``
        without reaching into ``_learned_patterns``.
        """
        for row in rows:
            self._learned_patterns.append(dict(row))

    def get_live_patterns(self) -> List[dict]:
        """Return patterns that pass ``is_live`` (bitemporal + trust + strength)."""
        from .forgetting import is_live

        return [p for p in self._learned_patterns if is_live(p)]

    def get_live_patterns_since(self, since: str) -> List[dict]:
        """Return live patterns distilled after the given ISO timestamp."""
        from .forgetting import is_live

        return [
            p for p in self._filter_since(since, self._learned_patterns)
            if is_live(p)
        ]

    def _effective_importance(self, p: dict) -> float:
        return effective_importance(p)

    def load(self) -> None:
        """Load knowledge from JSON file.

        Idempotent: resets ``_learned_patterns`` before parsing so
        repeat calls on the same instance cannot duplicate entries.
        Several commands (e.g. ``insight``) load at both the CLI
        handler and the core function layer; without this reset a
        subsequent ``save()`` would persist the doubled list.

        Validates content against forbidden patterns to detect
        tainted data that may have been injected via compromised
        external content during distillation.

        Also handles legacy Markdown format for migration.
        """
        self._learned_patterns = []
        if self._path is None or not self._path.exists():
            logger.debug("No knowledge file at %s", self._path)
            return
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to read knowledge file: %s", exc)
            return

        # Validate against forbidden patterns
        text_lower = text.lower()
        for pat in FORBIDDEN_SUBSTRING_PATTERNS:
            if pat.lower() in text_lower:
                logger.warning(
                    "Knowledge file contains forbidden pattern: %s — "
                    "file may be tainted, skipping load",
                    pat,
                )
                return

        # Try JSON first, fall back to legacy Markdown
        text_stripped = text.strip()
        if text_stripped.startswith("["):
            self._parse_json(text_stripped)
        else:
            self._parse_legacy_markdown(text)

    def update_view_telemetry(
        self,
        scores_per_pattern: List[Optional[Dict[str, float]]],
        timestamp: str,
        save: bool = True,
    ) -> int:
        """Write ADR-0020 observational telemetry onto pattern records.

        ``scores_per_pattern`` aligns with the internal pattern order; an
        entry of ``None`` skips that pattern (typically because it has no
        embedding). Returns the number of patterns updated.

        These fields are read-only observation — never branch on them
        (see ADR-0020 Consequences).
        """
        if len(scores_per_pattern) != len(self._learned_patterns):
            raise ValueError(
                f"scores length {len(scores_per_pattern)} != patterns {len(self._learned_patterns)}"
            )
        updated = 0
        for p, scores in zip(self._learned_patterns, scores_per_pattern):
            if scores is None:
                continue
            p["last_view_matches"] = scores
            p["last_classified_at"] = timestamp
            updated += 1
        if save and updated > 0:
            self.save()
        return updated

    def save(self) -> None:
        """Persist learned patterns to JSON file using atomic write."""
        if self._path is None:
            logger.debug("No knowledge path configured, skipping save")
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(self._learned_patterns, ensure_ascii=False, indent=2) + "\n"
        tmp_path = self._path.with_suffix(".json.tmp")
        try:
            write_restricted(tmp_path, content)
            os.replace(str(tmp_path), str(self._path))
        except OSError as exc:
            logger.error("Failed to save knowledge file: %s", exc)
            tmp_path.unlink(missing_ok=True)
            raise

    def _parse_json(self, text: str) -> None:
        """Parse JSON array of pattern objects."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse knowledge JSON: %s", exc)
            return
        if not isinstance(data, list):
            logger.warning("Knowledge JSON is not an array")
            return
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("pattern"), str):
                entry: dict = {
                    "pattern": item["pattern"],
                    "distilled": item.get("distilled", "unknown"),
                    "importance": item.get("importance", 0.5),
                }
                if item.get("source") is not None:
                    entry["source"] = item["source"]
                if item.get("last_accessed") is not None:
                    entry["last_accessed"] = item["last_accessed"]
                # ADR-0026: ``category`` / ``subcategory`` are no longer
                # restored on read. If a legacy file is loaded, the
                # field is silently dropped; run ``migrate-categories``
                # to rewrite the file without it.
                if isinstance(item.get("embedding"), list):
                    entry["embedding"] = list(item["embedding"])
                if isinstance(item.get("gated"), bool):
                    entry["gated"] = item["gated"]
                if isinstance(item.get("last_classified_at"), str):
                    entry["last_classified_at"] = item["last_classified_at"]
                if isinstance(item.get("last_view_matches"), dict):
                    entry["last_view_matches"] = dict(item["last_view_matches"])

                # ADR-0021 optional fields. Preserve only if present; the
                # load path does not auto-fill, so legacy files remain
                # legacy until migrate-patterns runs.
                if isinstance(item.get("provenance"), dict):
                    entry["provenance"] = dict(item["provenance"])
                if isinstance(item.get("trust_score"), (int, float)):
                    entry["trust_score"] = float(item["trust_score"])
                if isinstance(item.get("trust_updated_at"), str):
                    entry["trust_updated_at"] = item["trust_updated_at"]
                if isinstance(item.get("valid_from"), str):
                    entry["valid_from"] = item["valid_from"]
                if "valid_until" in item:
                    vu = item["valid_until"]
                    if vu is None or isinstance(vu, str):
                        entry["valid_until"] = vu
                if isinstance(item.get("last_accessed_at"), str):
                    entry["last_accessed_at"] = item["last_accessed_at"]
                if isinstance(item.get("access_count"), int):
                    entry["access_count"] = item["access_count"]
                if isinstance(item.get("success_count"), int):
                    entry["success_count"] = item["success_count"]
                if isinstance(item.get("failure_count"), int):
                    entry["failure_count"] = item["failure_count"]
                self._learned_patterns.append(entry)
            elif isinstance(item, str):
                # Bare string — legacy format
                self._learned_patterns.append({
                    "pattern": item,
                    "distilled": "unknown",
                    "importance": 0.5,
                })

    def _parse_legacy_markdown(self, text: str) -> None:
        """Parse legacy Markdown format (only extracts Learned Patterns)."""
        in_patterns = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                in_patterns = stripped[3:].strip() == "Learned Patterns"
                continue
            if in_patterns and stripped.startswith("- "):
                item = stripped[2:].strip()
                if item:
                    self._learned_patterns.append({
                        "pattern": item,
                        "distilled": "unknown",
                        "importance": 0.5,
                    })
