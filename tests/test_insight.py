"""Tests for core.insight — behavioral skill extraction (ADR-0009 view-based)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.core.insight import (
    InsightResult,
    SELF_REFLECTION_VIEW,
    _build_view_batches,
    _extract_skill,
    _extract_title,
    _slugify,
    extract_insight,
)
from contemplative_agent.core.memory import KnowledgeStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GOOD_SKILL_RESPONSE = (
    "---\n"
    "name: ask-before-reacting\n"
    'description: "Ask clarifying questions before forming a response"\n'
    "origin: auto-extracted\n"
    "---\n"
    "\n"
    "# Ask Before Reacting\n"
    "\n"
    "**Context:** When encountering unfamiliar viewpoints\n"
    "\n"
    "## Problem\n"
    "Premature responses reduce engagement quality\n"
    "\n"
    "## Solution\n"
    "Ask clarifying questions before forming a response\n"
)


@pytest.fixture
def knowledge_store(tmp_path: Path) -> KnowledgeStore:
    ks = KnowledgeStore(path=tmp_path / "knowledge.json")
    for i in range(5):
        ks.add_learned_pattern(f"Pattern {i}: some behavioral observation",
                               embedding=[float(i) / 5, 1.0 - float(i) / 5])
    ks.save()
    return ks


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    d = tmp_path / "skills"
    d.mkdir()
    return d


@pytest.fixture
def view_registry_one_topic():
    """Mock registry with one non-excluded view that matches all candidates."""
    registry = MagicMock()
    registry.names.return_value = [SELF_REFLECTION_VIEW, "communication"]
    def _find(name, candidates):
        if name == SELF_REFLECTION_VIEW:
            return []
        return list(candidates)
    registry.find_by_view.side_effect = _find
    return registry


# ---------------------------------------------------------------------------
# Unit: _extract_title / _slugify
# ---------------------------------------------------------------------------


class TestExtractTitle:
    def test_extracts_from_markdown(self) -> None:
        assert _extract_title("# My Skill\nsome content") == "My Skill"

    def test_skips_non_title_lines(self) -> None:
        assert _extract_title("## Not a title\n# Real Title") == "Real Title"

    def test_returns_none_for_no_title(self) -> None:
        assert _extract_title("no title here") is None


class TestSlugify:
    def test_basic(self) -> None:
        assert _slugify("Ask Before Reacting") == "ask-before-reacting"

    def test_special_chars(self) -> None:
        assert _slugify("a/b\\c:d") == "a-b-c-d"

    def test_max_length(self) -> None:
        assert len(_slugify("a" * 100)) <= 50


# ---------------------------------------------------------------------------
# _extract_skill
# ---------------------------------------------------------------------------

class TestExtractSkill:
    @patch("contemplative_agent.core.insight.generate")
    def test_returns_skill_text(self, mock_generate) -> None:
        mock_generate.return_value = GOOD_SKILL_RESPONSE
        result = _extract_skill(["p1", "p2"], ["i1"])
        assert result is not None
        assert "# Ask Before Reacting" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_llm_failure(self, mock_generate) -> None:
        mock_generate.return_value = None
        assert _extract_skill(["p1"], []) is None

    @patch("contemplative_agent.core.insight.generate")
    def test_no_title_returns_none(self, mock_generate) -> None:
        mock_generate.return_value = "some text without a title line"
        assert _extract_skill(["p1"], []) is None

    @patch("contemplative_agent.core.insight.generate")
    def test_passes_topic_to_prompt(self, mock_generate) -> None:
        mock_generate.return_value = GOOD_SKILL_RESPONSE
        _extract_skill(["p1"], [], topic="communication")
        prompt_arg = mock_generate.call_args[0][0]
        assert "communication" in prompt_arg


# ---------------------------------------------------------------------------
# extract_insight (orchestrator)
# ---------------------------------------------------------------------------


class TestExtractInsight:
    def test_no_knowledge_store(self) -> None:
        result = extract_insight(knowledge_store=None)
        assert "No knowledge store" in str(result)

    def test_no_view_registry(self, knowledge_store) -> None:
        result = extract_insight(knowledge_store=knowledge_store)
        assert "ViewRegistry" in str(result)

    def test_insufficient_patterns(self, tmp_path, view_registry_one_topic) -> None:
        ks = KnowledgeStore(path=tmp_path / "k.json")
        ks.add_learned_pattern("only one", embedding=[0.1, 0.2])
        ks.save()
        result = extract_insight(knowledge_store=ks,
                                  view_registry=view_registry_one_topic)
        assert "Insufficient patterns" in str(result)

    @patch("contemplative_agent.core.insight._extract_skill")
    def test_extraction_failure(self, mock_skill, knowledge_store,
                                  view_registry_one_topic) -> None:
        mock_skill.return_value = None
        result = extract_insight(knowledge_store=knowledge_store,
                                  view_registry=view_registry_one_topic)
        assert "Failed to extract" in str(result)

    @patch("contemplative_agent.core.insight._extract_skill")
    def test_returns_insight_result(self, mock_skill, knowledge_store,
                                     view_registry_one_topic) -> None:
        mock_skill.return_value = GOOD_SKILL_RESPONSE
        result = extract_insight(knowledge_store=knowledge_store,
                                  view_registry=view_registry_one_topic)
        assert isinstance(result, InsightResult)
        assert len(result.skills) == 1
        assert "# Ask Before Reacting" in result.skills[0].text
        today = date.today().strftime("%Y%m%d")
        assert result.skills[0].filename == f"ask-before-reacting-{today}.md"

    @patch("contemplative_agent.core.insight._extract_skill")
    def test_self_reflection_excluded(self, mock_skill, tmp_path: Path) -> None:
        """Patterns matching the self_reflection view are routed away from insight."""
        ks = KnowledgeStore(path=tmp_path / "k.json")
        # 5 self-reflection patterns
        for i in range(5):
            ks.add_learned_pattern(f"Self-reflection pattern {i}",
                                    embedding=[1.0, 0.0])
        ks.save()

        registry = MagicMock()
        registry.names.return_value = [SELF_REFLECTION_VIEW, "communication"]
        # find_by_view("self_reflection", ...) → all matched (excluded from insight)
        def _find(name, candidates):
            if name == SELF_REFLECTION_VIEW:
                return list(candidates)
            return []
        registry.find_by_view.side_effect = _find

        result = extract_insight(knowledge_store=ks, view_registry=registry)
        # All patterns are self-reflection, so 0 remain → insufficient
        assert "Insufficient patterns" in str(result)
        mock_skill.assert_not_called()


# ---------------------------------------------------------------------------
# _build_view_batches
# ---------------------------------------------------------------------------


class TestBuildViewBatches:
    @staticmethod
    def _pat(text: str, importance: float = 0.5) -> dict:
        return {"pattern": text, "importance": importance,
                "embedding": [0.1, 0.2]}

    def test_one_batch_per_view(self) -> None:
        registry = MagicMock()
        registry.names.return_value = ["communication", "reasoning", "self_reflection"]

        comm_pats = [self._pat(f"comm-{i}") for i in range(5)]
        reason_pats = [self._pat(f"reason-{i}") for i in range(5)]
        all_pats = comm_pats + reason_pats

        def _find(name, candidates):
            if name == "communication":
                return comm_pats
            if name == "reasoning":
                return reason_pats
            return []
        registry.find_by_view.side_effect = _find

        batches = _build_view_batches(all_pats, registry, batch_size=10, min_batch_size=3)
        assert len(batches) == 2
        names = {n for n, _ in batches}
        assert names == {"communication", "reasoning"}

    def test_excluded_views_skipped(self) -> None:
        registry = MagicMock()
        registry.names.return_value = ["self_reflection", "noise", "constitutional", "communication"]
        comm_pats = [self._pat(f"c-{i}") for i in range(5)]
        registry.find_by_view.return_value = comm_pats

        batches = _build_view_batches(comm_pats, registry, batch_size=10, min_batch_size=3)
        # Only "communication" should produce a batch
        names = {n for n, _ in batches}
        assert "self_reflection" not in names
        assert "noise" not in names
        assert "constitutional" not in names

    def test_small_views_merged_into_mixed(self) -> None:
        registry = MagicMock()
        registry.names.return_value = ["communication", "reasoning", "social"]
        big = [self._pat(f"big-{i}") for i in range(5)]

        def _find(name, candidates):
            if name == "communication":
                return big
            if name == "reasoning":
                return [self._pat("r-0")]
            if name == "social":
                return [self._pat("s-0"), self._pat("s-1")]
            return []
        registry.find_by_view.side_effect = _find

        batches = _build_view_batches(big, registry, batch_size=10, min_batch_size=3)
        names = {n for n, _ in batches}
        assert "communication" in names
        # reasoning(1) + social(2) = 3 → "other" mixed batch
        assert "other" in names

    def test_importance_priority(self) -> None:
        registry = MagicMock()
        registry.names.return_value = ["technical"]
        pats = [
            self._pat("low", importance=0.3),
            self._pat("high", importance=0.9),
            self._pat("mid", importance=0.5),
        ]
        registry.find_by_view.return_value = pats

        batches = _build_view_batches(pats, registry, batch_size=30, min_batch_size=3)
        assert len(batches) == 1
        _, texts = batches[0]
        assert texts == ["high", "mid", "low"]
