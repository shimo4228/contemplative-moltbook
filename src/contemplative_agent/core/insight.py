"""Insight extraction: synthesize learned patterns into behavioral skills.

Single-pass LLM: extract a skill from each batch of knowledge patterns.
Quality control is deferred to skill-stocktake (external).
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

logger = logging.getLogger(__name__)

MIN_PATTERNS_REQUIRED = 3
MAX_SLUG_LENGTH = 50
BATCH_SIZE = 30


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
    patterns: List[str], insights: List[str]
) -> Optional[str]:
    """Extract a skill from patterns and insights via LLM.

    Returns the raw Markdown skill text, or None on failure.
    """
    prompt = INSIGHT_EXTRACTION_PROMPT.format(
        patterns="\n".join(f"- {p}" for p in patterns),
        insights="\n".join(f"- {i}" for i in insights) if insights else "(none)",
    )

    result = generate(prompt, max_length=3000)
    if result is None:
        logger.warning("LLM failed to generate skill extraction.")
        return None

    if _extract_title(result) is None:
        logger.warning("Skill extraction has no title (# line). Dropping.")
        logger.debug("Raw LLM output (first 200 chars): %.200s", result)
        return None

    return result


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

    Returns:
        InsightResult on success, or error message string.
    """
    if knowledge_store is None:
        return "No knowledge store provided."

    knowledge_store.load()

    if full:
        patterns: List[str] = list(knowledge_store.get_learned_patterns(category="uncategorized"))
    else:
        last_run = _read_last_insight(skills_dir)
        if last_run:
            patterns = list(knowledge_store.get_learned_patterns_since(last_run, category="uncategorized"))
            logger.info("Incremental mode: %d new patterns since %s", len(patterns), last_run)
        else:
            patterns = list(knowledge_store.get_learned_patterns(category="uncategorized"))
            logger.info("No previous insight run found, processing all %d patterns", len(patterns))

    insights: List[str] = []
    if episode_log is not None:
        insight_records = episode_log.read_range(days=30, record_type="insight")
        insights = [
            r.get("data", {}).get("observation", "")
            for r in insight_records[-10:]
            if r.get("data", {}).get("observation")
        ]

    if len(patterns) < MIN_PATTERNS_REQUIRED:
        return (
            f"Insufficient patterns ({len(patterns)}/{MIN_PATTERNS_REQUIRED}). "
            f"Run more sessions and distill first."
        )

    batches = [
        patterns[i : i + BATCH_SIZE]
        for i in range(0, len(patterns), BATCH_SIZE)
    ]
    if len(batches) > 1 and len(batches[-1]) < MIN_PATTERNS_REQUIRED:
        batches[-2].extend(batches[-1])
        batches.pop()

    logger.info(
        "Processing %d patterns in %d batches", len(patterns), len(batches)
    )

    skill_results: List[SkillResult] = []
    dropped_count = 0

    for batch_idx, batch in enumerate(batches):
        logger.info(
            "Batch %d/%d: %d patterns", batch_idx + 1, len(batches), len(batch)
        )

        skill_text = _extract_skill(batch, insights)
        if skill_text is None:
            logger.warning("Batch %d/%d: extraction failed", batch_idx + 1, len(batches))
            dropped_count += 1
            continue

        if not validate_identity_content(skill_text):
            logger.warning("Batch %d/%d: forbidden pattern detected", batch_idx + 1, len(batches))
            dropped_count += 1
            continue

        title = _extract_title(skill_text) or ""
        slug = _slugify(title)
        if not slug:
            logger.warning("Batch %d/%d: empty slug, dropping", batch_idx + 1, len(batches))
            dropped_count += 1
            continue

        today = date.today().strftime("%Y%m%d")
        filename = f"{slug}-{today}.md"

        if skills_dir is not None:
            file_path = skills_dir / filename
            if not file_path.resolve().is_relative_to(skills_dir.resolve()):
                logger.error("Skill path escape attempt: %s", file_path)
                dropped_count += 1
                continue
        else:
            file_path = Path(filename)

        skill_results.append(SkillResult(
            text=skill_text,
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
