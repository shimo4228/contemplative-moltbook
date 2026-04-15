"""Sleep-time memory distillation: extract patterns from episode logs.

ADR-0009: dedup is embedding-cosine based; subcategorisation has been
removed (replaced by views, which materialise grouping at query time).
The Step 0 LLM classifier is still used here for ``constitutional`` /
``noise`` / ``uncategorized`` namespacing — replacement with an
embedding centroid gate is commit 5's scope.
"""

from __future__ import annotations

import json as json_mod
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

from ._io import strip_code_fence
from .embeddings import cosine, embed_texts
from .knowledge_store import effective_importance
from .llm import generate, _get_default_system_prompt, get_distill_system_prompt, validate_identity_content
from .memory import EpisodeLog, KnowledgeStore
from .prompts import (
    DISTILL_PROMPT,
    DISTILL_REFINE_PROMPT,
    DISTILL_IMPORTANCE_PROMPT,
    DISTILL_CONSTITUTIONAL_PROMPT,
    IDENTITY_DISTILL_PROMPT,
    IDENTITY_REFINE_PROMPT,
)
from .views import ViewRegistry

logger = logging.getLogger(__name__)

BATCH_SIZE = 30

# Embedding-based dedup thresholds (ADR-0009). Calibrated against
# nomic-embed-text on knowledge.json patterns; tune via dry runs.
SIM_DUPLICATE = 0.92  # near-exact same pattern → SKIP
SIM_UPDATE = 0.80     # similar enough to boost importance → UPDATE

# Episode classify thresholds (ADR-0009). The noise gate is intentionally
# above the constitutional threshold so that ambiguous episodes default to
# uncategorized rather than being incorrectly elevated.
NOISE_THRESHOLD = 0.55
CONSTITUTIONAL_THRESHOLD = 0.55

# JSON Schemas for constrained decoding (Ollama v0.5+ format parameter)
CLASSIFY_SCHEMA: Dict = {
    "type": "string",
    "enum": ["constitutional", "noise", "uncategorized"],
}
IMPORTANCE_SCHEMA: Dict = {
    "type": "object",
    "properties": {"scores": {"type": "array", "items": {"type": "integer"}}},
    "required": ["scores"],
}

def distill(
    days: int = 1,
    dry_run: bool = False,
    episode_log: Optional[EpisodeLog] = None,
    knowledge_store: Optional[KnowledgeStore] = None,
    log_files: Optional[List[Path]] = None,
    view_registry: Optional[ViewRegistry] = None,
) -> str:
    """Distill recent episodes into learned patterns.

    New patterns are embedded inline and dedup uses cosine similarity
    against existing same-category patterns. The legacy LLM-based
    subcategorize step has been removed (ADR-0009); grouping is now
    query-time via views.

    Args:
        days: Number of days of episodes to process.
        dry_run: If True, return results without writing.
        episode_log: EpisodeLog instance (uses default if None).
        knowledge_store: KnowledgeStore instance (uses default if None).
        log_files: Explicit JSONL file paths to process (overrides days).

    Returns:
        The distilled patterns as a string.
    """
    episodes = episode_log or EpisodeLog()
    knowledge = knowledge_store or KnowledgeStore()
    knowledge.load()

    if log_files:
        records: List[Dict] = []
        for path in log_files:
            records.extend(EpisodeLog.read_file(path))
    else:
        records = episodes.read_range(days=days)
    if not records:
        msg = "No episodes found for distillation."
        logger.info(msg)
        return msg

    # Step 0: Classify episodes via embedding centroid distance
    classified = _classify_episodes(records, view_registry=view_registry)
    if classified.noise:
        logger.info("Step 0: %d noise episodes excluded from distillation", len(classified.noise))
    logger.info(
        "Step 0: %d constitutional, %d uncategorized, %d noise",
        len(classified.constitutional), len(classified.uncategorized), len(classified.noise),
    )

    # Determine source date range from records
    timestamps = [r.get("ts", "")[:10] for r in records if r.get("ts")]
    source_date = timestamps[0] if timestamps else None
    if timestamps and timestamps[0] != timestamps[-1]:
        source_date = f"{timestamps[0]}~{timestamps[-1]}"

    all_results: List[str] = []
    total_added = 0
    total_updated = 0

    # Process each category through the 3-step pipeline
    for category, cat_records in [
        ("uncategorized", list(classified.uncategorized)),
        ("constitutional", list(classified.constitutional)),
    ]:
        if not cat_records:
            continue

        cat_results = _distill_category(
            cat_records, knowledge, category, source_date, dry_run,
        )
        all_results.extend(cat_results.results)
        total_added += cat_results.added
        total_updated += cat_results.updated

    if not dry_run and (total_added or total_updated):
        knowledge.save()
        logger.info("Distill complete: %d added, %d updated", total_added, total_updated)

    return "\n\n".join(all_results)


