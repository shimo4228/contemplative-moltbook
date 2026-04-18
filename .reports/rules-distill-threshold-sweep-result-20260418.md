# CLUSTER_THRESHOLD_RULES Sweep Result — 2026-04-18

`.reports/rules-distill-threshold-sweep.py` で `~/.config/moltbook/skills/*.md` (8 本) の cosine 分布と各 threshold でのクラスタ数を測定。`rules_distill.py:31` の暫定値 `CLUSTER_THRESHOLD_RULES = 0.65` の calibration が目的。

## 入力

- Skills: 8 本 (auto-extracted、2026-04-17 生成)
- Embedding model: nomic-embed-text (768 次元)
- Pairs: 28 (8 × 7 ÷ 2)

## Pairwise Cosine 分布

| Stat | Value |
|---|---|
| min | 0.8446 |
| P25 | 0.8706 |
| P50 | 0.8926 |
| **P75** | **0.9117** |
| P90 | 0.9332 |
| max | 0.9435 |
| mean | 0.8928 |

**観察**: 全ペアが 0.84 以上に集中。P25 と max の幅は 0.10 のみ。**スキル全体が semantic に極めて似ている**。

## Threshold ごとのクラスタ数

`min_size=3, max_size=10` (`_build_skill_clusters` と同条件)

| threshold | clusters | singletons | sizes |
|---|---|---|---|
| 0.55 | 1 | 0 | [8] |
| 0.60 | 1 | 0 | [8] |
| **0.65** | **1** | **0** | **[8]** |
| 0.70 | 1 | 0 | [8] |
| 0.75 | 1 | 0 | [8] |

**観察**: 0.55-0.75 のどの値でも 8 スキル全部が単一クラスタに収束。**現状の threshold は実質的に effect-less**。

## 解釈

スキルの本文を確認すると、auto-extracted された 8 本は全て contemplative agent の行動パターンの言い換え (「fluid」「anchoring」「reformation」「dissolving」「emptiness」「resonance」が共通語彙)。**genuine な semantic similarity** であり、embedding artifact や frontmatter 残存ではない。

`_build_skill_clusters` は元々「LLM batch を semantic に揃える」ための仕組みだが、現状コーパスは内容が均質すぎてグループ分けが起きない。1 クラスタ・サイズ 8 は `MAX_RULES_BATCH=10` 以内なので、結果として 1 batch にまとめて LLM に投げる挙動。これは現状コーパスでは妥当。

## 判断

**`CLUSTER_THRESHOLD_RULES = 0.65` を据え置く**。理由:

- 0.55-0.75 のどれを選んでも結果が変わらない (現状コーパスでは effect-less)
- 0.85+ に上げると突然分裂が起きるが、その境界の意味は未知 (P90=0.93 上で初めて分裂可能性、サンプル数 28 では断定不能)
- 値変更の根拠データがない → YAGNI

## Future Work

スキル数が **20+ に増えたら再度 sweep**。条件:

- 異なる auto-extraction 期間のスキルが混ざる (現状は 2026-04-17 同日生成のみ)
- 異なる adapter / domain のスキルが混ざる (moltbook 以外)
- 上記いずれかで cosine 分布が広がる (P25 が 0.7 を切る) → threshold 議論が意味を持つ

それまでは `0.65` を据え置きで問題なし。

## Reproduction

```bash
cd /Users/shimomoto_tatsuya/MyAI_Lab/contemplative-moltbook
uv run python .reports/rules-distill-threshold-sweep.py
```

Ollama が起動している必要あり (nomic-embed-text モデル)。
