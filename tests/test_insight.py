"""Tests for core.insight — behavioral skill extraction."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from contemplative_agent.core.insight import (
    InsightResult,
    _GROUP_SKIP_THRESHOLD,
    _build_subcategory_batches,
    _extract_skill,
    _extract_title,
    _group_patterns,
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
    "\n"
    "## When to Use\n"
    "When an agent presents a viewpoint you haven't encountered before\n"
)


@pytest.fixture
def knowledge_store(tmp_path: Path) -> KnowledgeStore:
    ks = KnowledgeStore(path=tmp_path / "knowledge.json")
    for i in range(5):
        ks.add_learned_pattern(f"Pattern {i}: some behavioral observation")
    ks.save()
    return ks


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    d = tmp_path / "skills"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Unit: _extract_title
# ---------------------------------------------------------------------------


class TestExtractTitle:
    def test_extracts_from_markdown(self) -> None:
        assert _extract_title("# My Skill\nsome content") == "My Skill"

    def test_skips_non_title_lines(self) -> None:
        assert _extract_title("## Not a title\n# Real Title") == "Real Title"

    def test_returns_none_for_no_title(self) -> None:
        assert _extract_title("no title here") is None

    def test_strips_whitespace(self) -> None:
        assert _extract_title("#   Spaced Title  ") == "Spaced Title"

    def test_with_frontmatter(self) -> None:
        text = "---\nname: foo\n---\n\n# Title After Frontmatter"
        assert _extract_title(text) == "Title After Frontmatter"


# ---------------------------------------------------------------------------
# Unit: _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic(self) -> None:
        assert _slugify("Ask Before Reacting") == "ask-before-reacting"

    def test_special_chars(self) -> None:
        assert _slugify("a/b\\c:d") == "a-b-c-d"

    def test_empty(self) -> None:
        assert _slugify("") == ""

    def test_max_length(self) -> None:
        assert len(_slugify("a" * 100)) <= 50


# ---------------------------------------------------------------------------
# Integration: _extract_skills
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
    def test_passes_subcategory(self, mock_generate) -> None:
        mock_generate.return_value = GOOD_SKILL_RESPONSE
        _extract_skill(["p1"], [], subcategory="communication")
        prompt_arg = mock_generate.call_args[0][0]
        assert "communication" in prompt_arg


# ---------------------------------------------------------------------------
# Unit: _group_patterns
# ---------------------------------------------------------------------------


class TestGroupPatterns:
    def test_small_batch_skips_grouping(self) -> None:
        """Batches smaller than threshold return as single group."""
        patterns = ["p1", "p2", "p3"]
        assert len(patterns) < _GROUP_SKIP_THRESHOLD
        result = _group_patterns(patterns)
        assert result == [patterns]

    @patch("contemplative_agent.core.insight.generate")
    def test_valid_json_grouping(self, mock_generate) -> None:
        mock_generate.return_value = json.dumps(
            {"groups": {"theme_a": [1, 3, 5, 7, 9], "theme_b": [2, 4, 6, 8, 10]}}
        )
        patterns = [f"p{i}" for i in range(10)]
        result = _group_patterns(patterns)
        assert len(result) == 2
        assert result[0] == ["p0", "p2", "p4", "p6", "p8"]
        assert result[1] == ["p1", "p3", "p5", "p7", "p9"]

    @patch("contemplative_agent.core.insight.generate")
    def test_llm_failure_fallback(self, mock_generate) -> None:
        mock_generate.return_value = None
        patterns = [f"p{i}" for i in range(10)]
        result = _group_patterns(patterns)
        assert result == [patterns]

    @patch("contemplative_agent.core.insight.generate")
    def test_invalid_json_fallback(self, mock_generate) -> None:
        mock_generate.return_value = "not json at all"
        patterns = [f"p{i}" for i in range(10)]
        result = _group_patterns(patterns)
        assert result == [patterns]

    @patch("contemplative_agent.core.insight.generate")
    def test_out_of_range_indices_ignored(self, mock_generate) -> None:
        mock_generate.return_value = json.dumps(
            {"groups": {"a": [1, 99], "b": [2, -1]}}
        )
        patterns = [f"p{i}" for i in range(10)]
        result = _group_patterns(patterns)
        assert len(result) == 2
        assert result[0] == ["p0"]
        assert result[1] == ["p1"]

    @patch("contemplative_agent.core.insight.generate")
    def test_empty_groups_dropped(self, mock_generate) -> None:
        mock_generate.return_value = json.dumps(
            {"groups": {"a": [99, 100], "b": [1, 2]}}
        )
        patterns = [f"p{i}" for i in range(10)]
        result = _group_patterns(patterns)
        assert len(result) == 1
        assert result[0] == ["p0", "p1"]


# ---------------------------------------------------------------------------
# Integration: extract_insight (orchestrator)
# ---------------------------------------------------------------------------


class TestExtractInsight:
    def test_no_knowledge_store(self) -> None:
        result = extract_insight(knowledge_store=None)
        assert isinstance(result, str)
        assert "No knowledge store" in result

    def test_insufficient_patterns(self, tmp_path: Path) -> None:
        ks = KnowledgeStore(path=tmp_path / "k.md")
        ks.add_learned_pattern("only one")
        ks.save()
        result = extract_insight(knowledge_store=ks)
        assert isinstance(result, str)
        assert "Insufficient patterns" in result

    @patch("contemplative_agent.core.insight._extract_skill")
    @patch("contemplative_agent.core.insight._group_patterns")
    def test_extraction_failure(self, mock_group, mock_skill, knowledge_store) -> None:
        mock_group.side_effect = lambda pats: [pats]
        mock_skill.return_value = None
        result = extract_insight(knowledge_store=knowledge_store)
        assert isinstance(result, str)
        assert "Failed to extract" in result

    @patch("contemplative_agent.core.insight.validate_identity_content")
    @patch("contemplative_agent.core.insight._extract_skill")
    @patch("contemplative_agent.core.insight._group_patterns")
    def test_forbidden_pattern(
        self, mock_group, mock_skill, mock_validate, knowledge_store
    ) -> None:
        mock_group.side_effect = lambda pats: [pats]
        mock_skill.return_value = GOOD_SKILL_RESPONSE
        mock_validate.return_value = False
        result = extract_insight(knowledge_store=knowledge_store)
        assert isinstance(result, str)
        assert "Failed to extract" in result

    @patch("contemplative_agent.core.insight._extract_skill")
    @patch("contemplative_agent.core.insight._group_patterns")
    def test_returns_insight_result(self, mock_group, mock_skill, knowledge_store) -> None:
        mock_group.side_effect = lambda pats: [pats]
        mock_skill.return_value = GOOD_SKILL_RESPONSE
        result = extract_insight(knowledge_store=knowledge_store)
        assert isinstance(result, InsightResult)
        assert len(result.skills) == 1
        assert "# Ask Before Reacting" in result.skills[0].text
        today = date.today().strftime("%Y%m%d")
        assert result.skills[0].filename == f"ask-before-reacting-{today}.md"

    @patch("contemplative_agent.core.insight._extract_skill")
    @patch("contemplative_agent.core.insight._group_patterns")
    def test_result_has_target_path(
        self, mock_group, mock_skill, knowledge_store, skills_dir
    ) -> None:
        mock_group.side_effect = lambda pats: [pats]
        mock_skill.return_value = GOOD_SKILL_RESPONSE
        result = extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=skills_dir,
        )
        assert isinstance(result, InsightResult)
        today = date.today().strftime("%Y%m%d")
        assert result.skills[0].target_path == skills_dir / f"ask-before-reacting-{today}.md"
        # Core function does not write files — caller's responsibility
        assert len(list(skills_dir.glob("*.md"))) == 0

    @patch("contemplative_agent.core.insight._extract_skill")
    @patch("contemplative_agent.core.insight._group_patterns")
    def test_path_traversal_guard(
        self, mock_group, mock_skill, knowledge_store, tmp_path
    ) -> None:
        evil_response = GOOD_SKILL_RESPONSE.replace(
            "# Ask Before Reacting", "# ../../etc/passwd"
        )
        mock_group.side_effect = lambda pats: [pats]
        mock_skill.return_value = evil_response
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        result = extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=skills_dir,
        )
        # Path traversal is blocked but slug sanitization makes it safe
        assert isinstance(result, InsightResult)
        assert "etc-passwd" in result.skills[0].filename
        assert ".." not in result.skills[0].filename


# ---------------------------------------------------------------------------
# Integration: batch processing
# ---------------------------------------------------------------------------


class TestBatchProcessing:
    @pytest.fixture
    def three_batch_store(self, tmp_path: Path) -> KnowledgeStore:
        subs = ("communication", "reasoning", "social")
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        for i in range(65):
            ks.add_learned_pattern(
                f"Pattern {i}: observation about behavior {i}",
                subcategory=subs[i % 3],
            )
        ks.save()
        ks._learned_patterns.clear()
        return ks

    @patch("contemplative_agent.core.insight._extract_skill")
    @patch("contemplative_agent.core.insight._group_patterns")
    def test_multiple_batches(
        self, mock_group, mock_skill, three_batch_store, skills_dir
    ) -> None:
        # Each batch returns a single group (pass-through)
        mock_group.side_effect = lambda pats: [pats]
        skill_a = GOOD_SKILL_RESPONSE
        skill_b = GOOD_SKILL_RESPONSE.replace("Ask Before Reacting", "Adapt Tone").replace("ask-before-reacting", "adapt-tone")
        skill_c = GOOD_SKILL_RESPONSE.replace("Ask Before Reacting", "Set Boundaries").replace("ask-before-reacting", "set-boundaries")
        mock_skill.side_effect = [skill_a, skill_b, skill_c]
        result = extract_insight(
            knowledge_store=three_batch_store,
            skills_dir=skills_dir,
        )
        assert isinstance(result, InsightResult)
        assert len(result.skills) == 3

    @patch("contemplative_agent.core.insight._extract_skill")
    @patch("contemplative_agent.core.insight._group_patterns")
    def test_partial_failure(
        self, mock_group, mock_skill, three_batch_store, skills_dir
    ) -> None:
        mock_group.side_effect = lambda pats: [pats]
        skill_c = GOOD_SKILL_RESPONSE.replace("Ask Before Reacting", "Set Boundaries").replace("ask-before-reacting", "set-boundaries")
        mock_skill.side_effect = [None, GOOD_SKILL_RESPONSE, skill_c]
        result = extract_insight(
            knowledge_store=three_batch_store,
            skills_dir=skills_dir,
        )
        assert isinstance(result, InsightResult)
        assert len(result.skills) == 2
        assert result.dropped_count == 1

    @patch("contemplative_agent.core.insight._extract_skill")
    @patch("contemplative_agent.core.insight._group_patterns")
    def test_grouping_produces_multiple_skills(
        self, mock_group, mock_skill, three_batch_store, skills_dir
    ) -> None:
        """One batch can produce multiple skills via grouping."""
        mock_group.side_effect = [
            [["p1", "p2"], ["p3", "p4"]],  # batch 1: 2 groups
            [["p5"]],                        # batch 2: 1 group
            [["p6"]],                        # batch 3: 1 group
        ]
        skill_a = GOOD_SKILL_RESPONSE
        skill_b = GOOD_SKILL_RESPONSE.replace("Ask Before Reacting", "Adapt Tone").replace("ask-before-reacting", "adapt-tone")
        skill_c = GOOD_SKILL_RESPONSE.replace("Ask Before Reacting", "Set Boundaries").replace("ask-before-reacting", "set-boundaries")
        skill_d = GOOD_SKILL_RESPONSE.replace("Ask Before Reacting", "Deep Listening").replace("ask-before-reacting", "deep-listening")
        mock_skill.side_effect = [skill_a, skill_b, skill_c, skill_d]
        result = extract_insight(
            knowledge_store=three_batch_store,
            skills_dir=skills_dir,
        )
        assert isinstance(result, InsightResult)
        assert len(result.skills) == 4

    @patch("contemplative_agent.core.insight._extract_skill")
    @patch("contemplative_agent.core.insight._group_patterns")
    def test_small_last_batch_merged(self, mock_group, mock_skill, tmp_path: Path) -> None:
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        for i in range(32):
            ks.add_learned_pattern(f"Pattern {i}: unique observation {i}")
        ks.save()
        ks._learned_patterns.clear()

        mock_group.side_effect = lambda pats: [pats]
        mock_skill.return_value = GOOD_SKILL_RESPONSE
        extract_insight(knowledge_store=ks)
        assert mock_skill.call_count == 1  # 1 batch, 1 group, 1 skill

    def test_single_batch(self, knowledge_store, skills_dir) -> None:
        with patch("contemplative_agent.core.insight._group_patterns") as mock_group, \
             patch("contemplative_agent.core.insight._extract_skill") as mock_skill:
            mock_group.side_effect = lambda pats: [pats]
            mock_skill.return_value = GOOD_SKILL_RESPONSE
            result = extract_insight(
                knowledge_store=knowledge_store,
                skills_dir=skills_dir,
            )
            assert isinstance(result, InsightResult)
            assert len(result.skills) == 1


# ---------------------------------------------------------------------------
# Integration: incremental mode
# ---------------------------------------------------------------------------


class TestIncrementalMode:
    @patch("contemplative_agent.core.insight._extract_skill")
    @patch("contemplative_agent.core.insight._group_patterns")
    def test_no_marker_written_by_core(
        self, mock_group, mock_skill, knowledge_store, skills_dir
    ) -> None:
        """Core function does not write marker — caller's responsibility."""
        mock_group.side_effect = lambda pats: [pats]
        mock_skill.return_value = GOOD_SKILL_RESPONSE
        result = extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=skills_dir,
        )
        assert isinstance(result, InsightResult)
        marker = skills_dir / ".last_insight"
        assert not marker.exists()

    def test_incremental_filters_old_patterns(self, tmp_path) -> None:
        """With .last_insight set, only new patterns are processed."""
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("old pattern", distilled="2026-01-01T00:00+00:00")
        ks.add_learned_pattern("new pattern", distilled="2026-03-20T12:00+00:00")
        ks.save()
        ks._learned_patterns.clear()

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        # Set last insight to before the new pattern
        (skills_dir / ".last_insight").write_text("2026-03-01T00:00+00:00\n")

        result = extract_insight(
            knowledge_store=ks,
            skills_dir=skills_dir,
        )
        # Only 1 new pattern, which is < MIN_PATTERNS_REQUIRED (3)
        assert isinstance(result, str)
        assert "Insufficient patterns (1/3)" in result

    @patch("contemplative_agent.core.insight._extract_skill")
    @patch("contemplative_agent.core.insight._group_patterns")
    def test_full_ignores_marker(
        self, mock_group, mock_skill, knowledge_store, skills_dir
    ) -> None:
        """--full processes all patterns regardless of marker."""
        (skills_dir / ".last_insight").write_text("2099-01-01T00:00+00:00\n")
        mock_group.side_effect = lambda pats: [pats]
        mock_skill.return_value = GOOD_SKILL_RESPONSE
        result = extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=skills_dir,
            full=True,
        )
        assert isinstance(result, InsightResult)
        assert len(result.skills) == 1


