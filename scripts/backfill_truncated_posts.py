"""Backfill truncated original_post fields in episode logs.

Reads all .jsonl logs, finds entries where original_post was truncated
at 500 chars, fetches the full post content from the Moltbook API,
and writes corrected logs (preserving originals as .jsonl.bak).

Usage:
    uv run python scripts/backfill_truncated_posts.py [--dry-run]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

LOG_DIR = Path.home() / ".config" / "moltbook" / "logs"
CREDENTIALS_PATH = Path.home() / ".config" / "moltbook" / "credentials.json"
API_BASE = "https://www.moltbook.com/api/v1"
TRUNCATION_THRESHOLD = 490  # Posts >= this length were likely truncated at 500
REQUEST_INTERVAL = 1.5  # seconds between API calls (stay under 60 req/min)


def load_api_key() -> str:
    data = json.loads(CREDENTIALS_PATH.read_text())
    return data["api_key"]


def fetch_post_content(post_id: str, api_key: str) -> str | None:
    """Fetch full post content from Moltbook API."""
    url = f"{API_BASE}/posts/{post_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.get(url, headers=headers, timeout=30, allow_redirects=False)
        if resp.status_code == 200:
            data = resp.json()
            post = data.get("post", data)
            return post.get("content", post.get("body", ""))
        elif resp.status_code == 404:
            return None
        else:
            print(f"  WARNING: {post_id} returned {resp.status_code}")
            return None
    except requests.RequestException as e:
        print(f"  ERROR: {post_id}: {e}")
        return None


def process_log_file(log_path: Path, api_key: str, dry_run: bool) -> tuple[int, int]:
    """Process a single log file. Returns (found, updated) counts."""
    lines = log_path.read_text().splitlines()
    found = 0
    updated = 0
    new_lines = []

    for line in lines:
        record = json.loads(line)
        data = record.get("data", {})
        original_post = data.get("original_post", "")
        post_id = data.get("post_id", "")

        if original_post and post_id and len(original_post) >= TRUNCATION_THRESHOLD:
            found += 1
            if not dry_run:
                full_content = fetch_post_content(post_id, api_key)
                if full_content and len(full_content) > len(original_post):
                    data["original_post"] = full_content
                    record["data"] = data
                    updated += 1
                    print(f"  Updated {post_id[:12]}... ({len(original_post)} -> {len(full_content)} chars)")
                    time.sleep(REQUEST_INTERVAL)
                else:
                    time.sleep(REQUEST_INTERVAL)

        new_lines.append(json.dumps(record, ensure_ascii=False))

    if not dry_run and updated > 0:
        # Backup original
        backup_path = log_path.with_suffix(".jsonl.bak")
        if not backup_path.exists():
            log_path.rename(backup_path)
            print(f"  Backed up to {backup_path.name}")
        else:
            print(f"  Backup already exists, overwriting log")

        log_path.write_text("\n".join(new_lines) + "\n")

    return found, updated


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("DRY RUN — no changes will be made\n")
    else:
        api_key = load_api_key()

    log_files = sorted(LOG_DIR.glob("*.jsonl"))
    total_found = 0
    total_updated = 0

    for log_path in log_files:
        if log_path.suffix == ".bak":
            continue
        print(f"\n{log_path.name}:")
        if dry_run:
            # Just count
            found = 0
            for line in log_path.read_text().splitlines():
                r = json.loads(line)
                d = r.get("data", {})
                op = d.get("original_post", "")
                if op and d.get("post_id") and len(op) >= TRUNCATION_THRESHOLD:
                    found += 1
            print(f"  {found} truncated posts")
            total_found += found
        else:
            found, updated = process_log_file(log_path, api_key, dry_run)
            total_found += found
            total_updated += updated
            print(f"  {found} found, {updated} updated")

    print(f"\nTotal: {total_found} truncated, {total_updated} updated")
    if total_found > 0 and not dry_run:
        estimated_time = total_found * REQUEST_INTERVAL
        print(f"(API calls took ~{estimated_time:.0f}s)")


if __name__ == "__main__":
    main()
