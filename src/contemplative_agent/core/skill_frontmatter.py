"""Skill YAML frontmatter parser/renderer (ADR-0023).

Skills gain optional structured metadata at the top of the file:

    ---
    last_reflected_at: null
    success_count: 0
    failure_count: 0
    ---
    # Title
    <body>

A skill without a frontmatter block is read as if the defaults were
present — the reader-with-defaults pattern keeps legacy ``insight``-
emitted skills working unchanged. Parsing is permissive: unknown keys
are preserved in ``extra`` and round-tripped, and malformed YAML falls
back to "no frontmatter" rather than raising. The system prompt must
never hard-fail on skill formatting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_DELIMITER = "---"


@dataclass(frozen=True)
class SkillMeta:
    """Structured header for a skill file.

    ``extra`` holds any keys we did not promote to named fields; they
    round-trip through parse → render unchanged so external tooling can
    stash its own metadata without being lost.
    """

    last_reflected_at: Optional[str] = None
    success_count: int = 0
    failure_count: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)


def _coerce_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _coerce_str_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "" or stripped.lower() in {"null", "none", "~"}:
            return None
        return stripped
    return str(value)


def _parse_yaml_block(block: str) -> Optional[Dict[str, Any]]:
    """Parse a tiny YAML subset: ``key: value`` lines.

    We deliberately do not pull PyYAML: frontmatter values in this file
    format are primitive scalars (string, int, null). Bespoke parsing
    keeps the dependency surface flat and the failure mode predictable.
    """
    data: Dict[str, Any] = {}
    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            return None  # malformed; caller falls back to defaults
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            return None
        if value == "" or value.lower() in {"null", "none", "~"}:
            data[key] = None
            continue
        if value.lower() == "true":
            data[key] = True
            continue
        if value.lower() == "false":
            data[key] = False
            continue
        try:
            data[key] = int(value)
            continue
        except ValueError:
            pass
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            data[key] = value[1:-1]
        else:
            data[key] = value
    return data


def parse(text: str) -> Tuple[SkillMeta, str]:
    """Split a skill file into (metadata, body).

    Returns defaults and the original text when no parseable frontmatter
    is present; never raises on malformed input.
    """
    if not text:
        return SkillMeta(), ""

    stripped_leading = text.lstrip("\ufeff")  # tolerate BOM
    if not stripped_leading.startswith(_DELIMITER):
        return SkillMeta(), text

    after_open = stripped_leading[len(_DELIMITER):]
    if not after_open.startswith("\n"):
        return SkillMeta(), text
    after_open = after_open[1:]

    close_idx = after_open.find(f"\n{_DELIMITER}")
    if close_idx < 0:
        return SkillMeta(), text
    block = after_open[:close_idx]
    remainder_start = close_idx + len(_DELIMITER) + 1  # past "\n---"
    remainder = after_open[remainder_start:]
    if remainder.startswith("\n"):
        remainder = remainder[1:]

    data = _parse_yaml_block(block)
    if data is None:
        logger.debug("Skill frontmatter unparseable; falling back to defaults.")
        return SkillMeta(), text

    known = {"last_reflected_at", "success_count", "failure_count"}
    extra = {k: v for k, v in data.items() if k not in known}
    meta = SkillMeta(
        last_reflected_at=_coerce_str_or_none(data.get("last_reflected_at")),
        success_count=_coerce_int(data.get("success_count", 0)),
        failure_count=_coerce_int(data.get("failure_count", 0)),
        extra=extra,
    )
    return meta, remainder


def _format_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text != text.strip() or ":" in text or text.lower() in {"null", "none", "~", "true", "false"}:
        escaped = text.replace('"', '\\"')
        return f'"{escaped}"'
    return text


def render(meta: SkillMeta, body: str) -> str:
    """Render a skill file: frontmatter + body (body retains its own title)."""
    lines = [_DELIMITER]
    lines.append(f"last_reflected_at: {_format_value(meta.last_reflected_at)}")
    lines.append(f"success_count: {_format_value(meta.success_count)}")
    lines.append(f"failure_count: {_format_value(meta.failure_count)}")
    for key, value in meta.extra.items():
        lines.append(f"{key}: {_format_value(value)}")
    lines.append(_DELIMITER)
    frontmatter = "\n".join(lines) + "\n"
    body = body.lstrip("\n")
    return frontmatter + body


def update_meta(
    meta: SkillMeta,
    *,
    last_reflected_at: Optional[str] = None,
    success_count: Optional[int] = None,
    failure_count: Optional[int] = None,
) -> SkillMeta:
    """Return a new ``SkillMeta`` with some fields overridden."""
    return SkillMeta(
        last_reflected_at=(
            last_reflected_at
            if last_reflected_at is not None
            else meta.last_reflected_at
        ),
        success_count=(
            success_count if success_count is not None else meta.success_count
        ),
        failure_count=(
            failure_count if failure_count is not None else meta.failure_count
        ),
        extra=dict(meta.extra),
    )
