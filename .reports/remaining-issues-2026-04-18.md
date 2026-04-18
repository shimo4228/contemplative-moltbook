# Remaining Issues — 2026-04-18 (Consolidated, Cold-Start Ready)

`.reports/remaining-issues-2026-04-16.md` と `.reports/followup-issues-20260417.md` および MEMORY.md Pending Tasks を 2026-04-18 時点で verify-before-work で照合し、**実コードで未解決のものだけ**を一元化。旧 2 ファイルは superseded。

本ファイルは次セッションの cold-start で読むだけで着手できる状態に書かれている。各 §「次セッションで最初にやること」から着手可。

---

## Part A — Active Tasks (次セッションで着手可能)

### §A1. Rare-important pattern 救済 + singletons 可視化

**Severity**: medium
**状態**: ⬜ Pending (decision + 実装 1 PR)
**依存**: なし

#### 現状
- `src/contemplative_agent/core/insight.py:146` で `_singletons` は計算されるが以降の処理で unused (廃棄)
- `RARE_IMPORTANT_FLOOR` 定数は存在しない
- singletons log / artifact なし

#### 未決事項 (着手前に決める)
1. `RARE_IMPORTANT_FLOOR` 具体値 — 候補 0.3 / 0.5 / 0.7
2. プロンプト差別化 — insight 既存プロンプト分岐 vs 専用プロンプト
3. 救済件数上限 — N 件 cap vs 閾値のみ
4. 希少さ ≒ 異質さなのでプーリング禁止 (寄せ集めると抽象化量産、これは確定方針)

#### 次セッションで最初にやること
1. `.reports/` に sweep script 作成して現行 206 gated patterns の `effective_importance` P85-P95 分布を計測
2. 結果から `RARE_IMPORTANT_FLOOR` 候補値を決定
3. プロンプトは既存 insight 分岐で十分か、それとも専用 prompt を qwen3.5:9b に書かせるか判断 (feedback memory `prompt-model-match` 参照)
4. 実装: `insight.py` で `_singletons` を `effective_importance >= RARE_IMPORTANT_FLOOR` で filter、残りは `.staged/.singletons.json` にダンプ
5. 可視化: insight log に `skipped N patterns as singletons (kept M as rare-important)` を出力
6. stocktake で merge 判定前提なので、特段の保護は不要

#### 関連ファイル
- `src/contemplative_agent/core/insight.py:146` — `_singletons` 現状
- `src/contemplative_agent/core/knowledge_store.py:43-67` — `effective_importance` 計算式
- `.reports/rules-distill-threshold-sweep.py` — sweep スクリプトのテンプレート

---

### §A2. `effective_importance` time decay の実効性測定

**Severity**: low-medium (議論から派生、2026-04-18 保留)
**状態**: ⬜ Pending (測定して判断)
**依存**: A1 と同時並行可

#### 背景
2026-04-18 セッションで `0.95^days_elapsed` の time decay 部分が「心理モデル的」かどうか議論。結論: psych-model-placement rule の精密版 (raw immutable + 関数で per-query 計算) は満たしているので、原則的には撤回不要。ただし実効性を測って「**本当に効いているか、消した方が rare-important 救済と整合するか**」を見る必要がある。

#### 仮説
- 古い pattern が `0.95^days` で重みが下がる → dedup 候補から外れる / cluster ソートで後ろに下がる
- 14 日で半減、60 日でほぼゼロ
- 古くて高 importance な pattern (rare-important と同カテゴリ) が埋もれている可能性

#### 次セッションで最初にやること
1. `.reports/time-decay-effect-20260419.py` 作成:
   - 全 206 gated pattern の `(age_days, importance, trust_score, effective_importance)` を出力
   - time_decay あり/なしの `effective_importance` 分布を比較
2. dedup gate (`DEDUP_IMPORTANCE_FLOOR` との比較) でどれだけの pattern が時間だけで外れているかカウント
3. cluster / insight の順序が time decay の有無でどう変わるか 3-5 件確認
4. rare-important 候補 (高 importance × 高 age) がどの程度埋もれているか確認
5. 判断:
   - (a) 効いていて有害 → 係数調整 (`0.95` → `0.99` 等) か無効化
   - (b) 効いていて有益 → 維持
   - (c) ほぼ効いていない → 撤回してシンプル化

#### 関連ファイル
- `src/contemplative_agent/core/knowledge_store.py:43-67` — `effective_importance` 本体
- `src/contemplative_agent/core/distill.py:625` — dedup gate
- `src/contemplative_agent/core/clustering.py:106`, `insight.py:104/112/134` — ソート consumer

#### 判断軸 (memory 参照)
- `feedback_psych_model_placement.md` — raw + 関数分離は OK、mutable state 溜めないなら substrate に残してよい
- `feedback_single_responsibility_per_artifact.md` — SRP 視点での追加評価

---

### §A3. ADR status の棚卸し (コスメ、低優先)

**Severity**: low (コード影響なし)
**状態**: ⬜ Pending

#### 現状
多くの ADR が `Status: proposed` のまま。実装済みで land してから時間が経っているものは `accepted` に格上げすべき。

#### 対象候補
| ADR | 現 status | 提案 status |
|---|---|---|
| 0020 | proposed | accepted |
| 0021 | partially-superseded-by 0028, 0029 | accepted (reduced scope) |
| 0022 | proposed | accepted |
| 0023 | proposed | accepted |
| 0026 | proposed | accepted |
| 0027 | proposed | accepted |
| 0028 | proposed | accepted |
| 0029 | proposed | accepted |
| 0030 | proposed | accepted |

