"""Tests for insight extraction module."""

from unittest.mock import patch

import pytest

from contemplative_agent.core.insight import (
    SkillFile,
    _match_axiom,
    _parse_skill_content,
    _render_skill_file,
    _slugify,
    extract_insight,
)
from contemplative_agent.core.memory import KnowledgeStore


VALID_LLM_RESPONSE = (
    "TITLE: Engage with curiosity before judgment\n"
    "CONTEXT: When encountering unfamiliar viewpoints in discussions\n"
    "BEHAVIOR: Ask clarifying questions before forming a response\n"
    "EVIDENCE: Patterns show better engagement when understanding precedes reaction"
)


def _make_knowledge_store(tmp_path, num_patterns=5):
    """Create a KnowledgeStore with test data, saved and freshly loaded."""
    ks = KnowledgeStore(path=tmp_path / "knowledge.md")
    for i in range(num_patterns):
        ks.add_learned_pattern(f"Pattern {i}: some learned behavior")
    ks.add_insight("Insight about engagement quality")
    ks.save()
    # Return a fresh instance so load() in extract_insight doesn't double-count
    fresh = KnowledgeStore(path=tmp_path / "knowledge.md")
    return fresh


class TestExtractInsight:
    """Tests for the main extract_insight function."""

    @patch("contemplative_agent.core.insight.generate")
    def test_basic_extraction(self, mock_generate, tmp_path):
        mock_generate.return_value = VALID_LLM_RESPONSE
        ks = _make_knowledge_store(tmp_path)
        skills_dir = tmp_path / "skills"

        result = extract_insight(
            knowledge_store=ks,
            constitutional_clauses="Act with care and consideration.",
            skills_dir=skills_dir,
        )

        assert "# Engage with curiosity before judgment" in result
        assert "## Context" in result
        assert "## Behavior" in result
        assert "## Evidence" in result
        assert "confidence: 0.5" in result
        assert "source_patterns: 5" in result

        # Verify file was written
        files = list(skills_dir.glob("*.md"))
        assert len(files) == 1
        assert "engage-with-curiosity" in files[0].name

    @patch("contemplative_agent.core.insight.generate")
    def test_dry_run_does_not_write(self, mock_generate, tmp_path):
        mock_generate.return_value = VALID_LLM_RESPONSE
        ks = _make_knowledge_store(tmp_path)
        skills_dir = tmp_path / "skills"

        result = extract_insight(
            knowledge_store=ks,
            skills_dir=skills_dir,
            dry_run=True,
        )

        assert "# Engage with curiosity before judgment" in result
        assert not skills_dir.exists()

    def test_insufficient_patterns(self, tmp_path):
        ks = _make_knowledge_store(tmp_path, num_patterns=2)

        result = extract_insight(knowledge_store=ks)

        assert "Insufficient patterns" in result
        assert "2/3" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_llm_failure(self, mock_generate, tmp_path):
        mock_generate.return_value = None
        ks = _make_knowledge_store(tmp_path)

        result = extract_insight(knowledge_store=ks)

        assert "LLM failed" in result

    @patch("contemplative_agent.core.insight.generate")
    @patch("contemplative_agent.core.insight.validate_identity_content")
    def test_forbidden_pattern_prevents_write(
        self, mock_validate, mock_generate, tmp_path
    ):
        mock_generate.return_value = VALID_LLM_RESPONSE
        mock_validate.return_value = False
        ks = _make_knowledge_store(tmp_path)
        skills_dir = tmp_path / "skills"

        result = extract_insight(
            knowledge_store=ks, skills_dir=skills_dir
        )

        assert "forbidden" in result.lower()
        assert not skills_dir.exists()

    @patch("contemplative_agent.core.insight.generate")
    def test_parse_failure(self, mock_generate, tmp_path):
        mock_generate.return_value = "Just some random text without fields"
        ks = _make_knowledge_store(tmp_path)

        result = extract_insight(knowledge_store=ks)

        assert "Failed to parse" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_skills_dir_created(self, mock_generate, tmp_path):
        mock_generate.return_value = VALID_LLM_RESPONSE
        ks = _make_knowledge_store(tmp_path)
        skills_dir = tmp_path / "nested" / "skills"

        extract_insight(
            knowledge_store=ks, skills_dir=skills_dir
        )

        assert skills_dir.exists()
        assert len(list(skills_dir.glob("*.md"))) == 1

    def test_no_knowledge_store(self):
        result = extract_insight(knowledge_store=None)
        assert "No knowledge store" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_no_skills_dir_returns_result(self, mock_generate, tmp_path):
        mock_generate.return_value = VALID_LLM_RESPONSE
        ks = _make_knowledge_store(tmp_path)

        result = extract_insight(
            knowledge_store=ks, skills_dir=None
        )

        assert "# Engage with curiosity before judgment" in result


