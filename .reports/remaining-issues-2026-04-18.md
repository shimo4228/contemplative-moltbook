# Remaining Issues — 2026-04-18 (Consolidated)

`.reports/remaining-issues-2026-04-16.md` と `.reports/followup-issues-20260417.md` および MEMORY.md Pending Tasks を 2026-04-18 時点で verify-before-work で照合し、**実コードで未解決のものだけ**を一元化した successor。旧 2 ファイルは superseded。

## 前提: 2026-04-18 セッションで解消した項目

| # | 項目 | 出典 | 解消 commit / report |
|---|---|---|---|
| F1 | mark_accessed persistence gap | adr-0021 F1 | ADR-0028 (`241bf8a`) |
| F2 | user_input / external_post / sanitized dormant 整理 | adr-0021 F2 | ADR-0029 (`0370484`) |
| F3 | feedback live 配線 or schema removal | adr-0021 F3 | ADR-0028 (`241bf8a`) |
| F4 | Retrieval scoring rank-reversal behavioral test | adr-0021 F4 | commit `d9074ae` |
| F5 | Dry-run rank-reversal 効果測定 | adr-0021 F5 | commit `0823e95` + `.reports/retrieval-scoring-effect-20260418.md` |
| F6 | is_live() consumer 適用網羅性確認 | adr-0021 F6 | commit `4e8eca3` + `.reports/is-live-consumer-audit-20260418.md` |
| Issue 3 | SIM_DUPLICATE=0.92 が vacuous | followup-20260417 §3 | `distill.py:50` で 0.90 に calibrated (2026-04-17) |
| Issue 6 | title-abstraction バイアス | followup-20260417 §6 | 対応不要判断 (identity-level voice と再診断) |
| Issue 4 | CONSTITUTIONAL_THRESHOLD dead 削除 | this report §5 | 2026-04-18 セッション (distill.py / snapshot.py / 2 tests / core-modules.md) |
| Issue 3 (再) | dedup constrained decoding doc sweep | this report §3 | 2026-04-18 セッション (glossary.md / moltbook-agent.md / compiled-petting-pumpkin.md) |
| Issue 5 | CLUSTER_THRESHOLD_RULES sweep | this report §6 | 2026-04-18 セッション (`.reports/rules-distill-threshold-sweep{,-result-20260418}.{py,md}`、0.65 据え置き判断) |
| Bonus | `_dedup_patterns` Pyright invariance 警告 | session diagnostics | `List[Optional[ndarray]]` → `Sequence[Optional[ndarray]]` (distill.py:752-756) |
| D3 | Per-block distill routing (ADR-0024 deferred) | this report §1 | **Withdrawn** — ADR-0030 で ADR-0024/0025 全撤回 (2026-04-18)。handoff は `.reports/archive/d3-per-block-distill-handoff.md` |
| D4 | Runtime agent-edit tool (ADR-0024 deferred) | this report §2 | **Withdrawn** — 責任分界が曖昧で不要と判断 (ADR-0030, 2026-04-18) |

## 本当に残っているタスク (truly pending)

### 1. D3 + D4 — ✅ Withdrawn (2026-04-18, ADR-0030)

**Severity**: ~~high-effort~~ withdrawn
**状態**: ✅ 撤回

ADR-0024 (identity block separation) と ADR-0025 (identity history) は single-responsibility 観点から撤回された (ADR-0030)。identity.md は legacy whole-file 形式に戻る。

- **D3 (per-block distill routing)**: block 様式撤回で前提消失
- **D4 (runtime agent-edit tool)**: 責任分界が曖昧 (誰が発案し誰が責任を持つか) + 他の書き換え経路 (distill-identity / skill-reflect / amend-constitution は CLI 起点、memory_evolution はノレッジ層で bitemporal 監査可) の清潔さを壊すため不要と判断

identity を書き換える経路は `distill-identity` CLI + 承認ゲートのみに戻る。

詳細: [ADR-0030](../docs/adr/0030-withdraw-identity-blocks.md)、archive: `.reports/archive/d3-per-block-distill-handoff.md`。

### 3. Constrained decoding — ✅ Closed (2026-04-18 verify)

**Severity**: ~~medium~~ closed
**状態**: ✅ 完了

**verify-before-work で発見された前提崩れ**:
- 旧記述「dedup quality gate (SIM_DUPLICATE 判定後の LLM call) に `format` 未適用」は **stale**
- 実コード: ADR-0009/0019 で LLM-based dedup gate (`_llm_quality_gate`) は embedding cosine (`_dedup_patterns`) に置換済み。該当 LLM call が存在しない (`distill.py:644` のコメント `instead of SequenceMatcher + LLM gate` が証拠)
- benchmark 基盤も既に実装済み: `tests/benchmark_distill.py` (365 行、3/31 作成) + `tests/fixtures/benchmark/{synthetic,real_sample}.jsonl` + `results/` (4/10 まで蓄積)

**実際に行った作業 (doc sweep)**:
- `docs/glossary.md` Dedup/Quality Gate を embedding-only 形式に書き直し
- `docs/CODEMAPS/moltbook-agent.md` から `distill_dedup` プロンプト名を削除
- `~/.claude/plans/compiled-petting-pumpkin.md` を「Part 2 dedup row obsolete」と注記

