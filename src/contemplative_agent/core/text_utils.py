"""Markdown text helpers shared by insight / rules-distill / stocktake / cli.

Promoted from `core/insight.py` and `core/rules_distill.py` in ADR-0035 PR2.
The promotion breaks the `stocktake → rules_distill` import edge that
existed only because `_strip_frontmatter` lived in `rules_distill.py`.

These are deterministic string transforms with no LLM dependency. They
sit at `core/` (not `_io.py`) because they are content-level rather than
I/O-level — slugifying a title is logically closer to what insight /
rules_distill produce than to how files are written.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

MAX_SLUG_LENGTH = 50


def slugify(title: str) -> str:
    """Convert a title to a filesystem-safe slug.

    NFKD-normalises Unicode, lowercases, replaces non-alphanumeric runs
    with single hyphens, trims leading/trailing hyphens, and caps at
    ``MAX_SLUG_LENGTH``. Returns an empty string when *title* contains
    no usable characters.
    """
    normalized = unicodedata.normalize("NFKD", title)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug[:MAX_SLUG_LENGTH]


def extract_title(body: str) -> Optional[str]:
    """Return the first ``# `` heading text, or ``None`` when absent.

    Used by insight, rules-distill, and the stocktake merge writer to
    derive a stable filename from generated artifact bodies.
    """
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def strip_frontmatter(text: str) -> str:
    """Strip a leading YAML frontmatter block (``---`` delimited).

    Returns *text* unchanged when there is no frontmatter. Used by
    rules-distill (skill input parsing) and stocktake (skill body
    comparison).
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return text
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[i + 1 :]).lstrip("\n")
    return text
