Language: [English](README.md) | 日本語

# Contemplative Agent

ソーシャルプラットフォーム上で自律的に活動する AI エージェントフレームワーク。汎用エージェントフレームワークが抱えるセキュリティ脆弱性のクラスを構造的に排除する設計。

[OpenClaw](https://github.com/openclaw/openclaw) は、AI エージェントに広範なシステムアクセスを与えることが本質的に危険な攻撃面を生むことを実証した — [512件の脆弱性](https://www.tenable.com/plugins/nessus/299798)、[WebSocket 経由の完全なエージェント乗っ取り](https://www.oasis.security/blog/openclaw-vulnerability)、[22万以上のインスタンスがインターネットに露出](https://www.penligent.ai/hackinglabs/over-220000-openclaw-instances-exposed-to-the-internet-why-agent-runtimes-go-naked-at-scale/)。本フレームワークは逆のアプローチを取る: **能力をコードレベルで構造的に制限**し、Docker コンテナ化で強制する。悪用すべきシェル実行がなく、乗っ取るべき任意のネットワークアクセスがなく、トラバースすべきファイルシステムがない。プロンプトインジェクションは、エージェントに最初から組み込まれていない能力を付与できない。

> 初期アダプタ: [Moltbook](https://www.moltbook.com)（AI エージェント SNS）。Contemplative AI の四公理（[Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)）はオプションのプリセットとして含まれている。

## クイックスタート

[Claude Code](https://claude.ai/claude-code) をお持ちなら、このリポジトリの URL を貼り付けてセットアップを依頼するだけ。clone、設定、`./setup.sh` の実行まで全て行ってくれる。必要なのは `MOLTBOOK_API_KEY` の提供のみ（先に [moltbook.com](https://www.moltbook.com) で登録が必要）。

手動の場合:

```bash
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
cp .env.example .env
# .env を編集 — MOLTBOOK_API_KEY を設定（任意で OLLAMA_MODEL も）
./setup.sh                            # ビルド + モデル DL (~5GB) + 起動
```

```bash
docker compose logs -f agent          # ログを監視
docker compose run agent command status   # ステータス確認
docker compose down                   # 停止
docker compose up -d                  # 再起動（setup.sh 不要）
./setup.sh llama3.1:8b               # 追加モデルの DL
```

## セキュリティアーキテクチャ

エージェントはハードコードされた構造的制約の中で動作する — LLM によるガイドラインではなく:

| 攻撃ベクトル | OpenClaw | Contemplative Agent |
|-------------|----------|---------------------|
| **シェル実行** | コア機能 — [コマンドインジェクション CVE](https://www.tenable.com/plugins/nessus/299798) | コードベースに存在しない |
| **ネットワークアクセス** | 任意 — [SSRF 脆弱性](https://www.tenable.com/plugins/nessus/299798) | `moltbook.com` + localhost Ollama にドメインロック |
| **ローカルゲートウェイ** | localhost の WebSocket — [ClawJacked 乗っ取り](https://www.oasis.security/blog/openclaw-vulnerability) | リスニングサービスなし |
| **ファイルシステム** | フルアクセス — パストラバーサルリスク | `MOLTBOOK_HOME` のみに書き込み、0600 パーミッション |
| **LLM プロバイダ** | 外部 API キーが通信中に漏洩リスク | ローカル Ollama のみ（v0.18.0 固定）— データはマシンの外に出ない |
| **依存関係** | 大規模な依存ツリー | ランタイム依存は `requests` のみ |
| **コンテナ** | root で実行、Docker ソケット付きの場合も | 非 root (UID 1000)、Ollama はインターネットから隔離（セットアップ時のみモデル DL 用に接続） |

違いはアーキテクチャレベル: OpenClaw は発見された脆弱性をその都度パッチする必要がある。本フレームワークには悪用すべきシェル、任意のネットワーク、ファイルトラバーサルがそもそも存在しない。

> 私たちの言葉を信じる必要はない — このリポジトリの URL を [Claude Code](https://claude.ai/claude-code) やコード対応 AI に貼り付けて、実行しても安全か聞いてみてほしい。コードが自ら語る。

## エージェントのカスタマイズ

デフォルトのエージェントはニュートラルな人格で、公理なしで起動する。Markdown ファイルを編集してエージェントの振る舞いを定義:

```
config/rules/
  default/              # ニュートラル（デフォルトで有効）
    introduction.md       # Moltbook での自己紹介
  contemplative/        # Contemplative AI プリセット（四公理）
    introduction.md
    contemplative-axioms.md
  your-agent/           # 自分で作成
    introduction.md
    contemplative-axioms.md  # 任意: 憲法条項
```

環境変数または CLI フラグでプリセットを選択:

```bash
# Docker (.env)
RULES_DIR=config/rules/contemplative/

# CLI
contemplative-agent --rules-dir config/rules/contemplative/ run --session 60
```

詳細は [`config/rules/README.md`](config/rules/README.md) を参照。

## 設定

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `MOLTBOOK_API_KEY` | (必須) | Moltbook API キー |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Ollama モデル名 |
| `SESSION_MINUTES` | `30` | セッション時間（分） |
| `BREAK_MINUTES` | `5` | セッション間の休憩（分） |
| `MODE` | `loop` | `loop`, `single`, `command` |
| `RULES_DIR` | (ニュートラル) | ルールディレクトリのパス |

## ローカルセットアップ

Docker なしでの開発:

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
ollama serve && ollama pull qwen3.5:9b
```

```bash
contemplative-agent init              # identity + knowledge ファイル作成
contemplative-agent register          # Moltbook に登録
contemplative-agent run --session 60  # セッション実行
contemplative-agent distill --days 3  # エピソードログの蒸留
```

### 自律レベル

- `--approve`（デフォルト）: 投稿ごとに y/n 確認
- `--guarded`: 安全フィルター通過時に自動投稿
- `--auto`: 完全自律

### スケジューリング (macOS)

```bash
contemplative-agent install-schedule              # 6時間間隔、120分セッション
contemplative-agent install-schedule --uninstall  # スケジュール削除
```

## アーキテクチャ

```
src/contemplative_agent/
  core/             # プラットフォーム非依存
    llm.py            # Ollama インターフェース、サーキットブレーカー、出力サニタイズ
    memory.py         # 3層メモリ（エピソードログ + ナレッジ + アイデンティティ）
    distill.py        # スリープタイム記憶蒸留
    domain.py         # ドメイン設定 + プロンプト/ルールローダー
    scheduler.py      # レート制限スケジューリング
  adapters/
    moltbook/       # Moltbook 固有（初期アダプタ）
      agent.py          # セッションオーケストレータ
      feed_manager.py   # フィードスコアリング + エンゲージメント
      reply_handler.py  # 通知返信
      post_pipeline.py  # 動的投稿生成
      client.py         # ドメインロック HTTP クライアント
  cli.py            # コンポジションルート
config/
  domain.json       # ドメイン設定（サブモルト、閾値、キーワード）
  prompts/*.md      # LLM プロンプトテンプレート（13ファイル）
  rules/            # エージェント人格プリセット
```

- **core/** はプラットフォーム非依存。**adapters/** は core に依存（逆方向は禁止）
- 新しいプラットフォームアダプタは `adapters/` に追加するだけで、core を変更する必要なし

### メモリ（3層）

| レイヤー | ファイル | 目的 |
|---------|---------|------|
| エピソードログ | `logs/YYYY-MM-DD.jsonl` | 全アクションの追記専用記録 |
| ナレッジ | `knowledge.md` | 蒸留されたパターンと洞察 |
| アイデンティティ | `identity.md` | システムプロンプト（LLM の人格） |

## テスト

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing
```

558 テスト。

## アクティビティレポート

日次レポートは [`reports/comment-reports/`](reports/comment-reports/) に保存 — タイムスタンプ付きコメント、relevance スコア、自動生成投稿を含む。セッション終了時にエピソードログから自動生成。

これらのレポートは学術研究および非商用利用に自由に利用可能。

## 参考文献

Laukkonen, R. et al. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125)
