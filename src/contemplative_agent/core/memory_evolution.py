"""Memory evolution — revise neighbor pattern interpretations when a related
new pattern arrives (ADR-0022, IV-4).

Philosophy: a pattern's *meaning* is not static; it is a function of what
has arrived since it was written. When a topically-related new pattern
lands (below dedup threshold but above pure-distance noise), the older
pattern's ``distilled`` text is rewritten via LLM to reflect the new
context. Consistent with ADR-0021 bitemporal semantics, the old row is
soft-invalidated and a revised copy is added as a new row.

Reference: A-Mem (arXiv:2502.12110) — Zettelkasten-style dynamic linking +
memory evolution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from .embeddings import cosine
from .llm import generate

logger = logging.getLogger(__name__)

# Evolution similarity zone. Below SIM_UPDATE=0.80 (dedup territory) and
# above a lower bound that keeps us out of the "topically unrelated" range.
EVOLUTION_MIN = 0.65
EVOLUTION_MAX_EXCL = 0.80  # half-open: neighbors at >= 0.80 are dedup's job

# Per-new-pattern cap on neighbors to revise. Bounds worst-case cost to
# K × new_patterns LLM calls per distill run.
EVOLUTION_K = 3

# Marker the LLM can emit to signal "no revision needed".
NO_CHANGE_MARKER = "NO_CHANGE"


@dataclass(frozen=True)
class EvolutionPair:
    """One (new pattern, neighbor) pairing produced by ``find_neighbors``."""

    new_text: str
    new_emb: np.ndarray
    neighbor: Dict
    similarity: float


@dataclass(frozen=True)
class EvolutionResult:
    """Revision produced for a single neighbor.

    ``revised_distilled`` is None when the LLM signalled NO_CHANGE or
    produced unusable output; callers treat None as "skip this neighbor".
    """

    neighbor: Dict
    revised_distilled: Optional[str]
    similarity: float


def find_neighbors(
    new_text: str,
    new_emb: np.ndarray,
    live_patterns: List[Dict],
    *,
    min_sim: float = EVOLUTION_MIN,
    max_sim_excl: float = EVOLUTION_MAX_EXCL,
    k: int = EVOLUTION_K,
) -> List[EvolutionPair]:
    """Return top-k live neighbors of ``new_emb`` in [min_sim, max_sim_excl).

    ``live_patterns`` should already have ``valid_until is None`` filtered
    by the caller (keeps this function side-effect-free). Patterns without
    an ``embedding`` field are ignored.
    """
    candidates: List[EvolutionPair] = []
    for p in live_patterns:
        emb = p.get("embedding")
        if not isinstance(emb, list):
            continue
        vec = np.asarray(emb, dtype=np.float32)
        sim = float(cosine(new_emb, vec))
        if min_sim <= sim < max_sim_excl:
            candidates.append(EvolutionPair(
                new_text=new_text,
                new_emb=new_emb,
                neighbor=p,
                similarity=sim,
            ))
    candidates.sort(key=lambda c: c.similarity, reverse=True)
    return candidates[:k]


def _parse_revision(raw: Optional[str]) -> Optional[str]:
    """Clean LLM output. Returns None on NO_CHANGE / empty / obvious garbage."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if NO_CHANGE_MARKER in text.upper().split():
        return None
    # A bare NO_CHANGE with surrounding quotes or punctuation
    if text.upper().replace(".", "").replace('"', "").strip() == NO_CHANGE_MARKER:
        return None
    # Guard against the LLM echoing the prompt template or refusing
    if len(text) < 10:
        return None
    return text


def revise_neighbor(
    pair: EvolutionPair,
    prompt_template: str,
    *,
    generate_fn: Callable[..., Optional[str]] = generate,
    num_predict: int = 500,
) -> EvolutionResult:
    """Invoke the LLM once to produce a revised distilled text for ``pair``.

    ``prompt_template`` is expected to contain ``{neighbor}`` and
    ``{new_pattern}`` placeholders (see config/prompts/memory_evolution.md).
    ``generate_fn`` is injectable for tests.
    """
    neighbor_text = pair.neighbor.get("distilled") or pair.neighbor.get("pattern", "")
    prompt = prompt_template.format(
        neighbor=neighbor_text,
        new_pattern=pair.new_text,
    )
    raw = generate_fn(prompt, num_predict=num_predict)
    revised = _parse_revision(raw)
    return EvolutionResult(
        neighbor=pair.neighbor,
        revised_distilled=revised,
        similarity=pair.similarity,
    )