# ---------------------------------------------------------------------------
# Unit: _build_subcategory_batches
# ---------------------------------------------------------------------------


class TestSubcategoryBatches:
    """Test subcategory-based batch building for focused skill extraction."""

    @staticmethod
    def _make_pattern(
        text: str,
        subcategory: str | None = None,
        rarity: float | None = None,
        importance: float | None = None,
    ) -> dict:
        p: dict = {"pattern": text, "category": "uncategorized"}
        if subcategory is not None:
            p["subcategory"] = subcategory
        if rarity is not None:
            p["rarity"] = rarity
        if importance is not None:
            p["importance"] = importance
        return p

    def test_one_batch_per_subcategory(self) -> None:
        """Each subcategory with enough patterns gets its own batch."""
        patterns = []
        for sub in ("communication", "reasoning", "social"):
            for i in range(5):
                patterns.append(self._make_pattern(f"{sub}-{i}", subcategory=sub))
        batches = _build_subcategory_batches(patterns, batch_size=30)
        assert len(batches) == 3
        # Each batch is labeled with its subcategory
        names = {name for name, _ in batches}
        assert names == {"communication", "reasoning", "social"}

    def test_composite_score_priority(self) -> None:
        """Higher importance*rarity patterns come first within a batch."""
        patterns = [
            self._make_pattern("low-both", subcategory="technical", rarity=2.0, importance=0.3),
            self._make_pattern("high-rarity", subcategory="technical", rarity=9.0, importance=0.5),
            self._make_pattern("high-importance", subcategory="technical", rarity=3.0, importance=0.9),
        ]
        batches = _build_subcategory_batches(patterns, batch_size=30)
        assert len(batches) == 1
        name, texts = batches[0]
        assert name == "technical"
        # Scores: high-rarity=4.5, high-importance=2.7, low-both=0.6
        assert texts == ["high-rarity", "high-importance", "low-both"]

    def test_batch_size_caps_per_subcategory(self) -> None:
        """Each subcategory is capped at batch_size patterns."""
        patterns = [self._make_pattern(f"p{i}", subcategory="content", rarity=float(i)) for i in range(10)]
        batches = _build_subcategory_batches(patterns, batch_size=5)
        assert len(batches) == 1
        _, texts = batches[0]
        assert len(texts) == 5
        # Highest composite score first (importance defaults to 0.5)
        # Scores: p9=4.5, p8=4.0, p7=3.5, p6=3.0, p5=2.5
        assert texts[0] == "p9"

    def test_small_subcategories_merged(self) -> None:
        """Subcategories below min_batch_size are merged into one mixed batch."""
        patterns = [
            self._make_pattern("comm-0", subcategory="communication"),
            self._make_pattern("comm-1", subcategory="communication"),
            self._make_pattern("tech-0", subcategory="technical"),
            # 5 reasoning patterns → own batch
            *[self._make_pattern(f"reason-{i}", subcategory="reasoning") for i in range(5)],
        ]
        batches = _build_subcategory_batches(patterns, batch_size=30, min_batch_size=3)
        assert len(batches) == 2
        batch_dict = {name: texts for name, texts in batches}
        assert len(batch_dict["reasoning"]) == 5
        assert len(batch_dict["mixed"]) == 3

    def test_fallback_no_subcategory(self) -> None:
        """Patterns without subcategory all land in 'other' group."""
        patterns = [self._make_pattern(f"p{i}") for i in range(10)]
        batches = _build_subcategory_batches(patterns, batch_size=30)
        assert len(batches) == 1
        name, texts = batches[0]
        assert name == "other"
        assert len(texts) == 10

    def test_small_merged_into_last_when_below_min(self) -> None:
        """If merged small patterns are still below min, append to last batch."""
        patterns = [
            self._make_pattern("lone", subcategory="social"),
            *[self._make_pattern(f"reason-{i}", subcategory="reasoning") for i in range(5)],
        ]
        batches = _build_subcategory_batches(patterns, batch_size=30, min_batch_size=3)
        # social(1) < min_batch_size, merged into reasoning batch
        assert len(batches) == 1
        _, texts = batches[0]
        assert len(texts) == 6
