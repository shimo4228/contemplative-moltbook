#!/bin/bash
# Install Claude Code safety hooks for Contemplative Agent
#
# Blocks coding agents from reading raw episode logs (prompt injection surface).
# See docs/security/ for the full threat model.
#
# Usage: bash integrations/claude-code/install-hooks.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOKS_SRC="$SCRIPT_DIR/hooks"
HOOKS_DST="$HOME/.claude/hooks"

mkdir -p "$HOOKS_DST"

echo "Installing episode log protection hooks..."
echo ""

count=0
for hook in "$HOOKS_SRC"/block-episode-logs-*.sh; do
    [ -f "$hook" ] || continue
    name=$(basename "$hook")
    cp "$hook" "$HOOKS_DST/$name"
    chmod +x "$HOOKS_DST/$name"
    echo "  Installed: $HOOKS_DST/$name"
    count=$((count + 1))
done

echo ""
echo "$count hooks installed to $HOOKS_DST/"
echo ""
echo "Next step: add these entries to ~/.claude/settings.json"
echo "under \"hooks\" > \"PreToolUse\":"
echo ""
cat <<'SNIPPET'
{
  "matcher": "Read",
  "hooks": [{ "type": "command", "command": "bash ~/.claude/hooks/block-episode-logs-read.sh" }]
},
{
  "matcher": "Bash",
  "hooks": [{ "type": "command", "command": "bash ~/.claude/hooks/block-episode-logs-bash.sh" }]
},
{
  "matcher": "Grep",
  "hooks": [{ "type": "command", "command": "bash ~/.claude/hooks/block-episode-logs-grep.sh" }]
}
SNIPPET
echo ""
echo "If you already have a Bash PreToolUse hook, merge the episode"
echo "log check into your existing script instead of adding a new entry."
