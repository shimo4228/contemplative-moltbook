"""Shared file I/O utilities for core modules.

Provides restricted-permission file writes, JSONL append, UTC timestamp,
and text truncation helpers used across core / adapters.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


SUMMARY_MAX_LENGTH = 200


def truncate(text: str, max_length: int = SUMMARY_MAX_LENGTH) -> str:
    """Truncate text to max_length, appending '...' if trimmed."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def strip_code_fence(text: str) -> str:
    """Remove markdown code fences (```json ... ```) from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def write_restricted(path: Path, content: str) -> None:
    """Write content to a file with 0600 permissions from creation.

    Uses umask to ensure the file is never world-readable, even briefly.
    Note: os.umask() is process-wide and not thread-safe.
    """
    old_umask = os.umask(0o177)
    try:
        path.write_text(content, encoding="utf-8")
    finally:
        os.umask(old_umask)


def append_jsonl_restricted(path: Path, record: Dict[str, Any]) -> None:
    """Append one JSON record to a JSONL file with 0600 permissions.

    Creates the parent directory if missing. Serialises with
    ``ensure_ascii=False`` so unicode content stays readable in the log.
    Unlike ``write_restricted`` this opens in append mode, so the umask
    only affects files that do not exist yet — pre-existing files keep
    their current permission bits.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    old_umask = os.umask(0o177)
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    finally:
        os.umask(old_umask)


def now_iso(timespec: str = "minutes") -> str:
    """UTC ISO timestamp. Defaults to minutes precision.

    Centralises timestamp formatting so audit / frontmatter / log writers
    produce aligned strings. Callers that need finer-grained timestamps
    (e.g. audit log) pass ``timespec="seconds"``.
    """
    return datetime.now(timezone.utc).isoformat(timespec=timespec)


