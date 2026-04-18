"""One-off cleanup for test-leaked episode records.

Background
----------
Several tests (notably tests/test_agent.py::TestRunPostCycle::test_posts_dynamic)
mocked the HTTP client but exercised real memory.record_post() /
episodes.append() code paths. Before tests/conftest.py isolated
MOLTBOOK_HOME (2026-04-14), every test run wrote leaked records to the
production episode log.

Scope
-----
A scan of all 39 log files (2026-03-07 .. 2026-04-14) revealed 2548 records
with test-fixture post_ids (e.g., "new-post-123", "p1"-"p23+", "my-post-1",
"post1", "post2", "new-post-1/2", "dyn-post-1", "fallback-456", etc.). The
2026-04-12 weekly report surfaced only the Apr 7/10/11 subset ("17
placeholder posts"), but pollution dates back to 2026-03-07.

Detection rule: any record whose post_id is a non-empty string that is
NOT a UUID-style identifier is considered test-leaked. All genuine Moltbook
post_ids are UUIDs (32 hex chars, optionally hyphenated). Empty post_ids
(375 records) are NOT removed — they may correspond to genuine API failures
and need separate investigation.

Usage
-----
    python scripts/cleanup_reflective_note_episodes.py --dry-run
    python scripts/cleanup_reflective_note_episodes.py --apply

Backups (.pre-cleanup.bak) are left next to each touched file.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

LOGS_DIR = Path.home() / ".config" / "moltbook" / "logs"

# A genuine Moltbook post_id is a 32-char lowercase hex string, optionally
# in 8-4-4-4-12 UUID form. Anything else with a non-empty post_id is a
# test fixture.
_UUID_RE = re.compile(r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$")
_HEX_RE = re.compile(r"^[0-9a-f]{24,}$")


def is_genuine_post_id(pid: Any) -> bool:
    if not isinstance(pid, str) or not pid:
        return False  # empty post_id is ambiguous — caller decides
    return bool(_UUID_RE.match(pid) or _HEX_RE.match(pid))


def is_test_leak(rec: dict[str, Any]) -> bool:
    """True iff record is a test-leaked record.

    We only inspect records whose data has a non-empty post_id that isn't
    UUID-shaped. Records without post_id (e.g., insights, distillations,
    session summaries) are left alone. Records with empty post_id are also
    left alone — those may be genuine API failures.
    """
    data = rec.get("data") or {}
    pid = data.get("post_id")
    if not isinstance(pid, str) or not pid:
        return False
    return not is_genuine_post_id(pid)


def process_file(path: Path, apply: bool) -> tuple[int, int]:
    """Return (removed, kept) counts for one file."""
    removed = 0
    kept_lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            kept_lines.append(line)
            continue
        try:
            rec = json.loads(stripped)
        except json.JSONDecodeError:
            kept_lines.append(line)
            continue
        if isinstance(rec, dict) and is_test_leak(rec):
            removed += 1
        else:
            kept_lines.append(line)
    if apply and removed:
        bak = path.with_suffix(".jsonl.pre-cleanup.bak")
        if not bak.exists():  # don't clobber an earlier backup
            shutil.copy2(path, bak)
        path.write_text(
            "\n".join(kept_lines) + ("\n" if kept_lines else ""),
            encoding="utf-8",
        )
    return removed, len(kept_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report counts without writing",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually remove the records (creates .pre-cleanup.bak)",
    )
    args = parser.parse_args()
    if args.dry_run == args.apply:
        parser.error("pass exactly one of --dry-run / --apply")

    total_removed = 0
    touched = 0
    for path in sorted(LOGS_DIR.glob("*.jsonl")):
        if path.name == "audit.jsonl":
            continue
        removed, kept = process_file(path, apply=args.apply)
        if removed == 0:
            continue
        touched += 1
        total_removed += removed
        action = "would remove" if args.dry_run else "removed"
        print(f"{path.stem}: {action} {removed:>4} buggy records, kept {kept:>4} lines")

    print(f"\nTotal: {total_removed} records {'would be removed' if args.dry_run else 'removed'} across {touched} files")
    if args.apply and total_removed:
        print("Backups saved as *.pre-cleanup.bak next to each touched file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
