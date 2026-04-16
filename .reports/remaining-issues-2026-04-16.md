# Remaining Issues — 2026-04-16

今日のセッション（ADR-0023 / 0024 / 0025 + `/simplify`）の後に残っている課題の棚卸し。着手順序は Severity と依存関係から判断してよい。ここに書いてあるもの以外は今のところ認識していない。

## Session A (2026-04-16) で解消した項目

- **N1** — insight が ADR-0023 frontmatter を emit（commit `617f740`）
- **D1** — skill_router を reply_handler / post_pipeline から配線（commit `5cae245`）
- **N3** — insight の top-N を `effective_importance` (trust×strength 込み) で並び替え（Session A）
- **N2** — insight が `is_live(p)` を尊重、superseded pattern を skill 抽出から除外（Session A）

## Session B (2026-04-16) で解消した項目

- **D2** — `skill-reflect` CLI 追加（承認ゲート付き、`--stage` / `--days` 対応）。`core/skill_reflect.py` に `reflect_skills()` を実装。usage window で eligible skill を選び、failure contexts を prompt に埋めて revise、`last_reflected_at` を frontmatter に反映。NO_CHANGE 出力はスキップ。

## 1. ADR-0023..0025 からの明示的な deferred（next ADR 候補）

| # | 項目 | ADR | Severity | ポインタ / メモ |
|---|---|---|---|---|
| ~~**D1**~~ | ~~`skill_router` を `agent.run_session` / `agent.do_solve` に配線する~~ | ~~ADR-0023~~ | ~~medium~~ | **完了** (commit `5cae245`) |
| ~~**D2**~~ | ~~`skill-reflect` CLI を追加（承認ゲート付き、`insight --stage` と同じ形）~~ | ~~ADR-0023~~ | ~~medium~~ | **完了**（Session B）。`core/skill_reflect.py` + CLI handler。`--stage`/`--days` 対応。テスト: `tests/test_skill_reflect.py` |
| **D3** | 識別子ブロックごとの distill routing（`current_goals` を自分のビュー + 自分のプロンプトで refresh 等） | ADR-0024 | high-effort | ブロックごとの prompt を **qwen3.5:9b 自身に書かせる** 必要あり（prompt-model-match memory）。config の形状追加 + 複数ファイルに影響。 |
| **D4** | runtime `agent-edit` tool（セッション中に個別ブロックを更新できる） | ADR-0024 | deep | ADR-0013 authorship-problem + ADR-0017 manas フレームと接続。実装前に独立 ADR で設計議論が必要。 |

## 2. 今日の `/simplify` / レビューで新たに浮上した課題

### 2.1 `insight` コマンドの ADR-0021/0023 との整合性ギャップ

| # | 項目 | 場所 | Severity | メモ |
|---|---|---|---|---|
| ~~**N1**~~ | ~~`insight` が生成する skill ファイルに ADR-0023 frontmatter が入らない~~ | `src/contemplative_agent/core/insight.py:295` | ~~**high**~~ | **完了** (commit `617f740`)。parse-then-render で LLM の legacy frontmatter と router fields を単一ブロックにマージ。 |
| ~~**N2**~~ | ~~`insight` が ADR-0021 の `valid_until` フィルタを尊重していない~~ | `src/contemplative_agent/core/insight.py:207, 211` | ~~medium~~ | **完了**（Session A）。`extract_insight` が `is_live(p)` で superseded pattern を除外。テスト: `TestExtractInsightSupersededExclusion`。 |
| ~~**N3**~~ | ~~`insight` が `trust_score` を使わずに `importance` のみで top-N を決めている~~ | `src/contemplative_agent/core/insight.py:130` | ~~medium~~ | **完了**（Session A）。`_build_view_batches` が `effective_importance` で並び替え、trust×strength を反映。テスト: `test_effective_importance_orders_by_trust`。 |

### 2.2 `noise / uncategorized / constitutional` 分類の冗長性

