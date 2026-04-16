"""Tests for ADR-0023 skill frontmatter parsing/rendering."""

from __future__ import annotations

import pytest

from contemplative_agent.core.skill_frontmatter import (
    SkillMeta,
    _coerce_int,
    _coerce_str_or_none,
    parse,
    render,
    update_meta,
)


class TestParse:
    def test_no_frontmatter_returns_defaults_and_original_text(self):
        text = "# Title\n\nbody"
        meta, body = parse(text)
        assert meta == SkillMeta()
        assert body == text

    def test_empty_string(self):
        meta, body = parse("")
        assert meta == SkillMeta()
        assert body == ""

    def test_full_frontmatter_parsed(self):
        text = (
            "---\n"
            "last_reflected_at: 2026-04-16T10:00\n"
            "success_count: 3\n"
            "failure_count: 1\n"
            "---\n"
            "# Title\n"
            "\n"
            "body here\n"
        )
        meta, body = parse(text)
        assert meta.last_reflected_at == "2026-04-16T10:00"
        assert meta.success_count == 3
        assert meta.failure_count == 1
        assert body.startswith("# Title")
        assert "body here" in body

    def test_null_values_coerced(self):
        text = (
            "---\n"
            "last_reflected_at: null\n"
            "success_count: 0\n"
            "failure_count: 0\n"
            "---\n"
            "# Title\n"
        )
        meta, _ = parse(text)
        assert meta.last_reflected_at is None
        assert meta.success_count == 0

    def test_missing_known_key_defaults(self):
        text = "---\nsuccess_count: 5\n---\n# Title\n"
        meta, _ = parse(text)
        assert meta.success_count == 5
        assert meta.failure_count == 0
        assert meta.last_reflected_at is None

    def test_extra_keys_preserved(self):
        text = (
            "---\n"
            "last_reflected_at: null\n"
            "success_count: 0\n"
            "failure_count: 0\n"
            "authored_by: distill-identity\n"
            "---\n"
            "# Title\n"
        )
        meta, _ = parse(text)
        assert meta.extra == {"authored_by": "distill-identity"}

    def test_malformed_frontmatter_falls_back_to_defaults(self):
        text = "---\ninvalid line without colon\n---\n# Title\n"
        meta, body = parse(text)
        assert meta == SkillMeta()
        assert body == text  # original preserved on parse failure

    def test_unclosed_frontmatter_treated_as_body(self):
        text = "---\nsuccess_count: 2\n# Title\n"
        meta, body = parse(text)
        assert meta == SkillMeta()
        assert body == text

    def test_quoted_string_values_unquoted(self):
        text = (
            "---\n"
            'last_reflected_at: "2026-04-16"\n'
            "success_count: 1\n"
            "failure_count: 0\n"
            "---\n# Title\n"
        )
        meta, _ = parse(text)
        assert meta.last_reflected_at == "2026-04-16"


class TestRender:
    def test_renders_all_fields(self):
        meta = SkillMeta(
            last_reflected_at="2026-04-16T10:00",
            success_count=3,
            failure_count=1,
        )
        out = render(meta, "# Title\n\nbody\n")
        assert out.startswith("---\n")
        assert "2026-04-16T10:00" in out
        assert "success_count: 3" in out
        assert "failure_count: 1" in out
        assert out.endswith("# Title\n\nbody\n")
        re_parsed, _ = parse(out)
        assert re_parsed.last_reflected_at == "2026-04-16T10:00"

    def test_null_rendered_as_null_literal(self):
        meta = SkillMeta()
        out = render(meta, "# Title\n")
        assert "last_reflected_at: null" in out

    def test_extra_keys_round_trip(self):
        meta = SkillMeta(extra={"authored_by": "insight"})
        out = render(meta, "# Title\n")
        assert "authored_by: insight" in out

    def test_round_trip_preserves_meta_and_body(self):
        original = SkillMeta(
            last_reflected_at="2026-04-16T10:00",
            success_count=2,
            failure_count=5,
            extra={"tag": "draft"},
        )
        body = "# Title\n\nbody\n"
        text = render(original, body)
        meta, parsed_body = parse(text)
        assert meta.last_reflected_at == original.last_reflected_at
        assert meta.success_count == original.success_count
        assert meta.failure_count == original.failure_count
        assert meta.extra == original.extra
        assert parsed_body == body


class TestUpdateMeta:
    def test_override_single_field(self):
        meta = SkillMeta(success_count=2, failure_count=1)
        out = update_meta(meta, failure_count=5)
        assert out.success_count == 2
        assert out.failure_count == 5

    def test_preserves_extra(self):
        meta = SkillMeta(extra={"x": "y"})
        out = update_meta(meta, last_reflected_at="2026-04-16T10:00")
        assert out.extra == {"x": "y"}
        assert out.last_reflected_at == "2026-04-16T10:00"


class TestCoerceInt:
    """ADR-0023 / skill_frontmatter.py:47-57 — _coerce_int must absorb every
    primitive the tiny YAML parser can emit. If a path falls through to
    the wrong branch, skill metadata silently flips to ``default`` (0 for
    success/failure counts) and the router mis-ranks skills."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (True, 1),          # bool branch
            (False, 0),         # bool branch (distinct from None)
            (3, 3),             # int branch
            (3.7, 3),           # float branch
            ("5", 5),           # str → int
            ("  7 ", 7),        # str with whitespace
            ("not-a-number", 0),  # str → ValueError → default
            (None, 0),          # fallthrough default
            ([1, 2], 0),        # unexpected type → default
        ],
    )
    def test_covers_every_branch(self, value, expected):
        assert _coerce_int(value) == expected

    def test_explicit_default_used_on_failure(self):
        assert _coerce_int("xxx", default=42) == 42
        assert _coerce_int(None, default=99) == 99


class TestCoerceStrOrNone:
    """ADR-0023 / skill_frontmatter.py:60-68 — _coerce_str_or_none must
    treat YAML null markers as None and coerce unexpected types via
    ``str()`` rather than silently dropping them."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, None),
            ("", None),
            ("  ", None),
            ("null", None),
            ("None", None),
            ("~", None),
            ("2026-04-16", "2026-04-16"),
            ("  spaced  ", "spaced"),
            (42, "42"),           # non-str fallback via str()
        ],
    )
    def test_covers_every_branch(self, value, expected):
        assert _coerce_str_or_none(value) == expected