def enrich(
    knowledge_store: KnowledgeStore,
    dry_run: bool = False,
) -> int:
    """No-op since ADR-0009: subcategorisation is now query-time via views.

    Kept as a stable entry point so the ``enrich`` CLI subcommand is
    callable; it now reports zero work and points users at
    ``embed-backfill`` for one-off migration of legacy patterns.
    """
    _ = (knowledge_store, dry_run)
    logger.info(
        "enrich is a no-op since ADR-0009. "
        "Run `embed-backfill` once to add embeddings to existing patterns."
    )
    return 0


@dataclass(frozen=True)
class IdentityResult:
    """Result of a successful identity distillation."""

    text: str
    target_path: Path


def distill_identity(
    knowledge_store: Optional[KnowledgeStore] = None,
    identity_path: Optional[Path] = None,
    view_registry: Optional[ViewRegistry] = None,
) -> Union[str, IdentityResult]:
    """Distill knowledge into an updated identity description.

    Reads the current identity and accumulated knowledge, then asks the LLM
    to write a brief self-description reflecting the agent's actual experience.

    File writing is the caller's responsibility (ADR-0012 approval gate).

    Args:
        knowledge_store: KnowledgeStore instance (uses default if None).
        identity_path: Path to identity.md file.
        view_registry: ViewRegistry used to retrieve self-reflection
            patterns via embedding cosine. Required for ADR-0009 routing;
            patterns lacking embeddings are skipped (run embed-backfill
            first to migrate).

    Returns:
        IdentityResult on success, or error message string.
    """
    knowledge = knowledge_store or KnowledgeStore()
    knowledge.load()

    if view_registry is None:
        msg = (
            "distill_identity requires a ViewRegistry since ADR-0009. "
            "Run embed-backfill once and pass a ViewRegistry instance."
        )
        logger.warning(msg)
        return msg

    # Identity is distilled from self-reflection patterns only. Routing is now
    # done via the "self_reflection" view's embedding cosine, not a discrete
    # subcategory field. Rationale: self-reflection captures internal states;
    # mixing behavioral norms into identity dilutes persona specificity via
    # the Emptiness axiom.
    candidates = [
        p for p in knowledge.get_raw_patterns()
        if p.get("category", "uncategorized") == "uncategorized"
    ]
    matched = view_registry.find_by_view("self_reflection", candidates)
    if not matched:
        msg = "No self-reflection patterns available for identity distillation."
        logger.info(msg)
        return msg
    knowledge_text = "\n".join(f"- {p['pattern']}" for p in matched)

    if not IDENTITY_DISTILL_PROMPT:
        msg = "identity_distill.md prompt template not found."
        logger.warning(msg)
        return msg

    current_identity = ""
    if identity_path and identity_path.exists():
        current_identity = identity_path.read_text(encoding="utf-8").strip()

    prompt = IDENTITY_DISTILL_PROMPT.format(
        current_identity=current_identity or "(no prior identity)",
        knowledge=knowledge_text,
    )

    # Step 1: Free-form self-analysis (rules/axioms for value grounding,
    # but no identity — it's already in the prompt via {current_identity})
    result = generate(prompt, system=get_distill_system_prompt(), num_predict=1500)
    if result is None:
        msg = "LLM failed at step 1 (self-analysis)."
        logger.warning(msg)
        return msg

    # Step 2: Refine into simple persona
    refine_prompt = IDENTITY_REFINE_PROMPT.format(raw_output=result)
    refined = generate(refine_prompt, system=_get_default_system_prompt(), num_predict=1500)
    if refined is None:
        msg = "LLM failed at step 2 (refine). Using step 1 output."
        logger.warning(msg)
        refined = result

    # Clean up: strip empty lines and preamble
    lines = [line.strip() for line in refined.strip().splitlines() if line.strip()]
    identity_text = "\n".join(lines)

    # Validate against forbidden patterns before returning
    if not validate_identity_content(identity_text):
        logger.warning("Generated identity failed validation")
        return identity_text

    if not identity_path:
        return identity_text

    return IdentityResult(text=identity_text, target_path=identity_path)



