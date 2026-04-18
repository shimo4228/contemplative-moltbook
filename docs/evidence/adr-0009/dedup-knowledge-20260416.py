"""One-shot dedup for knowledge.json entries duplicated by the load() bug.

Background: KnowledgeStore.load() used to append without reset, and three
CLI handlers (distill / distill-identity / insight) called load() at both
the CLI layer and the core-function layer. A save() after a double-load
persisted the doubled list. As of the fix commit, load() is idempotent,
but production knowledge.json files created before the fix may still
contain the duplicated pairs. This script removes them.

The script runs in dry-run mode by default. Use --apply to modify disk.

Strategy
--------

Group entries by (pattern_text, valid_from).

- Groups of size 1: legitimate unique pattern, keep as-is.
- Groups of size 2+ with identical valid_from: classic double-save
  fingerprint. Merge into one entry: sum counters, max timestamps /
  strength, union provenance.source_episode_ids, prefer richer fields.
- Groups of size 2+ with DIFFERENT valid_from: legitimate revision trail
  from ADR-0022 memory evolution. Leave untouched.

Atomic write via .tmp rename. Original backed up to knowledge.json.bak.dedup-<UTC>.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def _merge_pair(entries: list[dict]) -> dict:
    """Merge a duplicate group into a single entry.

    Non-counter fields come from the first entry (they are identical by
    construction — same pattern text, same valid_from). Counters are
    summed and timestamps maxed to preserve activity history across
    the duplicates.
    """
    base = dict(entries[0])

    def _sum_field(name: str) -> int:
        total = 0
        for e in entries:
            v = e.get(name, 0)
            if isinstance(v, int):
                total += v
        return total

    def _max_field(name: str) -> str | None:
        values = [e.get(name) for e in entries if e.get(name)]
        return max(values) if values else None

    def _max_float(name: str, default: float) -> float:
        values = [float(e.get(name, default)) for e in entries if name in e]
        return max(values) if values else default

    base["access_count"] = _sum_field("access_count")
    base["success_count"] = _sum_field("success_count")
    base["failure_count"] = _sum_field("failure_count")

    last_accessed = _max_field("last_accessed_at")
    if last_accessed is not None:
        base["last_accessed_at"] = last_accessed

    if any("strength" in e for e in entries):
        base["strength"] = _max_float("strength", 1.0)

    source_ids: set = set()
    for e in entries:
        prov = e.get("provenance") or {}
        ids = prov.get("source_episode_ids") or []
        source_ids.update(ids)
    if source_ids and isinstance(base.get("provenance"), dict):
        base["provenance"] = dict(base["provenance"])
        base["provenance"]["source_episode_ids"] = sorted(source_ids)

    return base


def dedup(path: Path, *, apply: bool) -> int:
    with path.open(encoding="utf-8") as fh:
        patterns = json.load(fh)

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for entry in patterns:
        key = (entry.get("pattern", ""), entry.get("valid_from", ""))
        groups[key].append(entry)

    kept: list[dict] = []
    merged_pairs = 0
    legit_revisions = 0
    unique_count = 0

    for key, entries in groups.items():
        if len(entries) == 1:
            kept.append(entries[0])
            unique_count += 1
            continue
        pattern_text, valid_from = key
        if all(e.get("valid_from") == valid_from for e in entries):
            kept.append(_merge_pair(entries))
            merged_pairs += 1
        else:
            kept.extend(entries)
            legit_revisions += len(entries)

    removed = len(patterns) - len(kept)

    print(f"{'APPLY' if apply else 'DRY-RUN'}: {path}")
    print(f"  before: {len(patterns)} entries")
    print(f"  unique groups: {unique_count}")
    print(f"  duplicate-by-valid_from groups merged: {merged_pairs}")
    print(f"  legitimate revision entries (valid_from differs): {legit_revisions}")
    print(f"  after: {len(kept)} entries (removed {removed})")

    if not apply:
        print("  (dry-run: no files modified)")
        return 0

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    backup = path.with_suffix(f".json.bak.dedup-{ts}")
    shutil.copy2(path, backup)
    print(f"  backup: {backup}")

    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(kept, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    print(f"  wrote: {path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=Path.home() / ".config/moltbook/knowledge.json",
        help="Path to knowledge.json (default: ~/.config/moltbook/knowledge.json)",
    )
    p.add_argument("--apply", action="store_true", help="Modify files. Default is dry-run.")
    args = p.parse_args()

    if not args.path.exists():
        print(f"error: {args.path} does not exist", file=sys.stderr)
        return 1

    return dedup(args.path, apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
