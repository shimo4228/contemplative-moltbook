# ADR-0019 Migration Guide

**生成日**: 2026-04-15
**対象 ADR**: [0019](../adr/0019-discrete-categories-to-embedding-views.md) — 離散カテゴリ廃止 → embedding + views
**前提**: 全 5 commits (`aaff3b8..HEAD`) が merge 済みの HEAD。`nomic-embed-text` モデルが pull 済み。

このガイドは「既存 knowledge.json + episode log に embedding を後付けして ADR-0019 の新スキーマに移行する」ための手順。初回実行時は順にやる。

---

## Step 1: 前提確認 (2 分)

```bash
# Ollama embed model が pull 済みか
ollama list | grep nomic-embed-text

# knowledge.json の現状サイズ
du -h ~/.config/moltbook/knowledge.json

# episode log の期間と容量
ls -lah ~/.config/moltbook/logs/*.jsonl | head
```

**目安**: pattern 100 件 + episode 過去 1 ヶ月なら ~2-3 分。半年以上溜まってるなら ~30 分以上。

## Step 2: dry-run で規模確認

```bash
uv run contemplative-agent embed-backfill --dry-run
```

**見るべき出力:**
- `patterns total`: 既存パターン数（0.4MB/100件 の目安）
- `episodes total`: SQLite sidecar の最終サイズ試算（~5KB/episode）
- `errors`: **0 でないと次に進まない**。特に「noise view centroid unavailable」は `config/views/noise.md` → `~/.config/moltbook/views/noise.md` のコピー失敗、または Ollama embed 呼び出し失敗

## Step 3: 本実行

```bash
# patterns だけ先に（LLM 品質への影響を早く観察したい場合）
uv run contemplative-agent embed-backfill --patterns-only

# 全部一気に
uv run contemplative-agent embed-backfill
```

**自動で取られる安全策:**
- `knowledge.json.bak.{timestamp}` に migration 前の knowledge を退避
- `audit.jsonl` に migration 履歴記録

`~/.config/moltbook/` は git 管理外なので、この bak ファイルが唯一のロールバック先。`contemplative-agent-data` リポジトリの最終 sync 時点以降の差分は含まれない点に注意。

## Step 4: 動作確認（重要）

```bash
# distill が embedding 経路で動くか
uv run contemplative-agent distill --dry-run --file tests/fixtures/benchmark/synthetic.jsonl

# identity 蒸留が view 経由で self_reflection 拾えるか
uv run contemplative-agent distill-identity --dry-run

# skill-stocktake 回帰
uv run contemplative-agent skill-stocktake --dry-run
```

**観察ポイント:**
- distill の `Step 0: N constitutional, M uncategorized, K noise` の比率が旧 LLM 版と大きく乖離していないか
- identity 蒸留で self_reflection パターンが 3 件未満だと "No self-reflection patterns" で停止する
- LLM コール数の激減（Ollama ログで確認 — 旧 classify 分が完全消滅しているはず）

## Step 5: 問題が出た場合の戻し方

### ケース A: dedup 閾値が厳しすぎ／緩すぎ

`src/contemplative_agent/core/distill.py`:
```python
SIM_DUPLICATE = 0.92  # 既存 skip 閾値。下げる → 重複判定が増える
SIM_UPDATE = 0.80     # importance boost 閾値
```

変更後 `distill --dry-run` で影響を見てから commit。変更が非自明なら **ADR-0020 以降を追加**して根拠を記録する。

### ケース B: classify が noise に引っ張られすぎ

`src/contemplative_agent/core/distill.py`:
```python
NOISE_THRESHOLD = 0.55          # 上げる → noise 判定が減る
CONSTITUTIONAL_THRESHOLD = 0.55  # 上げる → constitutional 判定が厳しくなる
```

または `~/.config/moltbook/views/noise.md` の seed 文を具体化（例: `"actual test pings, error tracebacks, status codes"` のような典型例を追記）。user-local views は git 管理外なので自由に調整できる。

### ケース C: view が狙った pattern を拾わない

`~/.config/moltbook/views/<name>.md` の frontmatter `threshold` を下げる (0.55 → 0.45) か、seed 文を肉付け。

### ケース D: 完全に戻したい

```bash
# 1. knowledge.json を migration 前に復元
cp ~/.config/moltbook/knowledge.json.bak.{ts} ~/.config/moltbook/knowledge.json

# 2. SQLite sidecar を破棄
rm ~/.config/moltbook/embeddings.sqlite

# 3. コードを revert
git revert aaff3b8..HEAD   # ADR-0019 全 5 commits + /simplify
```

---

## 今後の運用（長期）

### 新しい view を追加したい

`~/.config/moltbook/views/<name>.md` に seed 文を置くだけ。insight が次回実行時に自動でバッチ化候補に入る（`self_reflection` / `noise` / `constitutional` 以外）。**migration 不要**。

### Embedding model を変更したい

`OLLAMA_EMBEDDING_MODEL` 環境変数で切り替え可能。**ただし次元や空間が変わるので既存 embedding は使えない:**

```bash
export OLLAMA_EMBEDDING_MODEL=new-model

# 既存 embedding を破棄
rm ~/.config/moltbook/embeddings.sqlite
# knowledge.json から embedding 列を剥がす必要あり (手動 or jq スクリプト)

# 再 backfill
uv run contemplative-agent embed-backfill
```

### Episode sidecar が肥大化してきた

SQLite サイズは年間 ~1GB ペース。古い episode の embedding が不要になったら:

```bash
# 現状は手動 (--prune-days は未実装)
sqlite3 ~/.config/moltbook/embeddings.sqlite \
  "DELETE FROM episode_embeddings WHERE ts < '2025-10-01'"
```

将来的に `embed-backfill --prune-days N` を実装する候補。

### Threshold を非自明に動かしたとき

`SIM_DUPLICATE`, `SIM_UPDATE`, `NOISE_THRESHOLD`, `CONSTITUTIONAL_THRESHOLD` のいずれかを動かした場合は **ADR を追加**する（例: ADR-0020 として「SIM_DUPLICATE を 0.92 → 0.88 に下げた理由」）。閾値をサイレントに変えると再現不能な挙動変化の原因になる。

---

## 最初に走らせるときの推奨シーケンス

1. **週末など時間のある日** に実行（過去全 episode backfill で 30 分+ かかりうる）
2. **実行前に `contemplative-agent sync-data`** で `contemplative-agent-data` リポジトリに同期（二重バックアップ）
3. **backfill 後すぐに `distill --dry-run` で比較** — 今日の episode が旧 LLM classify 版と大きく違う分類になっていないか目視確認
4. **違和感があれば threshold を調整してから本番 distill** を走らせる

原則: **「dry-run → 実行 → 確認 → (閾値調整)」のループで段階的に馴染ませる**。LLM コール激減が主目的なので、1 日後に launchd distill ログの timing 比較で効果を定量化できる。

---

## 関連ファイル

- ADR: `docs/adr/0019-discrete-categories-to-embedding-views.md` (英) / `.ja.md` (日)
- Migration 実装: `src/contemplative_agent/core/migration.py`
- Embedding utilities: `src/contemplative_agent/core/embeddings.py`
- View 定義: `config/views/*.md` (template) → `~/.config/moltbook/views/*.md` (user copy)
- Episode sidecar: `src/contemplative_agent/core/episode_embeddings.py`