| # | 項目 | 場所 | Severity | メモ |
|---|---|---|---|---|
| **N4** | category 層と views 層が意味的に重複。`constitutional` は category AND view として存在し、しかも insight は `category="uncategorized"` で先に絞るので **constitutional view は skill 抽出から到達不能** | `distill.py:338–430`（`_classify_episodes`）、`insight.py:37`（`_INSIGHT_EXCLUDED_VIEWS`）、`insight.py:207` | medium | ADR-0019 で discrete label 廃止の方針が既に宣言済み（`migration.py:7` のコメント参照）。段階的廃止の道筋:<br>**Phase 1**: `insight` の `category=="uncategorized"` 事前フィルタを外し、`constitutional` view を `_INSIGHT_EXCLUDED_VIEWS` から取り除く。read 側を views に統一。<br>**Phase 2**: write 側の `_classify_episodes` を 3 値分類から binary `gated`（noise view centroid 一致で skip）に変える。constitutional / uncategorized の区別を廃止。<br>**Phase 3**: Pattern schema から `category` フィールドを完全に除去（下位互換は migration で吸収）。<br>スコープ感: ~150 LOC 程度、独立 ADR が妥当。 |

### 2.3 pre-session コードの積み残し（`/simplify` で skip したもの）

| # | 項目 | 場所 | Severity | メモ |
|---|---|---|---|---|
| **N5** | `CLAUDE.md` が CODEMAPS と内容重複（structure / CLI 一覧 / dependencies） | `CLAUDE.md:5–92` vs `docs/CODEMAPS/` | low | context-sync のロール分離に反する。今回は **あえて修正せず**、単独のドキュメント掃除セッションで対応。 |
| **N6** | `_build_system_prompt` が LLM generate 呼び出しのたびに skills/ と rules/ の .md を glob + read | `src/contemplative_agent/core/llm.py:235, 242` | low | identity 側は `/simplify` で mtime キャッシュ追加済み。skills/ rules/ も同形式で吸収可。セッションあたり 50 generate × N ファイル単位の I/O。 |
| **N7** | `_dedup_patterns` の戻り値型注釈が `Tuple` に削られている（5-tuple/6-tuple 可変） | `src/contemplative_agent/core/distill.py:717` | medium | `return_indices` パラメータで shape が変わる。実際の呼び出しは 1 箇所で常に `True`。フラグ削除 + 6-tuple 固定化が妥当。 |
| **N8** | `apply_revision` が neighbor dict を in-place で mutate し、KnowledgeStore API をバイパス | `src/contemplative_agent/core/memory_evolution.py:161`、`distill.py:697` | medium | coding-style.md の immutability 規約に反する。`_learned_patterns` private field に直接手を入れている。モック/ロールバック不可能。`KnowledgeStore.add_revised_patterns()` 相当を追加するのが筋。 |
| **N9** | `_trust_for_source("mixed")` が `min(0.9, 0.55) = 0.55` を返すが、`TRUST_BASE_BY_SOURCE["mixed"] = 0.5` | `src/contemplative_agent/core/distill.py:463–470` | low | 片方を変えるとサイレントにズレる。特殊ケースを撤去して定数参照に統一するだけ。 |
| **N10** | 同パッケージ import を `try/except Exception` で覆う | `src/contemplative_agent/core/distill.py:673–678` | low | 本当の import 失敗を握りつぶす。fallback パスは本番で一度も走っていない。import を top に移動して、スキップは `MEMORY_EVOLUTION_PROMPT` 文字列の空判定で行う。 |
| **N11** | `identity_history.jsonl` / `skill-usage-*.jsonl` の成長上限なし | `identity_blocks.py`、`skill_router.py` | low | ADR-0021 / ADR-0025 で明示的に「rotation なし」を選んでいる（append-only 規約）。将来 `inspect-identity-history` / `prune-usage-log` CLI を足す余地。 |
| **N12** | `_now_iso()` が 2 定義（`timespec` 不一致） + 8 箇所以上のインライン呼び出し | `feedback.py:23`（minutes）、`identity_blocks.py:493`（seconds）、`distill.py:640, 739`、`knowledge_store.py:111`、`memory_evolution.py:158`、`migration.py:368`、`forgetting.py:89`、`insight.py:163`、`rules_distill.py:185` | low | ログ同士のタイムスタンプ粒度がサイレントにズレる。`_io.py` に統合するのが自然。 |
| **N13** | `umask(0o177) + open("a")` JSONL 追記パターンが 5 箇所で重複 | `skill_router.py:288`、`cli.py:280`（`_log_approval`）、`episode_log.py:48`、`episode_embeddings.py:70`、`scheduler.py:73` | low | `_io.append_restricted(path, line)` 相当を作るだけで全部吸収できる。 |

