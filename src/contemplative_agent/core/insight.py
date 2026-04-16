"""Insight extraction: synthesize learned patterns into behavioral skills.

Single-pass LLM: extract one skill per view from the top-N most
important patterns matching that view. Cross-view synthesis and
quality control are deferred to skill-stocktake (external).

ADR-0009: views replace the legacy ``subcategory`` field. Patterns are
embedded; views materialise grouping at query time via cosine
similarity to the view's seed text. The ``self_reflection`` view is
excluded here (it is routed to distill_identity); ``noise`` and
``constitutional`` views are also excluded from skill extraction.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Union

from .llm import generate, validate_identity_content
from .episode_log import EpisodeLog
from .memory import KnowledgeStore
from .prompts import INSIGHT_EXTRACTION_PROMPT
from .skill_frontmatter import parse as parse_skill_frontmatter, render as render_skill_frontmatter
from .views import ViewRegistry

logger = logging.getLogger(__name__)

MIN_PATTERNS_REQUIRED = 3
MAX_SLUG_LENGTH = 50
BATCH_SIZE = 10  # top-N per view → 1 skill per view
_FALLBACK_TOPIC = "other"
SELF_REFLECTION_VIEW = "self_reflection"  # routed to distill_identity, excluded from insight
_INSIGHT_EXCLUDED_VIEWS = frozenset({"self_reflection", "noise", "constitutional"})


@dataclass(frozen=True)
class SkillResult:
    """A single generated skill ready for approval."""

    text: str
    filename: str
    target_path: Path


@dataclass(frozen=True)
class InsightResult:
    """Result of a successful insight extraction."""

    skills: Tuple[SkillResult, ...]
    dropped_count: int
    skills_dir: Path


def _slugify(title: str) -> str:
    """Convert a title to a filesystem-safe slug."""
    normalized = unicodedata.normalize("NFKD", title)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug[:MAX_SLUG_LENGTH]


def _extract_title(skill_text: str) -> Optional[str]:
    """Extract title from the first '# ' line in skill text."""
    for line in skill_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _extract_skill(
    patterns: List[str], insights: List[str], topic: str = "mixed"
) -> Optional[str]:
    """Extract one skill from patterns and insights via LLM.

    Returns valid Markdown skill text, or None on failure.
    """
    # The prompt template still uses {subcategory} as variable name for
    # backward compatibility with the .md file; we pass the view name there.
    prompt = INSIGHT_EXTRACTION_PROMPT.format(
        subcategory=topic,
        patterns="\n".join(f"- {p}" for p in patterns),
        insights="\n".join(f"- {i}" for i in insights) if insights else "(none)",
    )

    result = generate(prompt, num_predict=1500)
    if result is None:
        logger.warning("LLM failed to generate skill extraction.")
        return None

    text = result.strip()
    if _extract_title(text) is None:
        logger.warning("Skill has no title, dropping.")
        logger.debug("Raw LLM output (first 300 chars): %.300s", result)
        return None

    return text


def _build_view_batches(
    raw_patterns: List[dict],
    view_registry: ViewRegistry,
    batch_size: int = BATCH_SIZE,
    min_batch_size: int = MIN_PATTERNS_REQUIRED,
) -> List[Tuple[str, List[str]]]:
    """Build one batch per view (excluding self_reflection / noise / constitutional).

    For each view, runs an embedding cosine query against ``raw_patterns``
    and keeps the top-N by importance. Views with fewer than
    ``min_batch_size`` matches are pooled into a "mixed" batch. A pattern
    can match multiple views (multi-membership is intentional under
    ADR-0009); skill-stocktake handles cross-view consolidation.

    Patterns lacking embeddings are silently skipped — run
    ``embed-backfill`` first to migrate them.

    Returns:
        List of (view_name, pattern_texts) tuples.
    """
    batches: List[Tuple[str, List[str]]] = []
    small: List[str] = []

    for view_name in view_registry.names():
        if view_name in _INSIGHT_EXCLUDED_VIEWS:
            continue
        matched = view_registry.find_by_view(view_name, raw_patterns)
        # Re-rank by importance within the view's already-filtered set.
        matched.sort(key=lambda p: p.get("importance", 0.5), reverse=True)
        texts = [p["pattern"] for p in matched[:batch_size]]
        if len(texts) < min_batch_size:
            small.extend(texts)
        else:
            batches.append((view_name, texts))

    # Merge small views into one mixed batch.
    if small:
        if len(small) >= min_batch_size:
            batches.append((_FALLBACK_TOPIC, small[:batch_size]))
        elif batches:
            name, texts = batches[-1]
            batches[-1] = (name, texts + small)

    return batches


def _read_last_insight(skills_dir: Optional[Path]) -> Optional[str]:
    """Read the timestamp of the last insight run."""
    if skills_dir is None:
        return None
    marker = skills_dir / ".last_insight"
    if marker.exists():
        return marker.read_text(encoding="utf-8").strip()
    return None


def _write_last_insight(skills_dir: Path) -> None:
    """Record the current timestamp as the last insight run."""
    skills_dir.mkdir(parents=True, exist_ok=True)
    marker = skills_dir / ".last_insight"
    marker.write_text(
        datetime.now(timezone.utc).isoformat(timespec="minutes") + "\n",
        encoding="utf-8",
    )


def extract_insight(
    knowledge_store: Optional[KnowledgeStore] = None,
    skills_dir: Optional[Path] = None,
    episode_log: Optional[EpisodeLog] = None,
    full: bool = False,
    view_registry: Optional[ViewRegistry] = None,
) -> Union[str, InsightResult]:
    """Extract behavioral skills from accumulated knowledge.

    Single-pass per batch: extract skill, validate, return.
    File writing is the caller's responsibility (ADR-0012 approval gate).
    Quality control is deferred to skill-stocktake.

    By default, only processes patterns added since the last insight run.
    Use full=True to process all patterns.

    Args:
        knowledge_store: KnowledgeStore with learned patterns.
        skills_dir: Directory for skill files (used for incremental tracking).
        episode_log: EpisodeLog for reading recent insights.
        full: If True, process all patterns instead of only new ones.
        view_registry: ViewRegistry used to (a) filter out self-reflection
            patterns (routed to distill_identity) and (b) build per-view
            batches via embedding cosine. Required since ADR-0009.

    Returns:
        InsightResult on success, or error message string.
    """
    if knowledge_store is None:
        return "No knowledge store provided."
    if view_registry is None:
        return (
            "extract_insight requires a ViewRegistry since ADR-0009. "
            "Run embed-backfill once and pass a ViewRegistry instance."
        )

    knowledge_store.load()

    if full:
        raw_patterns = knowledge_store.get_raw_patterns(category="uncategorized")
    else:
        last_run = _read_last_insight(skills_dir)
        if last_run:
            raw_patterns = knowledge_store.get_raw_patterns_since(last_run, category="uncategorized")
            logger.info("Incremental mode: %d new patterns since %s", len(raw_patterns), last_run)
        else:
            raw_patterns = knowledge_store.get_raw_patterns(category="uncategorized")
            logger.info("No previous insight run found, processing all %d patterns", len(raw_patterns))

    # self-reflection patterns are routed to distill_identity, not skill extraction.
    # Routing is now done via the self_reflection view's embedding cosine.
    self_reflection_matched = view_registry.find_by_view(SELF_REFLECTION_VIEW, raw_patterns)
    self_reflection_ids = {id(p) for p in self_reflection_matched}
    raw_patterns = [p for p in raw_patterns if id(p) not in self_reflection_ids]

    insights: List[str] = []
    if episode_log is not None:
        insight_records = episode_log.read_range(days=30, record_type="insight")
        insights = [
            r.get("data", {}).get("observation", "")
            for r in insight_records[-10:]
            if r.get("data", {}).get("observation")
        ]

    if len(raw_patterns) < MIN_PATTERNS_REQUIRED:
        return (
            f"Insufficient patterns ({len(raw_patterns)}/{MIN_PATTERNS_REQUIRED}). "
            f"Run more sessions and distill first."
        )

    batches = _build_view_batches(raw_patterns, view_registry)

    logger.info(
        "Processing %d patterns in %d batches (per-view)",
        len(raw_patterns), len(batches),
    )

    skill_results: List[SkillResult] = []
    dropped_count = 0

    today = date.today().strftime("%Y%m%d")

    for batch_idx, (topic, batch) in enumerate(batches):
        logger.info(
            "Batch %d/%d [%s]: %d patterns",
            batch_idx + 1, len(batches), topic, len(batch),
        )

        skill_text = _extract_skill(batch, insights, topic=topic)
        if skill_text is None:
            logger.warning(
                "Batch %d/%d [%s]: extraction failed",
                batch_idx + 1, len(batches), topic,
            )
            dropped_count += 1
            continue

        if not validate_identity_content(skill_text):
            logger.warning(
                "Batch %d/%d [%s]: forbidden pattern detected",
                batch_idx + 1, len(batches), topic,
            )
            dropped_count += 1
            continue

        title = _extract_title(skill_text) or ""
        slug = _slugify(title)
        if not slug:
            logger.warning(
                "Batch %d/%d [%s]: empty slug, dropping",
                batch_idx + 1, len(batches), topic,
            )
            dropped_count += 1
            continue

        filename = f"{slug}-{today}.md"

        if skills_dir is not None:
            file_path = skills_dir / filename
            if not file_path.resolve().is_relative_to(skills_dir.resolve()):
                logger.error("Skill path escape attempt: %s", file_path)
                dropped_count += 1
                continue
        else:
            file_path = Path(filename)

        # Merge ADR-0023 router fields into the LLM's legacy frontmatter block
        # (stacking two blocks leaks legacy metadata into the router's body embed).
        existing_meta, body = parse_skill_frontmatter(skill_text)
        rendered = render_skill_frontmatter(existing_meta, body)
        skill_results.append(SkillResult(
            text=rendered,
            filename=filename,
            target_path=file_path,
        ))

    if not skill_results:
        return "Failed to extract skill from knowledge."

    return InsightResult(
        skills=tuple(skill_results),
        dropped_count=dropped_count,
        skills_dir=skills_dir or Path("."),
    )
