"""Tests for core.rules_distill — behavioral rule extraction."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from contemplative_agent.core.insight import _extract_title, _slugify
from contemplative_agent.core.rules_distill import (
    RulesDistillResult,
    _extract_rules,
    distill_rules,
)
from contemplative_agent.core.memory import KnowledgeStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GOOD_RULES_RESPONSE_STAGE1 = (
    "Analysis: The patterns reveal a principle about asking questions first."
)

GOOD_RULES_RESPONSE_STAGE2 = (
    "# Engagement Rules\n"
    "\n"
    "## Rule 1: Ask Before Reacting\n"
    "\n"
    "**When:** Encountering unfamiliar viewpoints\n"
    "**Do:** Ask clarifying questions before forming a response\n"
    "**Why:** Premature responses reduce engagement quality\n"
)


def _make_knowledge(tmp_path: Path, n: int = 15) -> KnowledgeStore:
    """Create a KnowledgeStore with n test patterns."""
    ks = KnowledgeStore(path=tmp_path / "knowledge.json")
    for i in range(n):
        ks.add_learned_pattern(
            f"Pattern {i}: agents who ask questions first get better engagement scores and more meaningful conversations",
            importance=0.6,
        )
    ks.save()
    return KnowledgeStore(path=tmp_path / "knowledge.json")


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_basic(self):
        assert _slugify("Engagement Rules") == "engagement-rules"

    def test_special_chars(self):
        assert _slugify("Rule: Ask First!") == "rule-ask-first"

    def test_empty(self):
        assert _slugify("") == ""

    def test_max_length(self):
        long = "a" * 100
        assert len(_slugify(long)) <= 50


class TestExtractTitle:
    def test_extracts_from_markdown(self):
        assert _extract_title("# My Rules") == "My Rules"

    def test_skips_non_title_lines(self):
        assert _extract_title("Hello\n## Subtitle") is None

    def test_returns_none_for_no_title(self):
        assert _extract_title("No title here") is None


class TestExtractRules:
    @patch("contemplative_agent.core.rules_distill.generate")
    def test_success(self, mock_generate):
        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            GOOD_RULES_RESPONSE_STAGE2,
        ]
        result = _extract_rules(["pattern1", "pattern2"])
        assert result is not None
        assert "Engagement Rules" in result
        assert mock_generate.call_count == 2

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_stage1_failure(self, mock_generate):
        mock_generate.return_value = None
        result = _extract_rules(["pattern1"])
        assert result is None

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_stage2_failure(self, mock_generate):
        mock_generate.side_effect = [GOOD_RULES_RESPONSE_STAGE1, None]
        result = _extract_rules(["pattern1"])
        assert result is None

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_no_title_drops(self, mock_generate):
        mock_generate.side_effect = ["Stage 1 result", "No title here"]
        result = _extract_rules(["pattern1"])
        assert result is None


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestDistillRules:
    def test_no_knowledge_store(self):
        result = distill_rules()
        assert isinstance(result, str)
        assert "No knowledge store" in result

    def test_insufficient_patterns(self, tmp_path):
        ks = _make_knowledge(tmp_path, n=5)
        result = distill_rules(knowledge_store=ks, rules_dir=tmp_path / "rules")
        assert isinstance(result, str)
        assert "Insufficient patterns" in result
        assert "5/10" in result

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_extraction_failure(self, mock_generate, tmp_path):
        mock_generate.return_value = None
        ks = _make_knowledge(tmp_path, n=15)
        result = distill_rules(knowledge_store=ks, rules_dir=tmp_path / "rules")
        assert isinstance(result, str)
        assert "Failed to extract" in result

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_forbidden_pattern(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            "Stage 1",
            "# Rules\nLeaked api_key: sk-1234\n",
        ]
        ks = _make_knowledge(tmp_path, n=15)
        result = distill_rules(knowledge_store=ks, rules_dir=tmp_path / "rules")
        assert isinstance(result, str)
        assert "Failed to extract" in result

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_returns_rules_result(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            GOOD_RULES_RESPONSE_STAGE2,
        ]
        ks = _make_knowledge(tmp_path, n=15)
        rules_dir = tmp_path / "rules"
        result = distill_rules(knowledge_store=ks, rules_dir=rules_dir)
        assert isinstance(result, RulesDistillResult)
        assert len(result.rules) == 1
        assert "Engagement Rules" in result.rules[0].text
        today = date.today().strftime("%Y%m%d")
        assert result.rules[0].filename == f"engagement-rules-{today}.md"
        assert result.rules[0].target_path == rules_dir / f"engagement-rules-{today}.md"
        # Core function does not write — caller's responsibility
        assert not rules_dir.exists()

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_empty_slug_dropped(self, mock_generate, tmp_path):
        """Title with only special chars produces empty slug → dropped."""
        mock_generate.side_effect = ["Stage 1", "# !!!\n\nContent"]
        ks = _make_knowledge(tmp_path, n=15)
        rules_dir = tmp_path / "rules"
        result = distill_rules(knowledge_store=ks, rules_dir=rules_dir)
        assert isinstance(result, str)
        assert "Failed to extract" in result


class TestBatchProcessing:
    @patch("contemplative_agent.core.rules_distill.generate")
    def test_multiple_batches(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            GOOD_RULES_RESPONSE_STAGE2,
        ] * 2
        ks = _make_knowledge(tmp_path, n=50)
        result = distill_rules(knowledge_store=ks, rules_dir=tmp_path / "rules")
        assert isinstance(result, RulesDistillResult)
        assert len(result.rules) == 2

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_partial_failure(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            None,  # batch 1 fails
            GOOD_RULES_RESPONSE_STAGE1,  # batch 2 succeeds
            GOOD_RULES_RESPONSE_STAGE2,
        ]
        ks = _make_knowledge(tmp_path, n=50)
        result = distill_rules(knowledge_store=ks, rules_dir=tmp_path / "rules")
        assert isinstance(result, RulesDistillResult)
        assert len(result.rules) == 1
        assert result.dropped_count == 1


class TestIncrementalMode:
    @patch("contemplative_agent.core.rules_distill.generate")
    def test_no_marker_written_by_core(self, mock_generate, tmp_path):
        """Core function does not write marker — caller's responsibility."""
        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            GOOD_RULES_RESPONSE_STAGE2,
        ]
        ks = _make_knowledge(tmp_path, n=15)
        rules_dir = tmp_path / "rules"
        result = distill_rules(knowledge_store=ks, rules_dir=rules_dir)
        assert isinstance(result, RulesDistillResult)
        marker = rules_dir / ".last_rules_distill"
        assert not marker.exists()

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_full_ignores_marker(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            GOOD_RULES_RESPONSE_STAGE2,
        ]
        ks = _make_knowledge(tmp_path, n=15)
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir(parents=True)
        # Write a marker in the future so incremental would find 0 patterns
        (rules_dir / ".last_rules_distill").write_text("2099-01-01T00:00+00:00\n")
        result = distill_rules(
            knowledge_store=ks, rules_dir=rules_dir, full=True,
        )
        assert isinstance(result, RulesDistillResult)
        assert "Engagement Rules" in result.rules[0].text