def _parse_importance_scores(raw: str, expected_count: int) -> List[float]:
    """Parse {"scores": [8, 5, ...]} into [0.8, 0.5, ...].

    Falls back to comma-separated integers, then 0.5 defaults.
    """
    defaults = [0.5] * expected_count
    text = strip_code_fence(raw)

    # Try JSON parse
    scores_raw: list = []
    try:
        parsed = json_mod.loads(text)
        scores_raw = parsed.get("scores", [])
    except (json_mod.JSONDecodeError, TypeError, AttributeError):
        # Fallback: try comma-separated integers (e.g., "8, 5, 9, 7")
        try:
            scores_raw = [int(x.strip()) for x in text.split(",") if x.strip()]
        except ValueError:
            logger.warning("Failed to parse importance scores: %s", text[:200])
            return defaults

    if len(scores_raw) != expected_count:
        logger.warning("Importance count mismatch: got %d, expected %d",
                       len(scores_raw), expected_count)
        return defaults

    result = []
    for s in scores_raw:
        try:
            val = int(s)
        except (ValueError, TypeError):
            val = 5
        result.append(max(1, min(10, val)) / 10.0)
    return result


VALID_CATEGORIES = frozenset({"constitutional", "noise", "uncategorized"})


@dataclass(frozen=True)
class _ClassifiedRecords:
    """Records grouped by classification category."""
    constitutional: Tuple[Dict, ...]
    noise: Tuple[Dict, ...]
    uncategorized: Tuple[Dict, ...]


def _parse_classify_result(raw: Optional[str]) -> str:
    """Parse a classification LLM response.

    Scans the entire response for a valid category keyword.
    Returns one of the VALID_CATEGORIES. Falls back to "uncategorized"
    if no valid category is found.
    """
    if raw is None:
        return "uncategorized"
    text = raw.strip().lower()
    if not text:
        return "uncategorized"
    # Search for valid categories in the response
    for cat in ("constitutional", "noise"):
        if cat in text:
            return cat
    if "uncategorized" in text:
        return "uncategorized"
    logger.warning("No category found in %r, defaulting to uncategorized", raw.strip()[:60])
    return "uncategorized"


def _classify_episodes(
    records: List[Dict],
    view_registry: Optional[ViewRegistry] = None,
) -> _ClassifiedRecords:
    """Step 0: Classify episodes via embedding centroid distance (ADR-0009).

    Each episode summary is bulk-embedded once and compared against the
    ``noise`` and ``constitutional`` view centroids:

      - noise_sim >= NOISE_THRESHOLD                 → noise (skipped)
      - else if const_sim >= CONSTITUTIONAL_THRESHOLD → constitutional
      - else                                          → uncategorized

    A missing view_registry or unavailable centroids degrades safely to
    "all uncategorized" (no LLM fallback). The legacy LLM-per-episode
    classify path has been removed.
    """
    if not records:
        return _ClassifiedRecords(constitutional=(), noise=(), uncategorized=())

    if view_registry is None:
        logger.warning(
            "_classify_episodes called without view_registry — "
            "all episodes will be uncategorized (ADR-0009 requires views)"
        )
        return _ClassifiedRecords(
            constitutional=(), noise=(), uncategorized=tuple(records),
        )

    summaries: List[str] = []
    for r in records:
        record_type = r.get("type", "unknown")
        data = r.get("data", {})
        ts = r.get("ts", "")
        summary = summarize_record(record_type, data)
        episode_line = (
            f"[{ts[:16]}] {record_type}: {summary}"
            if summary
            else f"[{ts[:16]}] {record_type}: (no summary)"
        )
        summaries.append(episode_line)

    embeddings_arr = embed_texts(summaries)
    if embeddings_arr is None or embeddings_arr.shape[0] != len(records):
        logger.warning(
            "Failed to embed %d episodes for classification — defaulting to uncategorized",
            len(records),
        )
        return _ClassifiedRecords(
            constitutional=(), noise=(), uncategorized=tuple(records),
        )

    noise_centroid = view_registry.get_centroid("noise")
    const_centroid = view_registry.get_centroid("constitutional")

    constitutional: List[Dict] = []
    noise: List[Dict] = []
    uncategorized: List[Dict] = []

    for idx, r in enumerate(records):
        emb = embeddings_arr[idx]
        if noise_centroid is not None:
            noise_sim = cosine(emb, noise_centroid)
        else:
            noise_sim = 0.0
        if const_centroid is not None:
            const_sim = cosine(emb, const_centroid)
        else:
            const_sim = 0.0

        if noise_sim >= NOISE_THRESHOLD:
            noise.append(r)
        elif const_sim >= CONSTITUTIONAL_THRESHOLD:
            constitutional.append(r)
        else:
            uncategorized.append(r)

        if (idx + 1) % 50 == 0:
            logger.info("Classified %d/%d episodes", idx + 1, len(records))

    return _ClassifiedRecords(
        constitutional=tuple(constitutional),
        noise=tuple(noise),
        uncategorized=tuple(uncategorized),
    )


