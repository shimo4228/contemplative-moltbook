#!/usr/bin/env bash
# Launch a fresh Claude Code session in tmux to plan + implement one phase
# of the ADR-0021..0024 pattern-memory extension roadmap.
#
# Usage:
#   ./scripts/launch-phase.sh 2            # Phase 2 (ADR-0022)
#   ./scripts/launch-phase.sh 3            # Phase 3 (ADR-0023)
#   ./scripts/launch-phase.sh 4            # Phase 4 (ADR-0024)
#
# The session starts in Plan Mode with a prompt that points the new
# Claude at:
#   - ~/.claude/plans/unified-booping-snowflake.md  (master plan)
#   - docs/adr/0021-*.md + prior ADRs               (what's done)
#   - .reports/phase-{N-1}-report.md                (last phase summary)
# and asks it to draft ADR-00(20+N), implement, verify, and commit.

set -euo pipefail

PHASE="${1:-}"
if [[ -z "$PHASE" ]] || ! [[ "$PHASE" =~ ^[2-4]$ ]]; then
    echo "Usage: $0 <phase_number>  (2, 3, or 4)" >&2
    exit 1
fi

REPO="/Users/shimomoto_tatsuya/MyAI_Lab/contemplative-moltbook"
ADR_NUM="$((20 + PHASE))"           # 22 / 23 / 24
PREV_PHASE="$((PHASE - 1))"
SESSION="cm-phase${PHASE}"

# Phase-specific focus lines. Keep descriptions terse — the full plan
# lives in the unified plan file.
case "$PHASE" in
    2) FOCUS="Phase 2 — IV-4 (Memory Evolution, A-Mem bidirectional update) + IV-5 (Hybrid Retrieval, BM25 augmentation). Target ADR-0022." ;;
    3) FOCUS="Phase 3 — IV-9 (Skill-as-Memory loop: skill router + reflective write + usage log). Target ADR-0023." ;;
    4) FOCUS="Phase 4 — IV-6 (Identity block separation, Letta-style editable blocks). Target ADR-0024." ;;
esac

# Write the initial prompt to a temp file. Passing a large multi-line
# string as a positional arg through `tmux new-session "claude \"…\""`
# breaks on quoting / locale; a file round-trip is stable.
PROMPT_FILE="$(mktemp -t "cm-phase${PHASE}-prompt-XXXXXX")"
cat > "$PROMPT_FILE" <<EOF
Phase ${PHASE} を開始します。

## 参照ドキュメント（必ず最初に読むこと）

1. ~/.claude/plans/unified-booping-snowflake.md — 4 フェーズ全体のマスタープラン
2. docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md — Phase 1 で書いた ADR
3. .reports/phase-${PREV_PHASE}-report.md — 直前フェーズの実装サマリ
4. docs/adr/README.md — ADR index で既存の 0001-0021 の要点を把握

## このセッションの焦点

${FOCUS}

次 ADR は ADR-00${ADR_NUM}。先行 ADR (0021) と整合するように設計する。

## 進め方（前フェーズと同じ流れ）

1. **Plan Mode** で入る。まず Explore agent で現状 Phase 1 実装の該当箇所を確認。
2. Plan 書き、ユーザー確認 → ExitPlanMode。
3. ADR-00${ADR_NUM} 起草（問題 / 決定 / 代替案 / 結果）。
4. 実装 (targeted tests TDD, 既存テスト破壊しない)。
5. \`uv run pytest tests/<関連>.py -v\` で合格。
6. \`.reports/phase-${PHASE}-report.md\` 作成。
7. \`feat(<scope>):\` コミット。Attribution は無効なので Co-Authored-By は不要。
8. セッション終了を報告。

## 重要な前提

- メカニズムは論文アルゴリズムを自前写経 (Mem0 等の丸ごと依存は却下, 既に ADR-0021 で確定)
- ADR-0015 (1 外部アダプタ) と承認ゲート方針を尊重
- long-running-test-discipline に従う: 変更範囲を見てから targeted/full を決める
- prototype-before-scale: フル実行前に 3-5 件 smoke
- no-numeric-caps: LLM 出力に max_rules=N 型 quality filter を使わない
- no-delete-episodes: エピソードログ物理削除禁止 (bitemporal と整合)

準備ができたら最初の Explore agent を launch してください。
EOF

# Sanity check: tmux session not already running
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "tmux session '$SESSION' already exists. Attach with: tmux attach -t $SESSION" >&2
    echo "Or kill first with: tmux kill-session -t $SESSION" >&2
    rm -f "$PROMPT_FILE"
    exit 1
fi

# Launch in detached tmux session. --permission-mode plan forces Plan Mode
# at startup. The prompt is read from the temp file so shell quoting cannot
# corrupt it.
#
# Unset headless-auth tokens before calling claude so the session uses the
# interactive OAuth (keychain / subscription) flow. ``CLAUDE_CODE_OAUTH_TOKEN``
# is sourced via ``~/.config/claude/env`` for CI / non-interactive work but
# routes claude through API-style billing when active; we want subscription
# billing for long planning sessions. Same reasoning for ``ANTHROPIC_API_KEY``
# if a developer sets it for one-off scripts.
tmux new-session -d -s "$SESSION" -c "$REPO" \
    "unset CLAUDE_CODE_OAUTH_TOKEN ANTHROPIC_API_KEY; claude --model opus --permission-mode plan \"\$(cat '$PROMPT_FILE')\"; rm -f '$PROMPT_FILE'; exec \$SHELL"

echo "✓ Launched Phase ${PHASE} session in tmux (name: ${SESSION})"
echo ""
echo "  Attach   : tmux attach -t ${SESSION}"
echo "  Detach   : Ctrl-b d"
echo "  Kill     : tmux kill-session -t ${SESSION}"
echo ""
echo "The new Claude starts in Plan Mode and will read:"
echo "  - ~/.claude/plans/unified-booping-snowflake.md"
echo "  - docs/adr/0021-*.md"
echo "  - .reports/phase-${PREV_PHASE}-report.md"
