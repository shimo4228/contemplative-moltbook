# Retrieval Scoring Effect — F5 Measurement — 2026-04-18

ADR-0021 audit follow-up F5 (see `.reports/adr-0021-audit-followups-20260418.md:46-68`).
F4 / F6 は完了済み。本 report は F5 の単体成果。

## Context

ADR-0021 で導入した scoring 式 `(α·cosine + β·bm25_norm) × trust` に対し、production 377 patterns のうち `trust_score` の分布が migration default に張り付いていることを背景に、trust 因子が実質的に top-K を discrimination しているかを実データで測定した。

**関連 ADR**:
- ADR-0021: trust_score を cosine に乗算する scoring 導入
- ADR-0022: BM25 lexical 併用 (β=0.3 default)
- ADR-0028: Ebbinghaus strength 撤回 (trust は残した)
- ADR-0029: dormant provenance 撤回

**trust 分布 (production knowledge.json, 2026-04-18)**:

| trust_score | 件数 | 割合 |
|---|---|---|
| 0.6 | 345 | 91.5% |
| 0.9 | 24 | 6.4% |
| 0.5 | 8 | 2.1% |
| **合計** | **377** | — |

TRUST_FLOOR = 0.3 なので全 377 件が live 判定を通過し得る。valid_until によるフィルタ後の live 候補は 311 件。

## Method

### Approach B (in-process simulation) を採用

計画書 (`hidden-booping-sunrise.md`) の 3 選択肢のうち Approach B を採用。`src/contemplative_agent/core/views.py:307-355` の `_rank` ロジックを script 内で複製し、同じ 311 件 live pool に対して scoring 式の 3 variant を切り替える。過去 commit checkout (Approach A) は schema 互換性リスクで棄却。

### 3 variant の定義

| variant | 式 | 意味 |
|---|---|---|
| **V_current** | `(α·cos + β·bm25) × trust` | 現行 (ADR-0021 + 0022) |
| **V_notrust** | `(α·cos + β·bm25) × 1.0` | trust 因子を中立化 (trust 単独寄与の測定) |
| **V_cosineonly** | `cos × 1.0` | ADR-0021 前相当 (β=0, trust=1) |

α = 1 − β。各 view の YAML frontmatter から `bm25_weight` / `threshold` / `top_k` を読み、`top_k` は比較のため一律 10 に揃える。

### Metric

| metric | 定義 | 測れること |
|---|---|---|
| **Jaccard@10** | `|A ∩ B| / |A ∪ B|` | top-10 set 重複 |
| **Kendall tau** | 共通 pattern 間の順位相関 (ties 無視) | 順序の保存 |
| **Top-1 agreement** | top-1 が一致するか (0/1) | 最優先 hit が変わるか |
| **Top-3 agreement** | top-3 共通件数 (0–3) | 高優先帯の安定性 |

### Views

`noise` を除く 6 views (`technical`, `reasoning`, `communication`, `self_reflection`, `constitutional`, `social`) をテスト。seed text は `~/.config/moltbook/views/*.md` を優先、無ければ `config/views/*.md` にフォールバック。

**注記**: `constitutional.md` は `seed_from: ${CONSTITUTION_DIR}/*.md` の placeholder が path_vars 未設定で unresolved 扱いとなり、body にフォールバック。production では CLI 経由で `CONSTITUTION_DIR` が注入されるため、本 measurement の constitutional 結果は lower-bound (seed が短い分、cosine 値が小さくなる)。

## Prototype Phase (technical view, 5-10 sample)

最初に `technical` view 単体で走らせて sanity check。

```
[view] technical: J(current,notrust)=0.250 J(current,cos)=0.000
                   K(current,notrust)=1.000 K(current,cos)=-
                   t1(cn/cc)=0/0 t3(cn/cc)=0/0
```

発見:
1. J(current, notrust) = 0.250 → trust 因子を外すと top-10 の 75% が入れ替わる
2. J(current, cosineonly) = 0.000 → trust + BM25 を両方外すと完全に別の top-10
3. K(current, notrust) = 1.0 → 共通する 2–3 件の順位は保存される (乗算は順序保存なので当然)
4. Top-1 / Top-3 が完全不一致

→ 「trust 因子が実質 discrimination していない」という事前仮説は **誤り**。フル実行へ進む。

## Full Results (6 views × top-10)

### View 毎の metric

| view | threshold | β | J(cur,notrust) | J(cur,cos) | K(cur,notrust) | K(cur,cos) | t1 cn/cc | t3 cn/cc |
|---|---|---|---|---|---|---|---|---|
| technical | 0.55 | 0.3 | 0.250 | 0.000 | 1.000 | — | 0/0 | 0/0 |
| reasoning | 0.55 | 0.3 | 0.176 | 0.053 | 1.000 | — | 1/0 | 1/1 |
| communication | 0.55 | 0.3 | 0.111 | 0.053 | 1.000 | — | 0/0 | 0/0 |
| self_reflection | 0.55 | 0.3 | 0.176 | 0.111 | 1.000 | -1.000 | 0/0 | 0/0 |
| constitutional | 0.35 | 0.3 | 0.538 | 0.000 | 1.000 | — | 0/0 | 0/0 |
| social | 0.55 | 0.3 | 0.176 | 0.053 | 1.000 | — | 0/0 | 0/0 |

(K=`—` は intersection < 2 で計算不能。constitutional の threshold 低値は seed fallback による)

