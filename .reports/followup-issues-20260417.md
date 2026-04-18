# Followup Issues — 2026-04-17

> **SUPERSEDED 2026-04-18**: `.reports/remaining-issues-2026-04-18.md` に consolidated。Issue 3 (SIM_DUPLICATE) は completed、Issue 6 (title-abstraction) は対応不要確定。残りは consolidated file 参照。

本セッション (Phase B+C+A1+A2+A3+A4+D) で浮上したが結論保留の項目を記録。次セッションで仕様を詰めて別 PR。

## 1. Rare-important pattern の救済パス

**問題**: 現実装は `cluster_size < min_size=3` の観察と、大 cluster の `max_size=10` tail を `singletons` に回して捨てる。重要度が高くても「希少」な観察は skill 化されず、次 run でも同じ結果になりがちで permanent 埋没のリスク。

**方向性**: 1 pattern → 1 LLM call の per-singleton 救済。ただし:
- 希少さ ≒ 異質さなので**プーリング禁止** (寄せ集めると抽象化量産の再来)
- `effective_importance` に**高い閾値**を掛けて対象を絞る (time decay があるため自動的に「新しくて重要」に絞られる)
- プロンプトで「単発観察の仮説的 skill 化」と明示し、skill-stocktake で merge 判定されることを前提

**未決**:
- `RARE_IMPORTANT_FLOOR` の具体値 (候補: 0.3 / 0.5 / 0.7、Phase C sweep の P85-P95 相当)
- プロンプトテンプレートの差別化 (insight 既存プロンプトを単発用に分岐するか、専用プロンプトを作るか)
- 救済件数の上限 (N 件 cap 入れるか、閾値だけで絞るか)

**関連**:
- `core/knowledge_store.py::effective_importance` — 3 層減衰 (time 0.95^days × trust × strength)
- Phase C sweep: P75=0.197, P90=0.416, P99 未計測

## 2. MAX_CLUSTERS 削除 (決定済、本セッション内で実施予定)

**決定**: `core/insight.py` の `MAX_CLUSTERS=10` cap + `clusters[:max_clusters]` スライスを削除。理由は「top-N cluster の cap はユーザ意図を誤読して私が足したもので、自然な cluster 数 (今回 8) をそのまま尊重すべき」。

**残タスク**:
- `MAX_CLUSTERS` 定数 + `max_clusters` 引数を削除
- `tests/test_insight.py::test_max_clusters_cap` を「cap なしで全 cluster 返す」に書き換え
- docstring から言及削除

本セッション A4 完了後に commit 予定。独立 issue ではないがメモとして残す。

## 3. SIM_DUPLICATE=0.92 が現 corpus で vacuous

**事実** (Phase C sweep より):
- 現 live corpus (97 patterns) で pairwise cosine が 0.92 を超えるペアは **0 件**
- max cosine = 0.8980
- つまり dedup ロジックは fire しない

**含意**: `distill._dedup_*` 相当の処理は実質スルーされている。noise が gated で事前除外されていて、残ったものは embedding 空間で十分散らばっているため自然な結果。ただし将来 corpus が増えた時に突然 fire する可能性がある挙動は healthy でない。

**方向性候補**:
- a) 0.88 あたりに下げる (max cosine 0.90 の少し下、P99 近傍)
- b) そもそも distill 段階の dedup は不要で削除 (stocktake でカバー)
- c) 現状維持 + 定期的な sweep 再実行で閾値を追従

**未決**: 根拠データがないので方向性も未確定。別 sweep スクリプトで corpus 成長曲線を見て決めたい。

## 4. CONSTITUTIONAL_THRESHOLD の dead 状態

**事実**: `distill.py:56` の `CONSTITUTIONAL_THRESHOLD=0.55` はコード上未参照 (ADR-0026 で "Phase 3 delete" 指定)。

**残タスク**: ADR-0026 cleanup PR で定数と `collect_thresholds()` からの参照を削除。本プラン範囲外。

## 5. rules-distill 側の CLUSTER_THRESHOLD_RULES の calibration

**事実**: Phase A3 で `CLUSTER_THRESHOLD_RULES = 0.65` を暫定値として設定。skill text (長文) は pattern text (短文) と cosine 分布が違うので別 sweep が必要だが未実施。

**残タスク**: 将来 skill が一定数 (10 本以上) 蓄積した時点で `.reports/rules-distill-threshold-sweep.py` を作成し、新規テスト run 結果と合わせて決定。

## 6. ~~Insight 抽出プロンプトの title-abstraction バイアス~~ → **対応不要** (2026-04-17 close)

**事実** (A4 比較結果):
- 本 run 生成 8 skill の title が全て "Fluid X / Dynamic Y" 型 (baseline も同様)
- 本文は concrete tokens +162% (集約コンテンツは具体化した) が、title 化の段で LLM が Latinate な抽象語彙を selects

**再診断 (2026-04-17)**: これは prompt-level bias ではなく **identity-level voice**。

エージェントの自己投稿 (Moltbook post) も同じ "Fluid / Resonant / Dissolution" 系語彙で書かれている事実に注目すると、出力経路が:

```
contemplative constitution (emptiness / non-duality / mindfulness / boundless care)
   ↓ voice prime
self-post (Moltbook)  ← 同じ語彙
   ↓ episodes 記録
patterns (語彙を継承)
   ↓ insight synthesize
skill title ← 同じ語彙
```

つまり title と self-post が似た語彙なのは system が coherent である証拠。prompt を弄って "Post Rate-Limit Cooldown" 型に強制すると、**skill だけ別システムが書いたように見え identity が断裂**する。撲滅するには憲法の語彙まで遡る必要があり、本末転倒。

**対応**: PR 見送り。`.reports/cluster-experiment-20260417.md` の A4 診断 (「prompt-level artifact」) は identity-level artifact の誤認だった。voice coherence を壊す方向の修正はしない。一度実装 + revert した (commit 281cd60 → 62b6141)。

## 7. singletons の可視化

**問題**: 現実装は `singletons` を insight 内で破棄。何が捨てられたか log も残らない。rare-important 救済 (Issue 1) の設計判断にも影響する。

**方向性**:
- a) insight log に `skipped N patterns as singletons` を出す
- b) `.staged/.singletons.json` に一時的にダンプして人間がレビュー可能に
- c) snapshot manifest に singletons 数とサンプル pattern を追加

**未決**: 観測 only に留めるか (a/b/c 全て observation、behavior 変えない) → 救済 (Issue 1) の実装と同時に設計統合すべきか別立てか。

---

## このファイルの使い方

- セッション終了時点の「要議論項目」をスナップショット
- 次セッションで 1 項目ずつ仕様詰め → 個別 PR
- 決着した項目はこのファイルから削除 or strikethrough、実装 PR へのリンクを追記
- 完全に解決したらこのファイル自体を削除