@dataclass(frozen=True)
class _CategoryResult:
    """Result of distilling a single category."""
    results: Tuple[str, ...]
    added: int
    updated: int


def _distill_category(
    records: List[Dict],
    knowledge: KnowledgeStore,
    category: str,
    source_date: Optional[str],
    dry_run: bool,
) -> _CategoryResult:
    """Run the 3-step distill pipeline for a single category of records.

    Dedup is performed only against existing patterns of the same category.
    """
    batches = [records[i:i + BATCH_SIZE] for i in range(0, len(records), BATCH_SIZE)]
    logger.info("[%s] Processing %d episodes in %d batches", category, len(records), len(batches))

    all_patterns: List[str] = []
    all_importances: List[float] = []
    all_results: List[str] = []

    for batch_idx, batch in enumerate(batches):
        episode_lines = []
        for r in batch:
            record_type = r.get("type", "unknown")
            data = r.get("data", {})
            ts = r.get("ts", "")
            summary = summarize_record(record_type, data)
            if summary:
                episode_lines.append(f"[{ts[:16]}] {record_type}: {summary}")

        if not episode_lines:
            continue

        step1_prompt = DISTILL_CONSTITUTIONAL_PROMPT if category == "constitutional" else DISTILL_PROMPT
        prompt = step1_prompt.format(
            episodes="\n".join(episode_lines),
        )

        # Step 1: Extract — free-form output, with rules/axioms as lens
        result = generate(prompt, system=get_distill_system_prompt(), num_predict=1500)
        if result is None:
            logger.warning("[%s] Batch %d/%d: step 1 (extract) failed", category, batch_idx + 1, len(batches))
            continue

        # Step 2: Summarize — concise patterns as JSON string array
        refine_prompt = DISTILL_REFINE_PROMPT.format(raw_output=result)
        refined = generate(refine_prompt, num_predict=1500)
        if refined is None:
            logger.warning("[%s] Batch %d/%d: step 2 (summarize) failed, using step 1 output",
                           category, batch_idx + 1, len(batches))
            refined = result

        all_results.append(refined)

        raw_patterns: List[str] = []
        json_text = strip_code_fence(refined)
        try:
            parsed = json_mod.loads(json_text)
            for item in parsed.get("patterns", []):
                text = str(item).strip() if item else ""
                if text:
                    raw_patterns.append(text)
        except (json_mod.JSONDecodeError, TypeError):
            # Fallback: bullet-point parsing
            for line in refined.splitlines():
                line = line.strip()
                if line.startswith("- "):
                    pattern = line[2:].strip()
                    if pattern:
                        raw_patterns.append(pattern)

        # Decision gate: reject low-quality patterns
        batch_patterns = [p for p in raw_patterns if _is_valid_pattern(p)]
        rejected = len(raw_patterns) - len(batch_patterns)

        # Step 3: Evaluate importance — separate LLM call, single task
        batch_importances = [0.5] * len(batch_patterns)
        if batch_patterns and DISTILL_IMPORTANCE_PROMPT:
            patterns_text = "\n".join(f"- {p}" for p in batch_patterns)
            importance_prompt = DISTILL_IMPORTANCE_PROMPT.format(patterns=patterns_text)
            importance_result = generate(importance_prompt, num_predict=1500, format=IMPORTANCE_SCHEMA)
            if importance_result:
                batch_importances = _parse_importance_scores(importance_result, len(batch_patterns))

        all_patterns.extend(batch_patterns)
        all_importances.extend(batch_importances)
        imp_summary = ", ".join(f"{i:.1f}" for i in batch_importances) if batch_importances else "none"
        logger.info(
            "[%s] Batch %d/%d: %d episodes (prompt %d chars) → %d patterns (%d rejected) [importance: %s]",
            category, batch_idx + 1, len(batches), len(batch), len(prompt), len(batch_patterns), rejected,
            imp_summary,
        )

    if not all_patterns:
        return _CategoryResult(results=tuple(all_results), added=0, updated=0)

    # ADR-0009: bulk-embed new patterns inline so dedup can run on cosine
    # similarity instead of SequenceMatcher + LLM gate.
    new_embeddings_arr = embed_texts(all_patterns)
    if new_embeddings_arr is None or new_embeddings_arr.shape[0] != len(all_patterns):
        logger.warning(
            "[%s] Failed to embed %d new patterns; storing without embedding (dedup degraded)",
            category, len(all_patterns),
        )
        new_embeddings: List[Optional[np.ndarray]] = [None] * len(all_patterns)
    else:
        new_embeddings = [new_embeddings_arr[i] for i in range(len(all_patterns))]

    # Dedup within category only: constitutional and uncategorized are independent
    # namespaces. Cross-category overlap is acceptable — the same insight may be
    # relevant both as ethical principle and behavioral pattern.
    existing_same_cat = [
        p for p in knowledge.get_raw_patterns()
        if p.get("category", "uncategorized") == category
    ]
    pre_filter = len(existing_same_cat)
    existing_same_cat = [
        p for p in existing_same_cat
        if effective_importance(p) >= DEDUP_IMPORTANCE_FLOOR
    ]
    if pre_filter > len(existing_same_cat):
        logger.info("[%s] Dedup scope: %d/%d patterns (importance floor %.2f)",
                    category, len(existing_same_cat), pre_filter, DEDUP_IMPORTANCE_FLOOR)

    add_patterns, add_importances, add_embeddings, skipped, updated = _dedup_patterns(
        all_patterns, all_importances, new_embeddings, existing_same_cat,
        mutate_existing=not dry_run,
    )

    if dry_run:
        logger.info(
            "[%s] Dry run — %d patterns found, %d skipped, %d would update existing",
            category, len(all_patterns), skipped, updated,
        )
        return _CategoryResult(results=tuple(all_results), added=0, updated=0)

    if updated:
        logger.info("[%s] Dedup: %d updated (importance boosted)", category, updated)

    for pattern, importance, emb in zip(add_patterns, add_importances, add_embeddings):
        emb_list: Optional[List[float]] = (
            [float(x) for x in emb] if emb is not None else None
        )
        knowledge.add_learned_pattern(
            pattern, source=source_date, importance=importance,
            category=category, embedding=emb_list,
        )
        logger.info("[%s] Added pattern (importance=%.1f): %s",
                     category, importance, pattern[:80])

    return _CategoryResult(results=tuple(all_results), added=len(add_patterns), updated=updated)


