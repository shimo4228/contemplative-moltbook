# is_live Consumer Audit — 2026-04-18

F6 follow-up of `audit-followups-20260418.md`.
Baseline: `implementation-audit-20260418.md` section 4 P2.4.

## is_live API

`src/contemplative_agent/core/forgetting.py:23-34`:

```python
TRUST_FLOOR = 0.3

def is_live(pattern: Dict) -> bool:
    """True if the pattern is currently retrievable.
    Gates on bitemporal (``valid_until is None``) + trust floor."""
    if pattern.get("valid_until") is not None:
        return False
    trust = float(pattern.get("trust_score", 1.0))
    if trust < TRUST_FLOOR:
        return False
    return True
```

`is_live` は `valid_until is None and trust_score >= 0.3` の合議で「retrieval から弾かれない pattern」を判定する。

## Consumer 棚卸し表

| Consumer | 行 | 読み元 | filter 状況 (audit 前 / 後) |
|---|---|---|---|
| `views._rank` | views.py:339 | candidates | ✅ `is_live(pat)` 直接呼び (変更なし) |
| `insight.extract_insight` | insight.py:215, 219, 222 | `get_live_patterns()` / `get_live_patterns_since()` | ✅ API 内で `is_live` (commit 9086c90 で landing 後修正済み) |
| `constitution.amend_constitution` | constitution.py:75 | `get_live_patterns()` → view | ✅ API + view 両方で `is_live` |
| `distill._distill_identity` | distill.py:226 | `get_raw_patterns()` → view | ✅ view 内で `is_live` |
| `distill._distill_category` (dedup scope pre-filter) | distill.py:657-666 | `get_raw_patterns()` + `effective_importance >= DEDUP_IMPORTANCE_FLOOR` | ⚠️ 間接 filter のみ → コメント追記で「下流 `_dedup_patterns` で `is_live` gate される」と明示 |
| `distill._dedup_patterns` (existing pool) | distill.py:790-797 | `existing_patterns` | ❌ → ✅ **修正**: `valid_until is None` のみ → `is_live(p)` |
| `distill._distill_category` (memory_evolution input) | distill.py:721-725 | `get_raw_patterns()` | ❌ → ✅ **修正**: `valid_until is None` のみ → `is_live(p)` |
| `migration.py` | migration.py:145, 647 | `get_raw_patterns()` | ✅ 意図的 (migration は raw 全件が正しい) |
| `memory.py` | — | pattern を読まない (interaction/post/insight 専用) | — |
| `skill_router.py` | — | skill (Markdown) を読む、distilled pattern 非経由 | — |
| `rules_distill.py` | — | skill file 経由、pattern 非経由 | — |
| `memory_evolution.find_neighbors` | memory_evolution.py:65-78 | caller-provided pool (docstring が「`valid_until is None` filter 済み」と明記) | ✅ caller 側で実施。本 audit で caller (distill) を `is_live` 化したため自動的に強化 |

## 発見した gap と修正

### Gap 1 — `distill.py:721-725` (memory_evolution input)

**Before**: `valid_until is None` のみ filter。低 trust pattern が `evolve_patterns` に neighbor として渡り、retrieval から弾かれる pattern を revise の対象にしていた。

**After**: `is_live(p)` 経由。意味論「retrieval されない pattern は evolution の対象外」に統一。

### Gap 2 — `distill.py:790-797` (`_dedup_patterns` existing pool)

**Before**: `valid_until is None` のみ filter。trust=0.1 (低 trust = retrieval されない) の "noise pattern" と semantic 一致した new pattern が誤って SKIP され、価値ある新規が失われる回帰リスク。

**After**: `is_live(p)` 経由。低 trust existing は dedup pool から除外 → new pattern は ADD される。

### Gap 3 (no-op) — `distill.py:657-666` (dedup scope pre-filter)

`effective_importance(p) >= DEDUP_IMPORTANCE_FLOOR` は trust を **重み付け** で含むが TRUST_FLOOR の **cutoff** とは等価でない。本 PR では下流 `_dedup_patterns` 内に `is_live` gate を入れたため pre-filter は触らず (二重 filter になり冗長)。代わりにコメントで「is_live は下流で適用」と明示し、将来の読み手の混乱を防ぐ。

## 修正内容

`src/contemplative_agent/core/distill.py`:
- `from .forgetting import is_live` を import 追加
- `distill.py:657-666` にコメント追加 (is_live gate の所在を明示)
- `distill.py:721-725` を `is_live(p)` 経由に変更 (memory_evolution input)
- `distill.py:790-797` を `is_live(p)` 経由に変更 (`_dedup_patterns` existing pool)

`tests/test_distill.py` に regression test 2 件追加 (`TestDedupPatternsEmbedding` クラス内):
- `test_dedup_skips_low_trust_existing_patterns` — trust=0.1 existing が dedup pool から除外、semantic 一致の new が ADD
- `test_dedup_keeps_trust_floor_boundary_in_pool` — trust=0.3 (TRUST_FLOOR boundary) は pool に残り、semantic 一致の new が SKIP

## 検証結果

```bash
uv run pytest tests/test_distill.py -q     # 52 passed (既存 50 + 新規 2)
uv run pytest tests/ -q                     # 1179 passed
```

## production 影響予測

`MEMORY.md` 記載「production 377 patterns で `trust_score` 91.5% が migration default 0.6 (>= TRUST_FLOOR 0.3)」より、本修正で dedup/evolution pool から外れる pattern はごく少数。実運用 shock は最小。

将来 trust_score の分布を migration default から動かす際 (F5 の対象) には、本 PR の挙動が「low-trust pattern を retrieval だけでなく dedup/evolution からも一貫して排除する」前提になる。F5 の判断材料の一部。

## 結論

- 既知の retrieval path (views / insight / constitution) は landing 時から適用済み
- distill 内部 (dedup / memory_evolution) に `valid_until` のみ check の gap が残っており、本 PR で `is_live` 経由に統一
- 今後 ADR で trust schema を変更しても `forgetting.is_live` の単一修正で全 consumer に伝播する形に整理完了
- 新たな未適用 path は本 audit の範囲では未発見