**残存タスク**: なし

### 4. Issue 1 — Rare-important pattern 救済パス + Issue 7 singletons 可視化

**Severity**: medium (統合対応推奨)
**状態**: ⬜ 未着手

**現状**:
- `insight.py:146` で `_singletons` は計算されるが以降の処理で unused (廃棄)
- `RARE_IMPORTANT_FLOOR` 定数なし
- singletons log / artifact なし

**要件**:
- 希少さ ≒ 異質さなのでプーリング禁止 (寄せ集めると抽象化量産)
- `effective_importance` に高い閾値 (候補: 0.3 / 0.5 / 0.7, Phase C sweep P85-P95)
- 単発観察の仮説的 skill 化を明示、stocktake で merge 判定前提
- 可視化: insight log に `skipped N patterns as singletons` or `.staged/.singletons.json` dump

**未決事項**:
- `RARE_IMPORTANT_FLOOR` 具体値
- プロンプト差別化 (insight 既存プロンプト分岐 vs 専用プロンプト)
- 救済件数上限 (N 件 cap vs 閾値のみ)

**依存**: なし (decision + 実装 1 PR)

### 5. Issue 4 — ✅ Closed (2026-04-18)

**Severity**: ~~low~~ closed
**状態**: ✅ 完了 (this session)

**現状**:
- `distill.py:57` `CONSTITUTIONAL_THRESHOLD = 0.55` (ADR-0026 で Phase 3 delete 指定、未実施)
- `snapshot.py:63` でレジストリに登録 (snapshot 時の値記録)
- `tests/test_distill.py:731, test_snapshot.py:88` で assertion 参照
- ADR-0026 で `_classify_episodes` から読まれなくなった (dead)

**作業**:
1. `distill.py:57` 定数削除
2. `snapshot.py:63` レジストリから削除
3. `tests/test_distill.py:731-734` の参照テスト削除
4. `tests/test_snapshot.py:88` から項目削除
5. `docs/CODEMAPS/core-modules.md:173` の記述更新

**依存**: なし (1 PR で完結)

### 6. Issue 5 — ✅ Closed (2026-04-18 sweep, 0.65 retained)

**Severity**: ~~low~~ closed
**状態**: ✅ 完了 (this session)。sweep 結果 0.55-0.75 のどれでも 1 cluster 収束 → 据え置き判断。詳細 `.reports/rules-distill-threshold-sweep-result-20260418.md`

**現状**:
- `rules_distill.py:31` `CLUSTER_THRESHOLD_RULES = 0.65` 暫定値
- 現在 skill 数 11 本 (`~/.config/moltbook/skills/`) — 条件 (10 本以上) 達成
- `.reports/rules-distill-threshold-sweep.py` 未作成 (`.reports/threshold-sweep.py` は汎用、rules 用ではない)

**作業**:
1. `.reports/rules-distill-threshold-sweep.py` 作成 (skill text の cosine 分布 sweep)
2. P75 / P90 / P99 を計測し `CLUSTER_THRESHOLD_RULES` 再決定

**依存**: なし (skill 数条件はクリア)

## 運用で気にしておくポイント (バグ化リスク、アクション不要)

`.reports/remaining-issues-2026-04-16.md` §3 から不変のもの:
- `skill_router._cache` は body on-memory (skill 数 200 超で再評価)

ADR-0030 (2026-04-18) による撤回済み:
- ~~identity_history は現在 `persona_core` しか記録しない~~ — identity_history 自体廃止
- ~~`_handle_adopt_staged` の identity 専用分岐~~ — 分岐自体削除
- ~~`MigrationResult.document` / `.rendered` は Optional~~ — 型自体削除
- ~~`load_for_prompt` の mtime キャッシュは module-level~~ — 関数自体削除
- ~~`distill-identity` は `persona_core` body のみ LLM に渡す~~ — whole-file に戻った

## 着手難易度マトリクス (2026-04-18 後)

| タスク | 工数 | 依存 | 状態 |
|---|---|---|---|
| 5. Issue 4 (dead 定数削除) | XS | なし | ✅ Closed (2026-04-18) |
| 3. Constrained decoding dedup + benchmark | — | なし | ✅ Closed (doc sweep のみ、本体作業はゴーストタスクと判明 2026-04-18) |
| 6. Issue 5 (CLUSTER_THRESHOLD sweep) | S | なし | ✅ Closed (0.65 据え置き 2026-04-18) |
| 4. Issue 1 + 7 (Rare-important 救済) | M (decision + 実装) | なし | ⬜ Pending |
| 1. D3 (per-block distill) | — | — | ✅ Withdrawn (ADR-0030, 2026-04-18) |
| 2. D4 (runtime agent-edit) | — | — | ✅ Withdrawn (ADR-0030, 2026-04-18) — 責任分界 ambiguity |

## 参考

- 旧 remaining: `.reports/remaining-issues-2026-04-16.md` (superseded、削除候補)
- 旧 followup: `.reports/followup-issues-20260417.md` (superseded、削除候補)
- 本日解消の audit follow-up: `.reports/adr-0021-audit-followups-20260418.md`
- MEMORY.md Pending Tasks セクションは本ファイルにリンクを向ける更新が必要
