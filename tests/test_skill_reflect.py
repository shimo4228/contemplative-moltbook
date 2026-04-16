"""Tests for core.skill_reflect — revise skills from usage outcomes (ADR-0023)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from contemplative_agent.core.skill_frontmatter import parse as parse_skill
from contemplative_agent.core.skill_reflect import ReflectResult, reflect_skills


REVISED_BODY = (
    "# Ask Before Reacting\n"
    "\n"
    "**Context:** When encountering unfamiliar viewpoints\n"
    "\n"
    "## Solution\n"
    "Narrow: ask one clarifying question, then respond.\n"
)

ORIGINAL_SKILL = (
    "---\n"
    "last_reflected_at: null\n"
    "success_count: 0\n"
    "failure_count: 0\n"
    "name: ask-before-reacting\n"
    "---\n"
    "\n"
    "# Ask Before Reacting\n"
    "\n"
    "## Solution\n"
    "Ask clarifying questions before forming a response.\n"
)


def _failure_records(skill_name: str, failures: int, successes: int = 0) -> List[Dict[str, Any]]:
    """Build selection+outcome records for one skill at a given failure rate."""
    out: List[Dict[str, Any]] = []
    for i in range(failures):
        action_id = f"fail-{i}"
        out.append({
            "type": "selection",
            "action_id": action_id,
            "selected": [skill_name],
            "context_excerpt": f"context-fail-{i}",
        })
        out.append({
            "type": "outcome",
            "action_id": action_id,
            "outcome": "failure",
            "note": "test",
        })
    for i in range(successes):
        action_id = f"ok-{i}"
        out.append({
            "type": "selection",
            "action_id": action_id,
            "selected": [skill_name],
            "context_excerpt": f"context-ok-{i}",
        })
        out.append({
            "type": "outcome",
            "action_id": action_id,
            "outcome": "success",
        })
    return out


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    d = tmp_path / "skills"
    d.mkdir()
    (d / "ask-before-reacting.md").write_text(ORIGINAL_SKILL, encoding="utf-8")
    return d


@pytest.fixture
def router() -> MagicMock:
    r = MagicMock()
    r.load_usage.return_value = []
    return r


class TestReflectSkills:
    def test_no_eligible_returns_message(self, skills_dir: Path, router: MagicMock) -> None:
        router.load_usage.return_value = _failure_records("ask-before-reacting.md", failures=1, successes=5)
        result = reflect_skills(skills_dir, router, generate_fn=lambda *a, **kw: "should not be called")
        assert isinstance(result, str)
        assert "No skills need reflection" in result

    def test_no_change_output_is_counted(self, skills_dir: Path, router: MagicMock) -> None:
        router.load_usage.return_value = _failure_records("ask-before-reacting.md", failures=3, successes=1)
        result = reflect_skills(skills_dir, router, generate_fn=lambda *a, **kw: "NO_CHANGE")
        assert isinstance(result, ReflectResult)
        assert result.eligible == 1
        assert result.no_change_count == 1
        assert result.skills == ()

    def test_revised_skill_updates_last_reflected_at(
        self, skills_dir: Path, router: MagicMock,
    ) -> None:
        router.load_usage.return_value = _failure_records("ask-before-reacting.md", failures=3, successes=1)
        result = reflect_skills(skills_dir, router, generate_fn=lambda *a, **kw: REVISED_BODY)
        assert isinstance(result, ReflectResult)
        assert len(result.skills) == 1
        revised = result.skills[0]
        assert revised.filename == "ask-before-reacting.md"
        assert revised.target_path == skills_dir / "ask-before-reacting.md"

        meta, body = parse_skill(revised.text)
        assert meta.last_reflected_at is not None
        assert meta.last_reflected_at.startswith("20")  # ISO year
        # Router frontmatter fields preserved
        assert meta.success_count == 0
        assert meta.failure_count == 0
        # Legacy metadata from the original skill survives via extra
        assert meta.extra.get("name") == "ask-before-reacting"
        assert body.lstrip().startswith("# Ask Before Reacting")

    def test_llm_none_is_skipped(self, skills_dir: Path, router: MagicMock) -> None:
        router.load_usage.return_value = _failure_records("ask-before-reacting.md", failures=3, successes=1)
        result = reflect_skills(skills_dir, router, generate_fn=lambda *a, **kw: None)
        assert isinstance(result, str)
        assert "no revisions" in result

    def test_missing_skill_file_is_skipped(self, tmp_path: Path, router: MagicMock) -> None:
        empty_dir = tmp_path / "empty_skills"
        empty_dir.mkdir()
        router.load_usage.return_value = _failure_records("missing.md", failures=3, successes=1)
        result = reflect_skills(empty_dir, router, generate_fn=lambda *a, **kw: REVISED_BODY)
        assert isinstance(result, str)
        assert "no revisions" in result

    def test_forbidden_content_is_rejected(self, skills_dir: Path, router: MagicMock) -> None:
        router.load_usage.return_value = _failure_records("ask-before-reacting.md", failures=3, successes=1)
        # Secret-leak pattern triggers validate_identity_content rejection
        # (see FORBIDDEN_SUBSTRING_PATTERNS in core/config.py).
        rogue = (
            "# Ask Before Reacting\n\n"
            "Use api_key=sk-leaked when initializing the client.\n"
        )
        result = reflect_skills(skills_dir, router, generate_fn=lambda *a, **kw: rogue)
        assert isinstance(result, str)
        assert "no revisions" in result

    def test_failure_contexts_are_passed_to_prompt(
        self, skills_dir: Path, router: MagicMock,
    ) -> None:
        router.load_usage.return_value = _failure_records(
            "ask-before-reacting.md", failures=3, successes=1,
        )
        captured: Dict[str, str] = {}

        def fake_generate(prompt: str, *_a, **_kw):
            captured["prompt"] = prompt
            return REVISED_BODY

        reflect_skills(skills_dir, router, generate_fn=fake_generate)
        prompt = captured["prompt"]
        assert "context-fail-0" in prompt
        assert "Successes: 1" in prompt
        assert "Failures: 3" in prompt