DEDUP_IMPORTANCE_FLOOR = 0.05  # Patterns below this effective importance are excluded from dedup


def _dedup_patterns(
    new_patterns: List[str],
    new_importances: List[float],
    new_embeddings: List[Optional[np.ndarray]],
    existing_patterns: List[dict],
    *,
    mutate_existing: bool = True,
) -> Tuple[List[str], List[float], List[Optional[np.ndarray]], int, int]:
    """Remove duplicates by comparing new patterns against existing ones.

    Returns (patterns_to_add, importances_to_add, embeddings_to_add, skip_count, update_count).
    - SKIP: cosine >= SIM_DUPLICATE (near-exact duplicate)
    - UPDATE: cosine >= SIM_UPDATE against existing (boost importance, refresh timestamp)
    - ADD: cosine <  SIM_UPDATE against everything

    Patterns whose embedding is None (Ollama failure) are always ADD'd
    so distillation degrades gracefully when the embed model is down.
    Existing patterns without embeddings are ignored as dedup candidates.
    """
    add_patterns: List[str] = []
    add_importances: List[float] = []
    add_embeddings: List[Optional[np.ndarray]] = []
    skip_count = 0
    update_count = 0

    # Pre-compute existing embeddings (only patterns with embeddings count for dedup)
    existing_with_emb: List[Tuple[Dict, np.ndarray]] = []
    for p in existing_patterns:
        emb = p.get("embedding")
        if isinstance(emb, list):
            existing_with_emb.append((p, np.asarray(emb, dtype=np.float32)))

    for new_text, new_imp, new_emb in zip(new_patterns, new_importances, new_embeddings):
        if new_emb is None:
            add_patterns.append(new_text)
            add_importances.append(new_imp)
            add_embeddings.append(None)
            continue

        # Best similarity vs existing
        best_existing_sim = -1.0
        best_existing_pat: Optional[Dict] = None
        for pat_dict, pat_emb in existing_with_emb:
            sim = cosine(new_emb, pat_emb)
            if sim > best_existing_sim:
                best_existing_sim = sim
                best_existing_pat = pat_dict

        # Best similarity vs already-accepted new patterns (cross-batch)
        best_new_sim = -1.0
        best_new_idx = -1
        for idx, accepted_emb in enumerate(add_embeddings):
            if accepted_emb is None:
                continue
            sim = cosine(new_emb, accepted_emb)
            if sim > best_new_sim:
                best_new_sim = sim
                best_new_idx = idx

        # Decide: SKIP / UPDATE existing / SKIP-NEW (boost in batch) / ADD
        if best_existing_sim >= SIM_DUPLICATE or best_new_sim >= SIM_DUPLICATE:
            skip_count += 1
            logger.debug("SKIP (%.2f): %s", max(best_existing_sim, best_new_sim), new_text[:60])
        elif best_existing_sim >= SIM_UPDATE and best_existing_pat is not None and best_existing_sim >= best_new_sim:
            if mutate_existing:
                old_imp = best_existing_pat.get("importance", 0.5)
                best_existing_pat["importance"] = max(old_imp, new_imp)
                best_existing_pat["distilled"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
            update_count += 1
            logger.debug("UPDATE (%.2f): %s", best_existing_sim, new_text[:60])
        elif best_new_sim >= SIM_UPDATE and best_new_idx >= 0:
            if new_imp > add_importances[best_new_idx]:
                add_importances[best_new_idx] = new_imp
            skip_count += 1
            logger.debug("SKIP-NEW (%.2f): %s", best_new_sim, new_text[:60])
        else:
            add_patterns.append(new_text)
            add_importances.append(new_imp)
            add_embeddings.append(new_emb)

    return add_patterns, add_importances, add_embeddings, skip_count, update_count


def _is_valid_pattern(pattern: str) -> bool:
    """Decision gate: is this pattern worth storing?

    Rejects labels, keywords, and fragments that aren't actionable patterns.
    """
    if len(pattern) < 30:
        return False
    if pattern.count(" ") < 3:
        return False
    return True


def summarize_record(record_type: str, data: dict) -> str:
    """Create a one-line summary of an episode record."""
    if record_type == "interaction":
        direction = data.get("direction", "?")
        agent = data.get("agent_name", "unknown")
        content = data.get("content_summary", "")[:80]
        return f"{direction} with {agent}: {content}"
    elif record_type == "post":
        title = data.get("title", data.get("topic_summary", "untitled"))
        return f"posted: {title}"
    elif record_type == "insight":
        return data.get("observation", "")[:80]
    elif record_type == "activity":
        action = data.get("action", "unknown")
        target = data.get("target_agent", data.get("post_id", ""))
        return f"{action} {target}".strip()
    return ""
