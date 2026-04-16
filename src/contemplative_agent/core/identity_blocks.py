"""Identity block parser/renderer (ADR-0024).

Identity files gain an optional YAML-frontmatter block list::

    ---
    blocks:
      - name: persona_core
        last_updated_at: 2026-04-16T10:00:00+00:00
        source: distill-identity
      - name: current_goals
        last_updated_at: 2026-04-16T10:00:00+00:00
        source: agent-edit
    ---

    ## persona_core

    I'm an AI agent exploring ...

    ## current_goals

    Running experiments with ...

Files without the ``---`` opener are treated as **legacy**: a single
``persona_core`` block whose body is the whole file. ``render()`` of a
legacy document returns the original bytes unchanged, so existing 11
templates keep working with zero migration.

Parser is stdlib-only; malformed frontmatter silently degrades to
legacy mode rather than raising (ADR-0024: "a corrupted identity.md
should degrade, not take the agent offline").
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

KNOWN_SOURCES = frozenset(
    {"distill-identity", "agent-edit", "migration", "template", "legacy"}
)
DEFAULT_SOURCE = "legacy"

PERSONA_CORE_BLOCK = "persona_core"

_FRONTMATTER_DELIM = "---"
_SECTION_HEADER_RE = re.compile(r"^##\s+([A-Za-z0-9_][A-Za-z0-9_\-]*)\s*$")

_PROMPT_CACHE: Optional[Tuple[Path, float, str]] = None


@dataclass(frozen=True)
class Block:
    """One named section of an identity document.

    ``extra`` preserves any frontmatter keys we do not recognise, so
    round-tripping an edited file never silently drops metadata added
    by a future version of the writer.
    """

    name: str
    body: str
    last_updated_at: Optional[str] = None
    source: str = DEFAULT_SOURCE
    extra: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class IdentityDocument:
    blocks: Tuple[Block, ...]
    is_legacy: bool

    def get(self, name: str) -> Optional[Block]:
        for b in self.blocks:
            if b.name == name:
                return b
        return None


def parse(text: str) -> IdentityDocument:
    """Parse identity text into a document.

    Legacy files (no ``---`` opener) return a single ``persona_core``
    block carrying the whole text. Malformed frontmatter also
    degrades to legacy rather than raising.
    """
    if not text:
        return IdentityDocument(
            blocks=(Block(name=PERSONA_CORE_BLOCK, body="", source=DEFAULT_SOURCE),),
            is_legacy=True,
        )

    stripped = text.lstrip("\n")
    if not stripped.startswith(_FRONTMATTER_DELIM):
        return _legacy_doc(text)

    lines = stripped.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_DELIM:
        return _legacy_doc(text)

    end_idx = _find_frontmatter_end(lines)
    if end_idx is None:
        return _legacy_doc(text)

    fm_lines = lines[1:end_idx]
    try:
        frontmatter_blocks = _parse_frontmatter_blocks(fm_lines)
    except _FrontmatterError as exc:
        logger.warning("identity frontmatter malformed, falling back to legacy: %s", exc)
        return _legacy_doc(text)

    body = "\n".join(lines[end_idx + 1 :]).lstrip("\n")
    sections = _split_sections(body)

    blocks: List[Block] = []
    for fm in frontmatter_blocks:
        name = fm["name"]
        blocks.append(
            Block(
                name=name,
                body=sections.get(name, "").rstrip() + ("\n" if sections.get(name) else ""),
                last_updated_at=_optional_str(fm.get("last_updated_at")),
                source=_coerce_source(fm.get("source")),
                extra=_extract_extras(fm),
            )
        )

    # If frontmatter parsed successfully but claimed no blocks, treat as
    # legacy — otherwise we would return an empty document and the prompt
    # build would go blank.
    if not blocks:
        return _legacy_doc(text)

    return IdentityDocument(blocks=tuple(blocks), is_legacy=False)


def render(doc: IdentityDocument) -> str:
    """Render a document back to text.

    Legacy documents render as just the body of their single block, so
    round-tripping a plain-text identity.md produces the original
    bytes (up to trailing newline normalisation).
    """
    if doc.is_legacy:
        if not doc.blocks:
            return ""
        return _ensure_trailing_newline(doc.blocks[0].body)

    out: List[str] = [_FRONTMATTER_DELIM, "blocks:"]
    for b in doc.blocks:
        out.append(f"  - name: {b.name}")
        if b.last_updated_at is not None:
            out.append(f"    last_updated_at: {b.last_updated_at}")
        out.append(f"    source: {b.source}")
        for k, v in b.extra.items():
            out.append(f"    {k}: {v}")
    out.append(_FRONTMATTER_DELIM)
    out.append("")

    for b in doc.blocks:
        out.append(f"## {b.name}")
        out.append("")
        body = b.body.strip("\n")
        if body:
            out.append(body)
        out.append("")

    return "\n".join(out).rstrip("\n") + "\n"


def update_block(
    doc: IdentityDocument,
    name: str,
    *,
    body: str,
    source: str,
    now: Optional[str] = None,
) -> IdentityDocument:
    """Return a new document with ``name``'s body replaced.

    If the document is legacy and ``name == "persona_core"``, the
    document stays legacy — the writer preserves the file's current
    format. Migration to block mode is explicit via
    :func:`migrate_to_blocks`.
    """
    if source not in KNOWN_SOURCES:
        raise ValueError(
            f"unknown source {source!r}; must be one of {sorted(KNOWN_SOURCES)}"
        )

    ts = now or _now_iso()
    updated_body = _ensure_trailing_newline(body.strip())

    if doc.is_legacy:
        if name != PERSONA_CORE_BLOCK:
            raise ValueError(
                "legacy identity file only supports the persona_core block; "
                "run migrate_to_blocks() first to add additional blocks"
            )
        return IdentityDocument(
            blocks=(
                Block(
                    name=PERSONA_CORE_BLOCK,
                    body=updated_body,
                    last_updated_at=None,
                    source=DEFAULT_SOURCE,
                ),
            ),
            is_legacy=True,
        )

    new_blocks: List[Block] = []
    replaced = False
    for b in doc.blocks:
        if b.name == name:
            new_blocks.append(
                Block(
                    name=b.name,
                    body=updated_body,
                    last_updated_at=ts,
                    source=source,
                    extra=b.extra,
                )
            )
            replaced = True
        else:
            new_blocks.append(b)

    if not replaced:
        new_blocks.append(
            Block(
                name=name,
                body=updated_body,
                last_updated_at=ts,
                source=source,
            )
        )

    return IdentityDocument(blocks=tuple(new_blocks), is_legacy=False)


def load_for_prompt(path: Path) -> str:
    """Read an identity file and return the text to splice into the prompt.

    Legacy files return verbatim bytes (compat with pre-ADR-0024
    behaviour). Block-format files return block bodies concatenated
    with blank-line separators. Frontmatter is never returned.

    Result is cached by ``(path, mtime)`` so the LLM hot path (one
    ``_build_system_prompt`` call per generate) does not re-parse
    identity.md on every invocation. Invalidated automatically on
    file edit via mtime bump.
    """
    global _PROMPT_CACHE
    if not path.exists():
        _PROMPT_CACHE = None
        return ""
    try:
        mtime = path.stat().st_mtime
    except OSError as exc:
        logger.warning("failed to stat identity file %s: %s", path, exc)
        return ""

    if (
        _PROMPT_CACHE is not None
        and _PROMPT_CACHE[0] == path
        and _PROMPT_CACHE[1] == mtime
    ):
        return _PROMPT_CACHE[2]

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("failed to read identity file %s: %s", path, exc)
        return ""

    doc = parse(raw)
    if doc.is_legacy:
        result = raw.strip()
    else:
        parts = [b.body.strip() for b in doc.blocks if b.body.strip()]
        result = "\n\n".join(parts)

    _PROMPT_CACHE = (path, mtime, result)
    return result


def body_hash(body: str) -> str:
    """16-hex-char SHA-256 prefix, for the history log."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class MigrationResult:
    migrated: bool
    already_migrated: bool = False
    backup_path: Optional[Path] = None
    rendered: Optional[str] = None
    document: Optional[IdentityDocument] = None


