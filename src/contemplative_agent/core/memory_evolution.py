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
) -> Optional[Tuple[Dict, Dict]]:
    """Produce (invalidated_neighbor, revised_new_row) from a revision result.

    Returns None if the result has no revision. Both returned dicts are
    fresh — the input ``neighbor`` is not mutated. The caller is
    responsible for swapping the original neighbor for
    ``invalidated_neighbor`` and appending ``revised_new_row``.
    """
    if result.revised_distilled is None:
        return None
    neighbor = result.neighbor
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="minutes")

    # Soft-invalidated copy (original left untouched)
    invalidated: Dict = {**neighbor, "valid_until": ts}

    # Build the revised row. Preserve the semantic coordinate (embedding),
    # content identity (pattern), and operational metadata (importance,
    # source/episodes). Bump provenance to "mixed" to reflect that the
    # interpretation now carries context from a later observation.
    # ADR-0026: ``category`` is no longer propagated — routing is via
    # ``ViewRegistry`` at query time.
    old_prov = dict(neighbor.get("provenance") or {"source_type": "unknown"})
    new_prov = {
        "source_type": "mixed",
        "source_episode_ids": old_prov.get("source_episode_ids", []),
        "pipeline_version": "memory_evolution@0.26",
        "derived_from": old_prov.get("pipeline_version", "unknown"),
        "evolution_similarity": round(result.similarity, 3),
    }
    revised: Dict = {
        "pattern": neighbor.get("pattern", ""),
        "distilled": result.revised_distilled,
        "importance": float(neighbor.get("importance", 0.5)),
        "embedding": list(neighbor.get("embedding") or []),
        "gated": bool(neighbor.get("gated", False)),
        "provenance": new_prov,
        "trust_score": float(neighbor.get("trust_score", 0.6)),
        "trust_updated_at": ts,
        "valid_from": ts,
        "valid_until": None,
    }
    return invalidated, revised


@dataclass(frozen=True)
class EvolutionBatch:
    """Outcome of an end-to-end evolution run.

    ``invalidations`` pairs each original neighbor (identity reference)
    with a fresh dict carrying the new ``valid_until``. Callers apply
    them via ``KnowledgeStore.replace_pattern``.
    """

    invalidations: Tuple[Tuple[Dict, Dict], ...]
    revised_rows: Tuple[Dict, ...]


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
) -> EvolutionBatch:
    """End-to-end evolution for a batch of new patterns.

    Returns an ``EvolutionBatch`` describing per-neighbor invalidations
    and new revised rows. Does not mutate ``live_patterns`` entries —
    callers must ``KnowledgeStore.replace_pattern(old, new)`` for each
    invalidation and extend their store with ``revised_rows``.

    Each neighbor is revised at most once per call even if multiple new
    patterns would target it; the first (highest-sim) wins.
    """
    empty = EvolutionBatch(invalidations=(), revised_rows=())
    if not prompt_template:
        logger.warning("memory_evolution.md not loaded — skipping evolution step")
        return empty
    if not new_entries or not live_patterns:
        return empty

    invalidations: List[Tuple[Dict, Dict]] = []
    revised_rows: List[Dict] = []
    already_processed: set = set()
    for new_text, new_emb in new_entries:
        pairs = find_neighbors(
            new_text, new_emb, live_patterns,
            min_sim=min_sim, max_sim_excl=max_sim_excl, k=k,
        )
        for pair in pairs:
            key = id(pair.neighbor)
            if key in already_processed:
                continue
            # Skip neighbors that were already invalidated before this call
            if pair.neighbor.get("valid_until") is not None:
                already_processed.add(key)
                continue
            result = revise_neighbor(pair, prompt_template, generate_fn=generate_fn)
            if result.revised_distilled is None:
                already_processed.add(key)
                continue
            outcome = apply_revision(result, now=now)
            if outcome is not None:
                invalidated, revised_row = outcome
                invalidations.append((pair.neighbor, invalidated))
                revised_rows.append(revised_row)
                already_processed.add(key)
                logger.info(
                    "Evolution: revised neighbor (sim=%.2f) in light of new pattern",
                    pair.similarity,
                )
    return EvolutionBatch(
        invalidations=tuple(invalidations),
        revised_rows=tuple(revised_rows),
    )
