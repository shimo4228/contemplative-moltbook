"""Insight extraction: synthesize learned patterns into behavioral skills.

Single-pass LLM: extract a skill from each batch of knowledge patterns.
Quality control is deferred to skill-stocktake (external).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import defaultdict
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
_FALLBACK_SUBCATEGORY = "other"
_FALLBACK_RARITY = 5.0


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


_SKILL_SEPARATOR = "---SKILL---"


def _extract_skills(
    patterns: List[str], insights: List[str], subcategory: str = "mixed"
) -> List[str]:
    """Extract one or more skills from patterns and insights via LLM.

    The LLM decides how many skills the patterns naturally support.
    Returns a list of valid Markdown skill texts (may be empty on failure).
    """
    prompt = INSIGHT_EXTRACTION_PROMPT.format(
        subcategory=subcategory,
        patterns="\n".join(f"- {p}" for p in patterns),
        insights="\n".join(f"- {i}" for i in insights) if insights else "(none)",
    )

    result = generate(prompt, max_length=8000)
    if result is None:
        logger.warning("LLM failed to generate skill extraction.")
        return []

    raw_skills = result.split(_SKILL_SEPARATOR)
    valid: List[str] = []
    for raw in raw_skills:
        text = raw.strip()
        if not text:
            continue
        if _extract_title(text) is None:
            logger.debug("Skill chunk has no title, dropping: %.100s", text)
            continue
        valid.append(text)

    if not valid:
        logger.warning("No valid skills extracted from LLM output.")
        logger.debug("Raw LLM output (first 300 chars): %.300s", result)

    return valid


def _build_subcategory_batches(
    raw_patterns: List[dict],
    batch_size: int = BATCH_SIZE,
    min_batch_size: int = MIN_PATTERNS_REQUIRED,
) -> List[Tuple[str, List[str]]]:
    """Build one batch per subcategory, prioritizing high rarity within each.

    Each batch contains patterns from a single subcategory so the LLM can
    synthesize a focused, thematically coherent skill. Cross-category synthesis
    is deferred to skill-stocktake.

    Within each subcategory, patterns are sorted by rarity descending and
    capped at batch_size. Subcategories with fewer than min_batch_size
    patterns are merged into a single "mixed" batch.

    Falls back gracefully when subcategory/rarity are missing (enrich not run):
    all patterns land in "other" group.

    Returns:
        List of (subcategory_name, pattern_texts) tuples.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for p in raw_patterns:
        sub = p.get("subcategory", _FALLBACK_SUBCATEGORY) or _FALLBACK_SUBCATEGORY
        groups[sub].append(p)

    batches: List[Tuple[str, List[str]]] = []
    small: List[str] = []

    for key in sorted(groups.keys()):
        group = groups[key]
        group.sort(key=lambda pat: pat.get("rarity", _FALLBACK_RARITY), reverse=True)
        texts = [p["pattern"] for p in group[:batch_size]]
        if len(texts) < min_batch_size:
            small.extend(texts)
        else:
            batches.append((key, texts))

    # Merge small subcategories into one mixed batch
    if small:
        if len(small) >= min_batch_size:
            batches.append(("mixed", small))
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
        raw_patterns = knowledge_store.get_raw_patterns(category="uncategorized")
    else:
        last_run = _read_last_insight(skills_dir)
        if last_run:
            raw_patterns = knowledge_store.get_raw_patterns_since(last_run, category="uncategorized")
            logger.info("Incremental mode: %d new patterns since %s", len(raw_patterns), last_run)
        else:
            raw_patterns = knowledge_store.get_raw_patterns(category="uncategorized")
            logger.info("No previous insight run found, processing all %d patterns", len(raw_patterns))

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

    batches = _build_subcategory_batches(raw_patterns)

    logger.info(
        "Processing %d patterns in %d batches (stratified)",
        len(raw_patterns), len(batches),
    )

    skill_results: List[SkillResult] = []
    dropped_count = 0

    today = date.today().strftime("%Y%m%d")

    for batch_idx, (subcategory, batch) in enumerate(batches):
        logger.info(
            "Batch %d/%d [%s]: %d patterns",
            batch_idx + 1, len(batches), subcategory, len(batch),
        )

        skill_texts = _extract_skills(batch, insights, subcategory=subcategory)
        if not skill_texts:
            logger.warning("Batch %d/%d: extraction failed", batch_idx + 1, len(batches))
            dropped_count += 1
            continue

        for skill_text in skill_texts:
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