def migrate_to_blocks(
    path: Path,
    *,
    now: Optional[str] = None,
) -> MigrationResult:
    """Migrate a legacy plain-text identity file to block format.

    Writes ``<path>.bak.pre-adr0024`` first, then rewrites ``path``
    with a single ``persona_core`` block carrying the original body.
    Idempotent: returns ``already_migrated=True`` without touching
    anything if the file already has frontmatter.

    Returns the rendered post-migration text and the resulting
    document so callers can audit or inspect without re-reading and
    re-parsing the file from disk.
    """
    if not path.exists():
        return MigrationResult(migrated=False)

    raw = path.read_text(encoding="utf-8")
    doc = parse(raw)
    if not doc.is_legacy:
        return MigrationResult(migrated=False, already_migrated=True)

    backup = path.with_suffix(path.suffix + ".bak.pre-adr0024")
    backup.write_text(raw, encoding="utf-8")

    migrated = IdentityDocument(
        blocks=(
            Block(
                name=PERSONA_CORE_BLOCK,
                body=_ensure_trailing_newline(raw.strip()),
                last_updated_at=now or _now_iso(),
                source="migration",
            ),
        ),
        is_legacy=False,
    )
    rendered = render(migrated)
    _write_text_preserving_mode(path, rendered)
    return MigrationResult(
        migrated=True,
        backup_path=backup,
        rendered=rendered,
        document=migrated,
    )


