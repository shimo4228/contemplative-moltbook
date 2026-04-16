"""Tests for ADR-0024 identity block parser/renderer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contemplative_agent.core.identity_blocks import (
    Block,
    IdentityDocument,
    append_history,
    body_hash,
    load_for_prompt,
    migrate_to_blocks,
    parse,
    render,
    update_block,
)


class TestParseLegacy:
    def test_empty_string_returns_legacy_with_empty_body(self):
        doc = parse("")
        assert doc.is_legacy is True
        assert len(doc.blocks) == 1
        assert doc.blocks[0].name == "persona_core"
        assert doc.blocks[0].body == ""

    def test_plain_text_no_frontmatter_returns_legacy(self):
        text = "I'm an AI agent.\n\nSecond paragraph.\n"
        doc = parse(text)
        assert doc.is_legacy is True
        assert doc.blocks[0].name == "persona_core"
        assert "AI agent" in doc.blocks[0].body
        assert "Second paragraph" in doc.blocks[0].body

    def test_malformed_frontmatter_degrades_to_legacy(self):
        text = "---\nblocks:\n  garbage\n---\n\nbody\n"
        doc = parse(text)
        assert doc.is_legacy is True

    def test_unclosed_frontmatter_degrades_to_legacy(self):
        text = "---\nblocks:\n  - name: persona_core\n\nbody without close\n"
        doc = parse(text)
        assert doc.is_legacy is True

    def test_empty_blocks_list_degrades_to_legacy(self):
        text = "---\nblocks:\n---\n\nbody\n"
        doc = parse(text)
        assert doc.is_legacy is True


class TestParseBlocks:
    def test_parses_single_block(self):
        text = (
            "---\n"
            "blocks:\n"
            "  - name: persona_core\n"
            "    last_updated_at: 2026-04-16T10:00:00+00:00\n"
            "    source: distill-identity\n"
            "---\n"
            "\n"
            "## persona_core\n"
            "\n"
            "I'm an AI agent.\n"
        )
        doc = parse(text)
        assert doc.is_legacy is False
        assert len(doc.blocks) == 1
        b = doc.blocks[0]
        assert b.name == "persona_core"
        assert b.last_updated_at == "2026-04-16T10:00:00+00:00"
        assert b.source == "distill-identity"
        assert "AI agent" in b.body

    def test_parses_multiple_blocks_preserving_order(self):
        text = (
            "---\n"
            "blocks:\n"
            "  - name: persona_core\n"
            "    last_updated_at: 2026-04-16T10:00:00+00:00\n"
            "    source: distill-identity\n"
            "  - name: current_goals\n"
            "    last_updated_at: 2026-04-16T10:05:00+00:00\n"
            "    source: agent-edit\n"
            "---\n"
            "\n"
            "## persona_core\n"
            "\n"
            "Core body.\n"
            "\n"
            "## current_goals\n"
            "\n"
            "Goals body.\n"
        )
        doc = parse(text)
        assert doc.is_legacy is False
        assert [b.name for b in doc.blocks] == ["persona_core", "current_goals"]
        assert "Core body" in doc.blocks[0].body
        assert "Goals body" in doc.blocks[1].body
        assert doc.blocks[1].source == "agent-edit"

    def test_unknown_source_coerced_to_legacy_default(self):
        text = (
            "---\n"
            "blocks:\n"
            "  - name: persona_core\n"
            "    source: malicious-override\n"
            "---\n"
            "## persona_core\n\nbody\n"
        )
        doc = parse(text)
        assert doc.is_legacy is False
        assert doc.blocks[0].source == "legacy"

    def test_missing_last_updated_at_is_none(self):
        text = (
            "---\n"
            "blocks:\n"
            "  - name: persona_core\n"
            "    source: distill-identity\n"
            "---\n"
            "## persona_core\n\nbody\n"
        )
        doc = parse(text)
        assert doc.blocks[0].last_updated_at is None

    def test_null_last_updated_at(self):
        text = (
            "---\n"
            "blocks:\n"
            "  - name: persona_core\n"
            "    last_updated_at: null\n"
            "    source: distill-identity\n"
            "---\n"
            "## persona_core\n\nbody\n"
        )
        doc = parse(text)
        assert doc.blocks[0].last_updated_at is None

    def test_extra_keys_preserved(self):
        text = (
            "---\n"
            "blocks:\n"
            "  - name: persona_core\n"
            "    source: distill-identity\n"
            "    authored_by: laukkonen\n"
            "---\n"
            "## persona_core\n\nbody\n"
        )
        doc = parse(text)
        assert doc.blocks[0].extra == {"authored_by": "laukkonen"}

    def test_missing_body_section_gives_empty_body(self):
        text = (
            "---\n"
            "blocks:\n"
            "  - name: persona_core\n"
            "    source: distill-identity\n"
            "---\n"
        )
        doc = parse(text)
        assert doc.blocks[0].body == ""

    def test_quoted_string_values_unquoted(self):
        text = (
            "---\n"
            "blocks:\n"
            '  - name: "persona_core"\n'
            "    source: distill-identity\n"
            "---\n"
            "## persona_core\n\nbody\n"
        )
        doc = parse(text)
        assert doc.blocks[0].name == "persona_core"


class TestRender:
    def test_legacy_round_trip_returns_body_only(self):
        text = "I'm an AI agent.\n\nSecond paragraph.\n"
        doc = parse(text)
        rendered = render(doc)
        assert rendered.strip() == text.strip()
        assert "---" not in rendered

    def test_blocks_render_with_frontmatter_and_sections(self):
        doc = IdentityDocument(
            blocks=(
                Block(
                    name="persona_core",
                    body="core body.\n",
                    last_updated_at="2026-04-16T10:00:00+00:00",
                    source="distill-identity",
                ),
                Block(
                    name="current_goals",
                    body="goals body.\n",
                    last_updated_at="2026-04-16T10:05:00+00:00",
                    source="agent-edit",
                ),
            ),
            is_legacy=False,
        )
        out = render(doc)
        assert out.startswith("---\n")
        assert "blocks:" in out
        assert "- name: persona_core" in out
        assert "- name: current_goals" in out
        assert "## persona_core" in out
        assert "## current_goals" in out
        assert "core body." in out
        assert "goals body." in out

    def test_round_trip_preserves_blocks(self):
        original = (
            "---\n"
            "blocks:\n"
            "  - name: persona_core\n"
            "    last_updated_at: 2026-04-16T10:00:00+00:00\n"
            "    source: distill-identity\n"
            "  - name: current_goals\n"
            "    last_updated_at: 2026-04-16T10:05:00+00:00\n"
            "    source: agent-edit\n"
            "---\n\n"
            "## persona_core\n\nCore body.\n\n"
            "## current_goals\n\nGoals body.\n"
        )
        doc = parse(original)
        re_doc = parse(render(doc))
        assert re_doc.is_legacy is False
        assert [b.name for b in re_doc.blocks] == ["persona_core", "current_goals"]
        assert re_doc.blocks[0].source == "distill-identity"
        assert re_doc.blocks[1].source == "agent-edit"
        assert "Core body" in re_doc.blocks[0].body
        assert "Goals body" in re_doc.blocks[1].body

    def test_extras_round_trip(self):
        doc = IdentityDocument(
            blocks=(
                Block(
                    name="persona_core",
                    body="body\n",
                    last_updated_at="2026-04-16T10:00:00+00:00",
                    source="distill-identity",
                    extra={"authored_by": "laukkonen"},
                ),
            ),
            is_legacy=False,
        )
        re_doc = parse(render(doc))
        assert re_doc.blocks[0].extra == {"authored_by": "laukkonen"}


class TestUpdateBlock:
    def test_updates_existing_block_body_and_metadata(self):
        text = (
            "---\n"
            "blocks:\n"
            "  - name: persona_core\n"
            "    last_updated_at: 2026-01-01T00:00:00+00:00\n"
            "    source: migration\n"
            "---\n"
            "## persona_core\n\nold body\n"
        )
        doc = parse(text)
        new_doc = update_block(
            doc,
            "persona_core",
            body="new body",
            source="distill-identity",
            now="2026-04-16T10:00:00+00:00",
        )
        assert new_doc.blocks[0].body.strip() == "new body"
        assert new_doc.blocks[0].last_updated_at == "2026-04-16T10:00:00+00:00"
        assert new_doc.blocks[0].source == "distill-identity"

    def test_other_blocks_untouched(self):
        text = (
            "---\n"
            "blocks:\n"
            "  - name: persona_core\n"
            "    last_updated_at: 2026-01-01T00:00:00+00:00\n"
            "    source: migration\n"
            "  - name: current_goals\n"
            "    last_updated_at: 2026-01-01T00:00:00+00:00\n"
            "    source: agent-edit\n"
            "---\n"
            "## persona_core\n\nold core\n\n## current_goals\n\ngoals stay\n"
        )
        doc = parse(text)
        new_doc = update_block(
            doc,
            "persona_core",
            body="refreshed core",
            source="distill-identity",
            now="2026-04-16T10:00:00+00:00",
        )
        goals = new_doc.get("current_goals")
        assert goals is not None
        assert "goals stay" in goals.body
        assert goals.last_updated_at == "2026-01-01T00:00:00+00:00"

    def test_append_new_block(self):
        text = (
            "---\n"
            "blocks:\n"
            "  - name: persona_core\n"
            "    source: migration\n"
            "---\n"
            "## persona_core\n\ncore\n"
        )
        doc = parse(text)
        new_doc = update_block(
            doc,
            "current_goals",
            body="newly added goals",
            source="agent-edit",
            now="2026-04-16T10:00:00+00:00",
        )
        names = [b.name for b in new_doc.blocks]
        assert names == ["persona_core", "current_goals"]
        assert new_doc.get("current_goals").body.strip() == "newly added goals"

    def test_legacy_persona_core_stays_legacy(self):
        doc = parse("legacy body\n")
        new_doc = update_block(
            doc,
            "persona_core",
            body="new body",
            source="distill-identity",
        )
        assert new_doc.is_legacy is True
        assert new_doc.blocks[0].body.strip() == "new body"
        assert "---" not in render(new_doc)

    def test_legacy_non_persona_raises(self):
        doc = parse("legacy body\n")
        with pytest.raises(ValueError):
            update_block(
                doc,
                "current_goals",
                body="x",
                source="agent-edit",
            )

    def test_unknown_source_rejected(self):
        doc = parse("body\n")
        with pytest.raises(ValueError):
            update_block(doc, "persona_core", body="x", source="bogus-source")


class TestLoadForPrompt:
    def test_missing_file_returns_empty_string(self, tmp_path: Path):
        assert load_for_prompt(tmp_path / "missing.md") == ""

    def test_legacy_returns_verbatim(self, tmp_path: Path):
        path = tmp_path / "identity.md"
        path.write_text("I'm an AI agent.\n", encoding="utf-8")
        assert load_for_prompt(path) == "I'm an AI agent."

    def test_block_returns_concatenated_without_frontmatter(self, tmp_path: Path):
        path = tmp_path / "identity.md"
        path.write_text(
            "---\n"
            "blocks:\n"
            "  - name: persona_core\n"
            "    source: distill-identity\n"
            "  - name: current_goals\n"
            "    source: agent-edit\n"
            "---\n"
            "## persona_core\n\nCore.\n\n## current_goals\n\nGoals.\n",
            encoding="utf-8",
        )
        out = load_for_prompt(path)
        assert "---" not in out
        assert "blocks:" not in out
        assert "## persona_core" not in out
        assert "Core." in out
        assert "Goals." in out

    def test_skips_empty_blocks(self, tmp_path: Path):
        path = tmp_path / "identity.md"
        path.write_text(
            "---\n"
            "blocks:\n"
            "  - name: persona_core\n"
            "    source: distill-identity\n"
            "  - name: current_goals\n"
            "    source: agent-edit\n"
            "---\n"
            "## persona_core\n\nCore.\n",
            encoding="utf-8",
        )
        # Only persona_core has body; current_goals empty → single chunk.
        out = load_for_prompt(path)
        assert out.strip() == "Core."


class TestMigration:
    def test_migrates_legacy_file(self, tmp_path: Path):
        path = tmp_path / "identity.md"
        path.write_text("legacy body\n", encoding="utf-8")
        result = migrate_to_blocks(path, now="2026-04-16T10:00:00+00:00")
        assert result.migrated is True
        assert result.already_migrated is False
        assert result.backup_path is not None
        assert result.backup_path.exists()
        assert result.backup_path.read_text(encoding="utf-8") == "legacy body\n"

        migrated_text = path.read_text(encoding="utf-8")
        assert migrated_text.startswith("---\n")
        doc = parse(migrated_text)
        assert doc.is_legacy is False
        assert doc.blocks[0].source == "migration"
        assert "legacy body" in doc.blocks[0].body

    def test_idempotent_when_already_migrated(self, tmp_path: Path):
        path = tmp_path / "identity.md"
        path.write_text(
            "---\n"
            "blocks:\n"
            "  - name: persona_core\n"
            "    source: distill-identity\n"
            "---\n"
            "## persona_core\n\nbody\n",
            encoding="utf-8",
        )
        original = path.read_text(encoding="utf-8")
        result = migrate_to_blocks(path)
        assert result.migrated is False
        assert result.already_migrated is True
        assert path.read_text(encoding="utf-8") == original

    def test_missing_file_no_op(self, tmp_path: Path):
        path = tmp_path / "does-not-exist.md"
        result = migrate_to_blocks(path)
        assert result.migrated is False
        assert result.already_migrated is False


class TestBodyHash:
    def test_deterministic(self):
        assert body_hash("hello") == body_hash("hello")

    def test_differs_for_different_input(self):
        assert body_hash("a") != body_hash("b")

    def test_sixteen_hex_chars(self):
        h = body_hash("anything")
        assert len(h) == 16
        int(h, 16)  # must parse as hex


class TestAppendHistory:
    def test_appends_jsonl_line(self, tmp_path: Path):
        hist = tmp_path / "identity_history.jsonl"
        append_history(
            hist,
            block="persona_core",
            old_body="old",
            new_body="new",
            source="distill-identity",
            now="2026-04-16T10:00:00+00:00",
        )
        entry = json.loads(hist.read_text(encoding="utf-8").strip())
        assert entry["block"] == "persona_core"
        assert entry["source"] == "distill-identity"
        assert entry["old_hash"] == body_hash("old")
        assert entry["new_hash"] == body_hash("new")
        assert entry["ts"] == "2026-04-16T10:00:00+00:00"

    def test_appends_not_truncates(self, tmp_path: Path):
        hist = tmp_path / "identity_history.jsonl"
        append_history(
            hist,
            block="persona_core",
            old_body="a",
            new_body="b",
            source="distill-identity",
        )
        append_history(
            hist,
            block="current_goals",
            old_body="c",
            new_body="d",
            source="agent-edit",
        )
        lines = hist.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        blocks = [json.loads(ln)["block"] for ln in lines]
        assert blocks == ["persona_core", "current_goals"]

    def test_creates_parent_dir(self, tmp_path: Path):
        hist = tmp_path / "nested" / "dir" / "identity_history.jsonl"
        append_history(
            hist,
            block="persona_core",
            old_body="a",
            new_body="b",
            source="distill-identity",
        )
        assert hist.exists()