def apply_revision(
    result: EvolutionResult,
    *,
    now: Optional[datetime] = None,
) -> Optional[Dict]:
    """Soft-invalidate the neighbor and produce the revised pattern dict.

    Returns the new pattern row to be appended to the knowledge store, or
    None if the result has no revision. The caller is responsible for
    appending the returned row (this function does not touch KnowledgeStore
    to keep it unit-testable without a store instance).
    """
    if result.revised_distilled is None:
        return None
    neighbor = result.neighbor
    now_iso = (now or datetime.now(timezone.utc)).isoformat(timespec="minutes")

    # Soft-invalidate the original
    neighbor["valid_until"] = now_iso

    # Build the revised row. Preserve the semantic coordinate (embedding),
    # content identity (pattern), and operational metadata (importance,
    # category, source/episodes). Bump provenance to "mixed" to reflect
    # that the interpretation now carries context from a later observation.
    old_prov = dict(neighbor.get("provenance") or {"source_type": "unknown"})
    new_prov = {
        "source_type": "mixed",
        "source_episode_ids": old_prov.get("source_episode_ids", []),
        "sanitized": bool(old_prov.get("sanitized", True)),
        "pipeline_version": "memory_evolution@0.22",
        "derived_from": old_prov.get("pipeline_version", "unknown"),
        "evolution_similarity": round(result.similarity, 3),
    }
    revised: Dict = {
        "pattern": neighbor.get("pattern", ""),
        "distilled": result.revised_distilled,
        "importance": float(neighbor.get("importance", 0.5)),
        "category": neighbor.get("category", "uncategorized"),
        "embedding": list(neighbor.get("embedding") or []),
        "gated": bool(neighbor.get("gated", False)),
        "provenance": new_prov,
        "trust_score": float(neighbor.get("trust_score", 0.6)),
        "trust_updated_at": now_iso,
        "valid_from": now_iso,
        "valid_until": None,
        "last_accessed_at": now_iso,
        "access_count": 0,
        "success_count": 0,
        "failure_count": 0,
    }
    return revised


def evolve_patterns(
    new_entries: List[Tuple[str, np.ndarray]],
    live_patterns: List[Dict],
    prompt_template: str,
    *,
    generate_fn: Callable[..., Optional[str]] = generate,
    now: Optional[datetime] = None,
    min_sim: float = EVOLUTION_MIN,
    max_sim_excl: float = EVOLUTION_MAX_EXCL,
    k: int = EVOLUTION_K,
) -> List[Dict]:
    """End-to-end evolution for a batch of new patterns.

    Mutates ``live_patterns`` entries in place (sets ``valid_until``) and
    returns the list of newly-created revised rows for the caller to
    persist. Safe to call with an empty ``prompt_template`` — evolution
    is skipped and a warning logged.

    Each neighbor is revised at most once per call even if multiple new
    patterns would target it; the first (highest-sim) wins.
    """
    if not prompt_template:
        logger.warning("memory_evolution.md not loaded — skipping evolution step")
        return []
    if not new_entries or not live_patterns:
        return []

    revised_rows: List[Dict] = []
    already_revised: set = set()
    for new_text, new_emb in new_entries:
        pairs = find_neighbors(
            new_text, new_emb, live_patterns,
            min_sim=min_sim, max_sim_excl=max_sim_excl, k=k,
        )
        for pair in pairs:
            key = id(pair.neighbor)
            if key in already_revised:
                continue
            # Skip neighbors already invalidated mid-loop by a prior revision
            if pair.neighbor.get("valid_until") is not None:
                already_revised.add(key)
                continue
            result = revise_neighbor(pair, prompt_template, generate_fn=generate_fn)
            if result.revised_distilled is None:
                already_revised.add(key)
                continue
            new_row = apply_revision(result, now=now)
            if new_row is not None:
                revised_rows.append(new_row)
                already_revised.add(key)
                logger.info(
                    "Evolution: revised neighbor (sim=%.2f) in light of new pattern",
                    pair.similarity,
                )
    return revised_rows