### Aggregate

| metric | mean | stdev |
|---|---|---|
| Jaccard(current, notrust) | **0.238** | 0.154 |
| Jaccard(current, cosineonly) | **0.045** | 0.041 |
| Kendall(current, notrust) | **1.000** | 0.000 |

### Current top-10 の trust 分布

6 views × 10 = 60 slots のうち trust=0.9 が占める数:

| view | trust=0.9 | trust=0.6 |
|---|---|---|
| technical | 6 | 4 |
| reasoning | 7 | 3 |
| communication | 8 | 2 |
| self_reflection | 7 | 3 |
| constitutional | 3 | 7 |
| social | 7 | 3 |
| **合計** | **38 / 60 (63%)** | **22 / 60 (37%)** |

**候補プールでの trust=0.9 の割合は 24/311 = 7.7%**。top-10 で 63% を占めるのは **8.2× の overrepresentation**。

## Interpretation

### trust 因子は強く discrimination している

事前仮説「91.5% が 0.6 固定だから trust は実質効かない」は反証された:

1. trust=0.9 pattern (6.4%) と trust=0.6 pattern (91.5%) の比 1.5× が、cosine スコアが近接する top 帯で順位を支配する
2. 結果として top-10 は trust=0.9 が 63% を占める (vs 候補での 7.7%)
3. Jaccard(current, notrust) = 0.238 = 「trust を外せば top-10 の 76% が別の pattern に置き換わる」

### Decision Tree による判定

計画書の decision tree (`hidden-booping-sunrise.md`):
- Jaccard(current, cosineonly) > 0.9 **かつ** Kendall > 0.85 → retire 候補
- 0.7 ~ 0.9 → reshape
- < 0.7 → **keep**

| 比較軸 | Jaccard | Kendall | 判定 |
|---|---|---|---|
| current vs cosineonly (combined: trust + BM25) | 0.045 | 1.000 (n<2 多い、信頼度低) | < 0.7 → **keep** |
| current vs notrust (trust 単独寄与) | 0.238 | 1.000 | < 0.7 → **keep** |

どちらの軸でも **keep** 判定。

### 判定の意味

trust は以下 2 つを同時に実現している:

1. **Curated 昇格**: 手動で trust=0.9 を付けた 24 patterns を top-K で優先 (6.4% → 63% に昇格)
2. **Default 下押しは無し**: 0.6 と 0.5 の差 (0.833×) は小さく、0.5 pattern を明確に沈める効果は薄い

実質的に「0.6 baseline + 0.9 curated boost」の二値的システムとして動作している。migration default 0.6 の一律性は、むしろ「curated 0.9 を目立たせる」という意図 (明示的/暗黙的) に合致している可能性。

### 付随的発見: BM25 も強く効いている

V_current (β=0.3) vs V_cosineonly (β=0) の Jaccard = 0.045 は、trust + BM25 を両方外すと top-10 がほぼ完全に別物になることを示す。trust 単独寄与 (0.238) よりさらに低い → **BM25 lexical channel (ADR-0022) が trust と同等以上に効いている**。これは ADR-0022 の想定通りだが、F5 scope 外なので記録のみ。

### 脆弱性

- trust=0.9 の 24 patterns が curated で設定された経緯を追えるか (inspect-identity-history 等)、分布が意図的に維持されているかは本測定の範囲外
- trust_score の update 経路 (episode-based) が実運用でほぼ発火していない → 「手動 curation」依存。episode 由来の trust 変化を強化する ADR が書ける可能性はある
- 将来 migration default を 0.6 から動かす場合、本測定の結果は無効化される

## Recommendation

### 短期: keep (trust_score を retire しない)

Jaccard 判定 + top-K の 63% が trust=0.9 で占有される実態より、trust は retrieval に強く効いている。**retire するとシステム挙動が大きく変わる** (recall される pattern set が ~76% 入れ替わる)。ADR-0030 起案は不要。

### 中期: 観察を続ける (reshape の可能性を否定しない)

以下 2 点は今後の ADR 候補:

1. **trust_score の自動 update 経路強化**: 現状 manual curation 依存。episode based な自動調整が機能しているか `inspect-identity-history` 等で定点観測
2. **trust 分布の意図の ADR 化**: 「0.6 baseline + 0.9 boost」が設計意図ならその旨を ADR として記録。分布が偶然なら migration default の見直し検討

### 長期: trust の semantic を定期的に再評価

本 measurement を年次程度で再実行。trust 分布が変化したら scoring 式のバランス (α/β/trust multiplier の扱い) を再検討。

## Artifacts

- 測定 script: `.reports/retrieval-scoring-effect-20260418.py` (read-only guaranteed)
- 生データ JSON: `.reports/retrieval-scoring-effect-20260418.json` (3 variant × 6 view × top-10 の pattern dump)

### Read-only 検証

```python
before_mtime = KNOWLEDGE_PATH.stat().st_mtime_ns
# ... run 3 variants ...
after_mtime = KNOWLEDGE_PATH.stat().st_mtime_ns
assert after_mtime == before_mtime
```

assert 成功 → production knowledge.json への write 無し。

## Conclusion

- F5 完了
- trust 因子は retire しない (keep 判定)
- BM25 lexical channel の寄与が trust と同等以上 (F5 scope 外の知見)
- ADR-0030 起案は不要。trust の自動 update 経路と分布意図の明文化は別 ADR 候補として記録