def append_history(
    history_path: Path,
    *,
    block: str,
    old_body: str,
    new_body: str,
    source: str,
    now: Optional[str] = None,
) -> None:
    """Append a compact history record for a block change.

    Records only SHA-256 prefixes of old/new bodies — full-text recovery
    is the snapshot subsystem's job (ADR-0020).
    """
    entry = {
        "ts": now or _now_iso(),
        "block": block,
        "source": source,
        "old_hash": body_hash(old_body),
        "new_hash": body_hash(new_body),
    }
    history_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    with history_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    try:
        history_path.chmod(0o600)
    except OSError:
        # chmod can fail on exotic filesystems; history still written.
        pass


# ---------------------------------------------------------------- helpers


def _legacy_doc(text: str) -> IdentityDocument:
    return IdentityDocument(
        blocks=(
            Block(
                name=PERSONA_CORE_BLOCK,
                body=_ensure_trailing_newline(text.strip()),
                source=DEFAULT_SOURCE,
            ),
        ),
        is_legacy=True,
    )


def _ensure_trailing_newline(s: str) -> str:
    if not s:
        return ""
    return s if s.endswith("\n") else s + "\n"


def _find_frontmatter_end(lines: List[str]) -> Optional[int]:
    for i in range(1, len(lines)):
        if lines[i].strip() == _FRONTMATTER_DELIM:
            return i
    return None


class _FrontmatterError(Exception):
    pass


def _parse_frontmatter_blocks(lines: List[str]) -> List[Dict[str, str]]:
    """Parse the narrow YAML subset ADR-0024 commits to.

    Accepts exactly::

        blocks:
          - name: <v>
            <k>: <v>
            ...
          - name: <v>
            ...
    """
    non_empty = [ln for ln in lines if ln.strip()]
    if not non_empty:
        raise _FrontmatterError("empty frontmatter")
    if non_empty[0].strip() != "blocks:":
        raise _FrontmatterError(
            "expected 'blocks:' marker as first non-empty frontmatter line"
        )

    items: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None
    for raw in non_empty[1:]:
        line = raw.rstrip()
        if line.startswith("  - "):
            # new list item; first field must be "name"
            current = {}
            key, value = _split_kv(line[4:])
            if key != "name":
                raise _FrontmatterError(
                    f"expected first item field to be 'name', got {key!r}"
                )
            current["name"] = value
            items.append(current)
        elif line.startswith("    ") and current is not None:
            key, value = _split_kv(line.strip())
            current[key] = value
        else:
            raise _FrontmatterError(f"unexpected frontmatter line: {raw!r}")

    for item in items:
        if "name" not in item or not item["name"]:
            raise _FrontmatterError("block missing name")

    return items


def _split_kv(s: str) -> Tuple[str, str]:
    if ":" not in s:
        raise _FrontmatterError(f"missing ':' in field: {s!r}")
    key, _, value = s.partition(":")
    key = key.strip()
    value = value.strip()
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        value = value[1:-1]
    elif value.startswith("'") and value.endswith("'") and len(value) >= 2:
        value = value[1:-1]
    return key, value


def _split_sections(body: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current_name: Optional[str] = None
    buf: List[str] = []
    for line in body.splitlines():
        m = _SECTION_HEADER_RE.match(line)
        if m is not None:
            if current_name is not None:
                sections[current_name] = _join_and_strip(buf)
            current_name = m.group(1)
            buf = []
        else:
            if current_name is not None:
                buf.append(line)
    if current_name is not None:
        sections[current_name] = _join_and_strip(buf)
    return sections


def _join_and_strip(lines: Iterable[str]) -> str:
    joined = "\n".join(lines).strip("\n")
    return joined


def _optional_str(v: object) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in {"null", "none", "~"}:
        return None
    return s


def _coerce_source(v: object) -> str:
    s = _optional_str(v)
    if s is None:
        return DEFAULT_SOURCE
    if s not in KNOWN_SOURCES:
        logger.warning("unknown identity block source %r, treating as legacy", s)
        return DEFAULT_SOURCE
    return s


_RESERVED_KEYS = frozenset({"name", "last_updated_at", "source"})


def _extract_extras(fm: Mapping[str, str]) -> Dict[str, str]:
    return {k: v for k, v in fm.items() if k not in _RESERVED_KEYS}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_text_preserving_mode(path: Path, content: str) -> None:
    """Write text to ``path``. Preserves 0600 perm if the file was 0600."""
    original_mode: Optional[int] = None
    if path.exists():
        try:
            original_mode = path.stat().st_mode & 0o777
        except OSError:
            original_mode = None
    path.write_text(content, encoding="utf-8")
    if original_mode is not None:
        try:
            path.chmod(original_mode)
        except OSError:
            pass
