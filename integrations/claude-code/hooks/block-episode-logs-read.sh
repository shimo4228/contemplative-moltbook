#!/usr/bin/env bash
# block-episode-logs-read.sh — PreToolUse hook for Read tool
# Block direct reads of episode logs (prompt injection surface).
# Use distilled outputs instead: knowledge.json, identity.md, reports/.
set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[[ -z "$FILE_PATH" ]] && exit 0

MOLTBOOK_LOGS="${MOLTBOOK_HOME:-$HOME/.config/moltbook}/logs"

case "$FILE_PATH" in
  "$MOLTBOOK_LOGS"/*.jsonl|*".config/moltbook/logs/"*.jsonl)
    echo "{\"decision\": \"block\", \"reason\": \"Episode logs contain raw external agent content (prompt injection risk). Use distilled outputs instead: knowledge.json, identity.md, reports/.\"}"
    ;;
esac