class TestParseSkillContent:
    """Tests for _parse_skill_content."""

    def test_parse_valid(self):
        result = _parse_skill_content(VALID_LLM_RESPONSE)
        assert result is not None
        title, context, behavior, evidence = result
        assert title == "Engage with curiosity before judgment"
        assert "unfamiliar viewpoints" in context
        assert "clarifying questions" in behavior
        assert "better engagement" in evidence

    def test_parse_missing_field(self):
        incomplete = "TITLE: Something\nCONTEXT: When doing things"
        result = _parse_skill_content(incomplete)
        assert result is None

    def test_parse_with_extra_text(self):
        response = (
            "Here is my analysis:\n\n"
            + VALID_LLM_RESPONSE
            + "\n\nI hope this helps."
        )
        result = _parse_skill_content(response)
        assert result is not None
        assert result[0] == "Engage with curiosity before judgment"

    def test_fields_truncated(self):
        long_response = (
            f"TITLE: {'x' * 300}\n"
            f"CONTEXT: {'y' * 300}\n"
            f"BEHAVIOR: {'z' * 300}\n"
            f"EVIDENCE: {'w' * 300}"
        )
        result = _parse_skill_content(long_response)
        assert result is not None
        for field in result:
            assert len(field) <= 200

    def test_case_insensitive(self):
        response = (
            "title: Skill Name\n"
            "context: When needed\n"
            "behavior: Do the thing\n"
            "evidence: Patterns show it works"
        )
        result = _parse_skill_content(response)
        assert result is not None
        assert result[0] == "Skill Name"


class TestMatchAxiom:
    """Tests for _match_axiom."""

    def test_match_found(self):
        content = "engage with curiosity and careful consideration"
        clauses = (
            "# Constitutional Clauses\n"
            "Act with careful consideration and empathy.\n"
            "Maintain transparency in all actions.\n"
        )
        result = _match_axiom(content, clauses)
        assert "careful consideration" in result

    def test_no_match(self):
        content = "completely unrelated topic about databases"
        clauses = "Act with empathy and care.\nMaintain transparency."
        result = _match_axiom(content, clauses)
        assert result == "none"

    def test_empty_clauses(self):
        result = _match_axiom("some content", "")
        assert result == "none"

    def test_empty_content(self):
        result = _match_axiom("", "Some clause text here")
        assert result == "none"

    def test_short_words_ignored(self):
        """Words shorter than 4 chars should be ignored to avoid noise."""
        content = "the and for but"
        clauses = "The and for but clause"
        result = _match_axiom(content, clauses)
        assert result == "none"


class TestSlugify:
    """Tests for _slugify."""

    def test_basic(self):
        assert _slugify("Engage With Care") == "engage-with-care"

    def test_special_chars(self):
        assert _slugify("Hello, World! #1") == "hello-world-1"

    def test_max_length(self):
        long_title = "a" * 100
        result = _slugify(long_title)
        assert len(result) <= 50

    def test_empty(self):
        assert _slugify("") == ""

    def test_unicode(self):
        result = _slugify("café résumé")
        assert "cafe" in result


class TestRenderSkillFile:
    """Tests for _render_skill_file."""

    def test_yaml_frontmatter(self):
        skill = SkillFile(
            title="Test Skill",
            context="When testing",
            behavior="Write tests first",
            evidence="TDD patterns",
            axiom="none",
            confidence=0.5,
            extracted="2026-03-16",
            source_patterns=5,
        )
        rendered = _render_skill_file(skill)

        assert rendered.startswith("---\n")
        assert 'axiom: "none"' in rendered
        assert "confidence: 0.5" in rendered
        assert 'extracted: "2026-03-16"' in rendered
        assert "source_patterns: 5" in rendered
        assert "# Test Skill" in rendered
        assert "## Context\nWhen testing" in rendered
        assert "## Behavior\nWrite tests first" in rendered
        assert "## Evidence\nTDD patterns" in rendered

    def test_body_sections(self):
        skill = SkillFile(
            title="My Skill",
            context="ctx",
            behavior="bhv",
            evidence="evd",
            axiom="some clause",
            confidence=0.7,
            extracted="2026-01-01",
            source_patterns=10,
        )
        rendered = _render_skill_file(skill)

        sections = ["## Context", "## Behavior", "## Evidence"]
        for section in sections:
            assert section in rendered
