#!/usr/bin/env bash
# block-episode-logs-bash.sh — PreToolUse hook for Bash tool
# Block shell commands that read episode log content (prompt injection surface).
set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
[[ -z "$COMMAND" ]] && exit 0

block() {
  echo "{\"decision\": \"block\", \"reason\": \"$1\"}"
  exit 0
}

if echo "$COMMAND" | grep -qE "(\.config/moltbook|MOLTBOOK_HOME)/logs/.*\.jsonl"; then
  block "Episode logs contain raw external agent content (prompt injection risk). Use distilled outputs instead."
fi
if echo "$COMMAND" | grep -qE "\.config/moltbook/logs" && echo "$COMMAND" | grep -qE '(cat|head|tail|less|more|grep|awk|sed|python|ruby)\s'; then
  block "Reading episode log content is blocked (prompt injection risk). Use distilled outputs instead."
fi
