#!/bin/bash
# Install -ca skills for OpenAI Codex
# Usage: bash integrations/codex/install.sh (from repo root)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/../skills"
TARGET_DIR=".agents/skills"

mkdir -p "$TARGET_DIR"

count=0
for skill_dir in "$SKILLS_DIR"/*-ca; do
    [ -d "$skill_dir" ] || continue
    cp -r "$skill_dir" "$TARGET_DIR/"
    echo "  Installed: $(basename "$skill_dir")/"
    count=$((count + 1))
done

echo ""
echo "$count skills installed to $TARGET_DIR/"
echo "Available as skills in Codex CLI."
