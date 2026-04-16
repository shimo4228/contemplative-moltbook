# Contemplative Agent

自律 AI エージェントフレームワーク。構造的に権限を最小化（security by absence）。初期アダプタは Moltbook (AI エージェント SNS)。Contemplative AI 四公理はオプションプリセット。

## 構造

```
src/contemplative_agent/
  cli.py              # Composition root (唯一 core/ と adapters/ 両方を import)
  core/               # プラットフォーム非依存
  adapters/moltbook/  # Moltbook 固有
  adapters/meditation/ # Active Inference 瞑想 (experimental)
config/                 # テンプレートのみ (git 管理)
  prompts/            # LLM プロンプトテンプレート
  templates/          # identity シード + constitution デフォルト
  domain.json         # ドメイン設定
~/.config/moltbook/     # ランタイムデータ (MOLTBOOK_HOME, ユーザー固有)
  identity.md         # 人格定義 (蒸留で更新、ADR-0024 でブロック形式対応、legacy 平文は従来どおり動作)
  knowledge.json      # 蒸留済みパターン (embedding + gated + provenance/trust/bitemporal/forgetting/feedback, ADR-0019/0021)
  embeddings.sqlite   # episode embedding sidecar (ADR-0019)
  views/              # seed 文ビュー定義 (init でコピー、ユーザー編集可, ADR-0019)
  constitution/       # 倫理原則 (init でデフォルトコピー、コマンドで変更可)
  skills/             # 行動スキル (insight で生成、skill-reflect で改訂。ADR-0023 frontmatter 対応済み)
  rules/              # 行動ルール (rules-distill で生成)
  logs/               # エピソードログ (JSONL) + audit.jsonl (承認履歴)
                      # + identity_history.jsonl (ADR-0025 per-block ハッシュ変更記録)
                      # + skill-usage-YYYY-MM-DD.jsonl (ADR-0023 skill selection + outcome)
  snapshots/          # pivot snapshots (ADR-0020, 再現性のため views + constitution + centroids.npz を凍結)
  reports/            # アクティビティレポート (generate-report で生成)
tests/                # テストスイート
docs/adr/             # 設計判断の記録 (→ docs/adr/README.md)
docs/CODEMAPS/        # アーキテクチャ詳細 (→ docs/CODEMAPS/INDEX.md)
```

モジュール詳細・依存グラフ・データフローは [docs/CODEMAPS/](docs/CODEMAPS/INDEX.md) を参照。

### Import 規約

依存方向の根拠は [ADR-0001](docs/adr/0001-core-adapter-separation.md)。以下は運用規約:

- **core/ は adapters/ を import しない** (依存方向: adapters -> core)
- cli.py は composition root として両方を import (唯一の例外)
- core/ モジュールはコンストラクタ引数で設定を受け取る (パラメータ化)
- adapters/ が core/config の定数と adapter 固有の config を組み合わせて渡す
- 協力者 (ReplyHandler, PostPipeline, FeedManager) は Agent を import しない。SessionContext + Callable で依存注入

### Immutability

- DTO とドメインオブジェクトは `frozen=True`。例外なし
- accumulator パターンは reduce か一括生成で書く (mutation で書かない)
- 蒸留パイプラインの原典保持、承認ゲートの diff 生成、bitemporal との整合のため

## 開発環境

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# テスト
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing

# CLI
contemplative-agent --help
contemplative-agent init                          # MOLTBOOK_HOME に identity, knowledge, constitution, skills, rules 作成
contemplative-agent init --template stoic          # テンプレートを指定して初期化
contemplative-agent distill --dry-run             # 記憶蒸留 (dry run)
contemplative-agent distill --days 3              # 3日分を蒸留
contemplative-agent distill-identity              # アイデンティティ蒸留 (承認ゲート付き, 手動のみ)
contemplative-agent insight                       # 行動スキル抽出 (承認ゲート付き)
contemplative-agent insight --stage               # staging dir に出力 (コーディングエージェント用)
contemplative-agent insight --full                # 全パターンからスキル抽出
contemplative-agent skill-reflect                  # skill-usage から失敗率の高いスキルを改訂 (ADR-0023, 承認ゲート付き)
contemplative-agent skill-reflect --days 30 --stage # 集計ウィンドウ指定 + staging 出力
contemplative-agent adopt-staged                  # staging の全ファイルを承認ゲートに通して本配置 (監査ログ記録)
contemplative-agent rules-distill                 # 行動ルール蒸留 (承認ゲート付き)
contemplative-agent rules-distill --full          # 全パターンからルール蒸留
contemplative-agent amend-constitution            # 憲法改正 (承認ゲート付き)
contemplative-agent skill-stocktake               # スキル重複・品質監査
contemplative-agent rules-stocktake               # ルール重複・品質監査
contemplative-agent solve "ttwweennttyy pplluuss ffiivvee"
contemplative-agent generate-report               # 本日のアクティビティレポート生成
contemplative-agent generate-report --all          # 全日分を生成
contemplative-agent meditate --dry-run             # 瞑想シミュレーション (dry run)
contemplative-agent meditate --days 14 --cycles 100  # 14日分、100サイクル
contemplative-agent embed-backfill                 # ADR-0019 移行: 既存 patterns + 全 episode を bulk embed
contemplative-agent embed-backfill --patterns-only # patterns のみ
contemplative-agent embed-backfill --dry-run       # 件数と推定時間のみ
contemplative-agent migrate-patterns               # ADR-0021 移行: provenance/trust/bitemporal/forgetting/feedback 欠損フィールドを補完 (冪等)
contemplative-agent migrate-patterns --dry-run     # 変更対象の件数のみ表示
contemplative-agent migrate-identity               # ADR-0024 移行: legacy 平文 identity.md を block 形式に変換 (冪等)
contemplative-agent migrate-identity --dry-run     # backup path + block 形式プレビュー (書き込みなし)
contemplative-agent sync-data                     # 研究データを別リポジトリに同期
contemplative-agent install-schedule              # launchd 定期起動 (6h毎, 60分)
contemplative-agent install-schedule --weekly-analysis  # 週次分析レポートも追加 (毎週月曜 09:00)
contemplative-agent install-schedule --uninstall  # スケジュール削除