#### 次セッションで最初にやること
1. 各 ADR の Decision セクションが実装と一致するか verify-before-work で確認
2. 一致するなら `Status: proposed` → `Status: accepted` に書き換え (en + ja ペア)
3. `docs/adr/README.md` の index 更新
4. 1 commit: `docs(adr): promote landed ADRs from proposed to accepted`

---

## Part B — Observation Tasks (trigger が来たら着手)

### §B1. Memory evolution の実効性測定

`ADR-0022 memory_evolution.evolve_patterns()` が実際に何件 revise を発火させていて、その revision の質はどうか。

- **Trigger**: 2-3 ヶ月稼働後、`memory_evolution` 呼び出しログが一定数溜まった段階
- **Read**: `logs/` の memory evolution 関連 entry、`knowledge.json` の soft-invalidate された旧行
- **評価軸**: revision の LLM 判断が `NO_CHANGE_MARKER` ばかりだと評価価値が低い。実 revision の質を 5-10 件手動 review

### §B2. Noise as seed の救済発動機会

`ADR-0027` で gated episodes が `noise-YYYY-MM-DD.jsonl` に貯まる。view centroid が大きく shift したタイミング (view 再定義 / noise view 係数変更) で re-classification が発動するはず。

- **Trigger**: view stocktake で seed text を変更したタイミング
- **Read**: `noise-*.jsonl` の蓄積状況、view centroid 再計算後の classify 結果
- **評価軸**: 実際に救済された pattern がいくつあるか

### §B3. skill-reflect の revision 品質

`ADR-0023` で `skill_router._usage_log` と `skill-reflect` が skill 本体を書き換える。現在 11 skills。失敗率が閾値を超えた skill で revision が発動する。

- **Trigger**: usage log が各 skill で 10-20 件以上溜まった段階
- **Read**: `logs/skill-usage-YYYY-MM-DD.jsonl`、`skill-reflect --stage` の結果
- **評価軸**: revision の採用率、revision 後の再 usage 結果

---

## Part C — Operational Gotchas (記録のみ、アクション不要)

`.reports/remaining-issues-2026-04-16.md` §3 から不変:
- `skill_router._cache` は body on-memory (skill 数 200 超で再評価)

2026-04-18 セッションで判明した gotcha (`MEMORY.md` Operational Gotchas と同期済み):
- `ollama-num-ctx-silent-truncation` — 長プロンプトが silent truncate、「stochastic な失敗」を見たら最初に疑う
- `distill-num-predict-risk` — 30 episodes に対して num_predict=1500 が tight な可能性、truncate 兆候が出たら 3000 に

ADR-0030 (2026-04-18) で撤回済みの gotcha は不要 (identity_history / block-mode identity 関連全部)。

---

## Part D — Previous Session History (2026-04-18)

### 完了タスク
| # | 項目 | commit / report |
|---|---|---|
| F1 | mark_accessed persistence gap | ADR-0028 (`241bf8a`) |
| F2 | user_input / external_post / sanitized dormant 整理 | ADR-0029 (`0370484`) |
| F3 | feedback live 配線 or schema removal | ADR-0028 (`241bf8a`) |
| F4 | Retrieval scoring rank-reversal behavioral test | commit `d9074ae` |
| F5 | Dry-run rank-reversal 効果測定 | commit `0823e95` + `.reports/retrieval-scoring-effect-20260418.md` |
| F6 | is_live() consumer 適用網羅性確認 | commit `4e8eca3` + `.reports/is-live-consumer-audit-20260418.md` |
| Issue 3 | SIM_DUPLICATE=0.92 が vacuous | `distill.py:50` で 0.90 に calibrated (2026-04-17) |
| Issue 4 | CONSTITUTIONAL_THRESHOLD dead 削除 | 2026-04-18 セッション |
| Issue 5 | CLUSTER_THRESHOLD_RULES sweep | 2026-04-18 セッション (0.65 据え置き) |
| Issue 6 | title-abstraction バイアス | 対応不要判断 |
| D3 | Per-block distill routing | Withdrawn (ADR-0030) |
| D4 | Runtime agent-edit tool | Withdrawn (ADR-0030, 責任分界 ambiguity) |

### 新規で生まれた教訓 memory
- `feedback_single_responsibility_per_artifact.md` — 1 artifact 1 責務
- `feedback_psych_model_placement.md` — 心理モデル配置ルール (mutable vs immutable 軸で精密化)

---

## 着手難易度マトリクス

| タスク | 工数 | 依存 | 状態 | 推奨順序 |
|---|---|---|---|---|
| §A1 Rare-important 救済 | M (decision + 実装) | なし | ⬜ Pending | 1 |
| §A2 time decay 実効性測定 | S (script + 観察) | §A1 と並行可 | ⬜ Pending | 2 (並行) |
| §A3 ADR status 棚卸し | XS | なし | ⬜ Pending | 3 (いつでも) |
| §B1-B3 Observation | — | trigger 待ち | 保留 | 時期が来たら |

次セッションで「何から着手」と聞かれたら §A1 (Rare-important) → §A2 (time decay) が自然な流れ。§A1 で effective_importance 分布を出せば §A2 の観察もほぼカバーできる。§A3 は合間に挟める。

---

## 参考

- 旧 remaining: `.reports/remaining-issues-2026-04-16.md` (superseded、削除候補)
- 旧 followup: `.reports/followup-issues-20260417.md` (superseded、削除候補)
- 本日解消の audit follow-up: `.reports/adr-0021-audit-followups-20260418.md`
- ADR-0030 (identity block 撤回): `docs/adr/0030-withdraw-identity-blocks.md`
- D3 handoff (archived): `.reports/archive/d3-per-block-distill-handoff.md`