## 3. 運用で気にしておくべきポイント（バグになりうる箇所）

- **identity_history は現在 `persona_core` しか記録しない** — D3（per-block routing）が動き出したら、`IdentityResult.block_name` のスレッディングはあるが **emitter 側に実装が必要**。silent data loss ではなく「単一ブロックのみ」で止まる形。
- **`_handle_adopt_staged` に identity 専用分岐がある** — `if command == "distill-identity" and target == IDENTITY_PATH` の文字列一致。3 件目の post-write hook が欲しくなった時点で、dispatch テーブルに移す方が良い（`adopt-staged` が generic な loop でなくなる方向は避けたい）。
- **`skill_router._cache` は `Dict[Path, Tuple[float, np.ndarray, SkillMeta, str]]`** — body がメモリに載る。現状のスキル数（20–30）では <1 MB で無害。D2 で agent-generated skill が 200 超になったら再評価。
- **`MigrationResult.document` / `.rendered` は Optional** — 呼び出し側は `.migrated` を先にチェックすること（CLI は既にそうなっている）。将来の呼び出し側が同じ順序で触らないと AttributeError。
- **`load_for_prompt` の mtime キャッシュは module-level** — 単一プロセスでは正しいが、テストが並列で異なる `_identity_path` を使うと理論上 pollution の可能性あり。今のところ green。flaky になったらここを疑う。
- **`distill-identity` は `persona_core` body のみ LLM に渡す** — block ファイルに `current_goals` 等が存在しても、distill はそれらを参照しない。ユーザーの期待と乖離する可能性があるので README 側で明示が必要になったら追記。

## 4. 次に配線が入った時に必ず走らせる検証

- **D1 配線後**: `run --session 30` を verbose で走らせ、`~/.config/moltbook/logs/skill-usage-YYYY-MM-DD.jsonl` に `selection` レコードが溜まるのを目視。閾値 0.45 を割り続けるなら threshold を下げる。
- **D2 配線後**: `prototype-before-scale` に従い、3–5 の skill で smoke run してから全件対象に広げる。失敗率 >30% の skill に `NO_CHANGE` が返ってくるかも確認。
- **N1 修正後**: `insight` を一度走らせ、出力 skill ファイルが YAML frontmatter 付きで始まることと、既存の `skill-stocktake` がそれをパースできることを確認。
- **N4 Phase 1 後**: `distill` を 1 日分のエピソード上で走らせ、`knowledge.json` を before/after で diff。constitutional な pattern が従来と同じように保持されているか（read 側のルートは views に移行したか）を確認。
- **N8 修正後**: `evolve_patterns` のテストをモックなしで走らせ、`KnowledgeStore._learned_patterns` への書き込みが公開 API 経由になったことを確認。

## 参考

- Phase レポート: [`phase-3-report.md`](phase-3-report.md) / [`phase-4-report.md`](phase-4-report.md) / [`phase-5-report.md`](phase-5-report.md)
- ADR: [`docs/adr/0023..0025`](../docs/adr/)
- simplify コミット: `420435a refactor: /simplify cleanup on ADR-0023..0025 session work`
