"""Skill reflection: revise skills based on usage outcomes (ADR-0023).

For each skill whose recent failure rate clears the reflection threshold
(``needs_reflection``), rewrite the body in light of the contexts where
it failed. The LLM returns ``NO_CHANGE`` when failures do not reveal a
meaningful problem with the skill itself.

File writing is the caller's responsibility (ADR-0012 approval gate);
this module only returns a frozen ``ReflectResult`` — same shape as
``insight.InsightResult`` so the CLI can reuse ``_stage_results`` /
``_approve_write`` without an adapter layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union

from .insight import SkillResult
from .llm import generate, validate_identity_content
from .prompts import SKILL_REFLECT_PROMPT
from .skill_frontmatter import (
    parse as parse_skill_frontmatter,
    render as render_skill_frontmatter,
    update_meta,
)
from .skill_router import (
    DEFAULT_USAGE_WINDOW_DAYS,
    SkillRouter,
    aggregate_usage,
    needs_reflection,
)

logger = logging.getLogger(__name__)

_NO_CHANGE = "NO_CHANGE"


@dataclass(frozen=True)
class ReflectResult:
    """Result of a skill-reflect run ready for the approval gate."""

    skills: Tuple[SkillResult, ...]
    eligible: int
    no_change_count: int
    skills_dir: Path


def reflect_skills(
    skills_dir: Path,
    skill_router: SkillRouter,
    *,
    days: int = DEFAULT_USAGE_WINDOW_DAYS,
    generate_fn: Optional[Callable[..., Optional[str]]] = None,
) -> Union[str, ReflectResult]:
    """Revise skills that recently accumulated enough failures.

    Returns an error-message string when the usage window turns up no
    eligible skills, or when every LLM attempt fails. Otherwise returns
    ``ReflectResult`` whose ``skills`` carry the revised body plus an
    updated ``last_reflected_at`` frontmatter field (used by ``select``
    as a tie-breaker).
    """
    gen = generate_fn or generate

    records = skill_router.load_usage(days=days)
    stats_by_name = aggregate_usage(records)
    eligible = [s for s in stats_by_name.values() if needs_reflection(s)]
    if not eligible:
        return (
            f"No skills need reflection over the last {days} days "
            f"(examined {len(stats_by_name)} skills)."
        )

    now_iso = datetime.now(timezone.utc).isoformat(timespec="minutes")
    revised: List[SkillResult] = []
    no_change_count = 0

    for stats in eligible:
        path = skills_dir / stats.name
        if not path.is_file():
            logger.warning("Eligible skill file missing: %s", path)
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to read skill %s: %s", path, exc)
            continue
        meta, body = parse_skill_frontmatter(text)
        if not body.strip():
            continue

        prompt = SKILL_REFLECT_PROMPT.format(
            skill_body=body,
            success_count=stats.successes,
            failure_count=stats.failures,
            failure_contexts=(
                "\n".join(f"- {c}" for c in stats.failure_contexts)
                or "(none)"
            ),
        )
        output = gen(prompt, num_predict=1500)
        if output is None:
            logger.warning("LLM failed to revise skill %s.", stats.name)
            continue
        trimmed = output.strip()
        if trimmed == _NO_CHANGE:
            no_change_count += 1
            continue
        if not validate_identity_content(trimmed):
            logger.warning("Revised skill %s rejected by validator.", stats.name)
            continue

        new_meta = update_meta(meta, last_reflected_at=now_iso)
        rendered = render_skill_frontmatter(new_meta, trimmed)
        revised.append(SkillResult(
            text=rendered,
            filename=stats.name,
            target_path=path,
        ))

    if not revised and no_change_count == 0:
        return "Reflection produced no revisions (all LLM calls failed or filtered)."

    return ReflectResult(
        skills=tuple(revised),
        eligible=len(eligible),
        no_change_count=no_change_count,
        skills_dir=skills_dir,
    )
