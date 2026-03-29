#!/bin/bash
# Install -ca skills as Cursor rules
# Usage: bash integrations/cursor/install.sh (from repo root)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/../skills"
TARGET_DIR=".cursor/rules"

mkdir -p "$TARGET_DIR"

# Strip YAML frontmatter (first --- to second --- inclusive)
strip_frontmatter() {
    awk 'BEGIN{fm=0} /^---$/ && fm==0{fm=1; next} /^---$/ && fm==1{fm=2; next} fm==2' "$1"
}

count=0
for skill in "$SKILLS_DIR"/*-ca.md; do
    basename="$(basename "$skill" .md)"
    target="$TARGET_DIR/$basename.mdc"

    description=$(sed -n 's/^description: *"\(.*\)"/\1/p' "$skill" | head -1)
    if [ -z "$description" ]; then
        echo "  WARNING: no description found in $(basename "$skill"), skipping"
        continue
    fi

    {
        echo "---"
        printf 'description: "%s"\n' "$description"
        echo "globs: []"
        echo "alwaysApply: false"
        echo "---"
        echo ""
        strip_frontmatter "$skill"
    } > "$target"

    echo "  Installed: $basename.mdc"
    count=$((count + 1))
done

echo ""
echo "$count rules installed to $TARGET_DIR/"
echo "Mention the skill name in conversation or use @rules to activate."
