#!/usr/bin/env bash
# block-episode-logs-grep.sh — PreToolUse hook for Grep tool
# Block content searches targeting episode logs (prompt injection surface).
set -euo pipefail

INPUT=$(cat)
SEARCH_PATH=$(echo "$INPUT" | jq -r '.tool_input.path // empty')
GLOB_PATTERN=$(echo "$INPUT" | jq -r '.tool_input.glob // empty')

[[ -z "$SEARCH_PATH" ]] && [[ -z "$GLOB_PATTERN" ]] && exit 0

case "$SEARCH_PATH" in
  *".config/moltbook/logs"*|*"MOLTBOOK_HOME/logs"*)
    echo "{\"decision\": \"block\", \"reason\": \"Episode logs contain raw external agent content (prompt injection risk). Use distilled outputs instead.\"}"
    exit 0
    ;;
esac

case "$GLOB_PATTERN" in
  *".jsonl"*)
    if [[ "$SEARCH_PATH" == *"logs"* ]] || [[ -z "$SEARCH_PATH" ]]; then
      echo "{\"decision\": \"block\", \"reason\": \"Episode logs contain raw external agent content (prompt injection risk). Use distilled outputs instead.\"}"
      exit 0
    fi
    ;;
esac