# カスタム constitution (別の倫理フレームワーク)
contemplative-agent --constitution-dir path/to/constitution/ run --session 30
# カスタムドメイン
contemplative-agent --domain-config path/to/domain.json run --session 30
```

- Python 3.9+ (venv は 3.13.5)
- 依存: requests, numpy。LLM は Ollama (qwen3.5:9b 生成 + nomic-embed-text 埋め込み, localhost)。Docker はオプション
- ビルド: hatch
- モジュール数・LOC・テスト数は [docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md) 参照（正本）

### Docker（オプション）

ネットワーク分離 + 非 root 実行を提供。通常の利用にはローカル Ollama で十分。

```bash
./setup.sh                                              # 初回: ビルド + モデルDL + 起動
./setup.sh llama3.1:8b                                  # 追加モデルのDL
docker compose up -d                                    # 2回目以降: 起動
docker compose logs -f agent                            # ログ確認
docker compose run agent command distill --days 3       # CLI パススルー
docker compose down                                     # 停止
```

- `docker-compose.override.yml` で既存データディレクトリをバインドマウント可能

## セキュリティ方針

- **1エージェント1外部アダプタ原則**: 外部に観測可能な副作用を持つアダプタは、1エージェントプロセスにつき最大1つ（ADR-0015）。複数の外部面を扱う場合は権限分離したマルチエージェントに分解
- 全外部入力を untrusted として扱う（`wrap_untrusted_content()`）。LLM 出力はサニタイズ（`_sanitize_output()`）
- API key: env var > credentials.json (0600)。ログには `_mask_key()` のみ
- HTTP: `allow_redirects=False`、ドメインロック (`www.moltbook.com` のみ)
- LLM: Ollama はローカルホスト + OLLAMA_TRUSTED_HOSTS のみ許可
- Docker: Ollama は internal-only ネットワーク（ADR-0006）。agent は非root (UID 1000)
- **Claude Code エピソードログ直読み禁止**: `~/.config/moltbook/logs/YYYY-MM-DD.jsonl` (+ `.bak`) を Read で直接読んではならない。プロンプトインジェクション経路。蒸留済み成果物を参照。同ディレクトリの `audit.jsonl` (承認履歴)、`identity_history.jsonl` (ADR-0025 per-block ハッシュのみ)、`skill-usage-YYYY-MM-DD.jsonl` (ADR-0023 selection + outcome)、`*.log` (launchd stderr) は自己書き込みなので読んでよい

セキュリティモデルの詳細は ADR-0007、Docker 分離は ADR-0006 を参照。

## ドキュメント言語方針

- CLAUDE.md、docs/CODEMAPS/ は日本語
- docs/adr/ は英語（*.ja.md が日本語版）
- README.md は英語（README.ja.md が日本語版）

## API レート制限

GET 60 req/min、POST 30 req/min（分離クォータ）。3層防御（`has_read_budget()`/`has_write_budget()` バジェット、プロアクティブ待機、リアクティブバックオフ）。API 仕様の詳細は `WebFetch https://www.moltbook.com/skill.md` で最新を参照。

## テスト

テスト数・カバレッジは [docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md) を参照（正本）。

## メモリアーキテクチャ

3層メモリ + AKC マッピングの詳細は [docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md)、設計経緯は [ADR-0004](docs/adr/0004-three-layer-memory.md) を参照。

## 残課題

ADR-0023..0025 後に残っている積み残しは [.reports/remaining-issues-2026-04-16.md](.reports/remaining-issues-2026-04-16.md) に集約。特に insight の ADR-0023 frontmatter 未対応（N1）と noise/uncategorized/constitutional 分類の冗長性（N4）は着手優先度が高い。

## 関連リポジトリ

- [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) — 四公理ルール、アダプタ、ベンチマーク
- [contemplative-agent-data](https://github.com/shimo4228/contemplative-agent-data) — ランタイムデータ（研究用、sync-data で同期）

## 論文

Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. arXiv:2504.15125

Laukkonen, R., Friston, K., & Chandaria, S. (2025). A Beautiful Loop. Neuroscience & Biobehavioral Reviews. (瞑想の計算モデル — meditation adapter の理論的基盤)
