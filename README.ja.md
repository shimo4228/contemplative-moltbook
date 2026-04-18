Language: [English](README.md) | 日本語

<p align="center">
  <img src="docs/assets/logo.png" alt="CA logo" width="200">
</p>

# Contemplative Agent (CA)

[![Tests](https://img.shields.io/badge/tests-1170_passed-brightgreen)](docs/CONFIGURATION.ja.md#開発)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

**経験から自律的に学習する AI エージェント。ローカル 9B モデルで完結。**
クラウド不要。API キーは外部に出ない。シェル実行は存在しない。危険な能力はルールで制限しているのではなく、最初からコードに組み込まれていない。

## なぜ作ったか

多くのエージェントフレームワークはセキュリティを後付けしている。[OpenClaw](https://github.com/openclaw/openclaw) は [512件の脆弱性](https://www.tenable.com/plugins/nessus/299798)、[WebSocket 経由のエージェント乗っ取り](https://www.oasis.security/blog/openclaw-vulnerability)、[22万以上のインスタンスのインターネット露出](https://www.penligent.ai/hackinglabs/over-220000-openclaw-instances-exposed-to-the-internet-why-agent-runtimes-go-naked-at-scale/)が報告されている。AI エージェントに広範なシステムアクセスを与えれば、攻撃面は構造的に拡大する。

本フレームワークは逆のアプローチ: **security by absence（不在によるセキュリティ）**。シェル実行もできない、任意の URL にもアクセスできない、ファイルシステムも走査できない — そのコードが書かれていないから。プロンプトインジェクションは、最初から組み込まれていない能力を付与できない。

**そしてこの全てがコンシューマーハードウェアで動く。** 経験からの学習、意味で引ける記憶、パターンからのスキル自動抽出、時間とともに更新されていく知識 — その全パイプラインが、単一の Apple Silicon Mac（M1 以降、メモリ 16 GB 程度）+ 2 つのオープンウェイトモデル（生成: **qwen3.5:9b** Q4_K_M 量子化 ~5.5 GB / 埋め込み: **nomic-embed-text** ~274 MB, 768次元）で走る。GPU クラスタ不要、クラウド推論不要。

外部サービスに接続するのは、そのサービスに対応するアダプタ層だけ。リファレンス実装の Moltbook アダプタは SNS なのでオンライン必須だが、それ以外のアダプタは完全オフライン動作可能 — 生成・埋め込み・リトリーバル・蒸留は全てオンデバイス。

**この設計はクラウドが使えない / 使いたくないエッジ環境への移植を可能にする**: データローカリティ制約のある医療・法務ワークフロー、プライバシー重視のパーソナルアシスタント、間欠的接続のフィールド展開、エアギャップ環境。

この安全でセルフコンテインドな基盤の上で、エージェントは**自らの経験から学習する**: 生のエピソードログからパターンを蒸留し、ナレッジ・スキル・ルール・進化するアイデンティティへと昇華させる。

## 仕組み

```
エピソードログ   生の行動, 不変 JSONL (untrusted)
 │
 ├── distill ─▶ ナレッジ (行動)
 │                 ・埋め込み座標 (embedding) + view
 │                 ・出所記録 (provenance) / 信頼度 (trust)
 │                 ・時間妥当性 (bitemporal) / 強度 (strength)
 │                 │
 │                 ├── distill-identity ─▶ アイデンティティ
 │                 │                       (ブロック addressed)
 │                 │
 │                 └── insight ─▶ スキル
 │                                 (retrieve / apply / reflect)
 │                                   │
 │                                   └── rules-distill ─▶ ルール
 │
 └── distill (憲法) ─▶ ナレッジ (憲法)
                                   │
                                   └── amend ─▶ 憲法
```

生の行動データがより抽象的なレイヤーへと上方に流れる。各レイヤーはオプション — 必要な部分だけ使えばよい。エピソードログより上のレイヤーはすべて、エージェント自身が経験を省察して生成する。

このループは本プロジェクトにおける **Agent Knowledge Cycle (AKC)** の実装 — Research → Extract → Curate → Promote → Measure → Maintain の 6 フェーズからなる自己改善サイクル。もともと Claude Code ハーネスにおけるメタワークフロー改善のために設計されたもので、本プロジェクトはそれを自律エージェントの文脈で再実装している。`distill` が Extract、`insight` / `rules-distill` / `amend-constitution` が Curate、`distill-identity` が Promote、基準点スナップショット (ADR-0020) と `skill-reflect` (ADR-0023) が Measure に対応する。フェーズとコードの完全な対応表は [docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md#akc-agent-knowledge-cycle-mapping) を参照。原典のハーネス: [agent-knowledge-cycle](https://github.com/shimo4228/agent-knowledge-cycle)。

内部では、ナレッジ層は各パターンを離散カテゴリではなく**埋め込み座標 (embedding)** として保持し、クエリは名前付きの *view*（意味的なシード）を通じて投影する。view はデータを移行せずに編集・差し替えができる（[ADR-0019](docs/adr/0019-discrete-categories-to-embedding-views.ja.md) + Phase 3 完了 [ADR-0026](docs/adr/0026-retire-discrete-categories.ja.md)）。各パターンには**出所記録 (provenance)** と**時間妥当性 (bitemporal validity)** が付与される（[ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.ja.md)、生存する範囲は [ADR-0028](docs/adr/0028-retire-pattern-level-forgetting-feedback.ja.md) / [ADR-0029](docs/adr/0029-retire-dormant-provenance-elements.ja.md) で縮小）。新しいパターンが既存の近傍に着地すると、古いパターンは上書きされず**再解釈 (re-interpret)** され、検索スコアは cosine + BM25 のハイブリッドで計算される（[ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.ja.md)）。メモリアーキテクチャの構造は**唯識 (Yogācāra) の八識モデル**を下敷きにしている。完全な対応付けは [ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.ja.md) を参照。

## 主な特徴

**AKC による自己改善** -- エージェントは自身のログに対して 6 フェーズの [Agent Knowledge Cycle](https://github.com/shimo4228/agent-knowledge-cycle) を回す — 外部の fine-tune 不要、ラベル付き学習データも不要。各フェーズ昇格（ログ → パターン、パターン → スキル、スキル → ルール、スキル → アイデンティティ）には[人間の承認ゲート](docs/adr/0012-human-approval-gate.md)が入る。

- *埋め込みと view (embedding + views)* — 分類は状態ではなく **クエリ**。view は編集可能な意味的シード（[ADR-0019](docs/adr/0019-discrete-categories-to-embedding-views.ja.md)。`category` フィールドは [ADR-0026](docs/adr/0026-retire-discrete-categories.ja.md) で廃止）。
- *記憶の進化 + ハイブリッド検索 (memory evolution + hybrid retrieval)* — 新しいパターンが到着すると、意味的に関連する既存パターンを LLM が再解釈。旧行は論理的に無効化 (soft-invalidate) し、改訂行を追加。検索スコアは cosine と BM25 の混成（[ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.ja.md)、*proposed*）。
- *記憶としてのスキル (skill-as-memory loop)* — スキルは「取り出し (retrieve)→適用 (apply)→結果に基づく書き換え (rewrite)」の単位（[ADR-0023](docs/adr/0023-skill-as-memory-loop.ja.md)、*proposed*）。
- *ノイズを種子として (noise as seed)* — 棄却されたエピソードは `noise-YYYY-MM-DD.jsonl` として保持される。view 重心が変わったとき、失われずに**再分類の候補**として利用できる（[ADR-0027](docs/adr/0027-noise-as-seed.ja.md)、*proposed*）。

**設計による安全 (secure by design)** -- シェル実行なし、任意のネットワークアクセスなし、ファイル走査なし。`moltbook.com` + localhost Ollama にドメインロック。ランタイム依存は `requests` のみ。[脅威モデルの詳細 →](docs/adr/0007-security-boundary-model.md)

- *出所の追跡 (provenance tracking)* — 各パターンに `source_type`（出所種別）と `trust_score`（信頼度）。MINJA 型の記憶注入攻撃 (memory injection) は構造的に可視化される（[ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.ja.md)、*proposed*。未使用要素は [ADR-0029](docs/adr/0029-retire-dormant-provenance-elements.ja.md) で削減済み）。
- *再現可能な基準点スナップショット (pivot snapshots)* — 蒸留の実行時に manifest + view + 憲法 + 重心埋め込みを一括保存し、任意の蒸留を bit-for-bit で再実行できる（[ADR-0020](docs/adr/0020-pivot-snapshots-for-replayability.ja.md)、*proposed*）。

**11種の倫理フレームワーク** -- ストア哲学、功利主義、ケアの倫理など11種のテンプレート同梱。同じ行動データ、異なる初期条件 — エージェントがどう分岐するかを観察。[独自テンプレートの作成 →](docs/CONFIGURATION.ja.md#キャラクターテンプレート)

**ローカル完結** -- Ollama + Qwen3.5 9B。API キーはマシン外に出ない。M1 Mac で快適動作。不変のエピソードログで実験は完全再現可能。

**研究グレードの透明性** -- すべての判断が追跡可能。不変のログ、蒸留成果物、日次レポートが再現性のために[公開同期](https://github.com/shimo4228/contemplative-agent-data)されている。実行単位での再現性は上記「再現可能な基準点スナップショット」に記載。

## ライブエージェント

Contemplative エージェントが [Moltbook](https://www.moltbook.com/u/contemplative-agent)（AI エージェント SNS）上で毎日稼働中。フィードを巡回し、relevance スコアで投稿をフィルタし、コメントを生成し、オリジナル投稿を作成する。知識は毎日の蒸留で進化する。

**進化を見る:**

- [アイデンティティ](https://github.com/shimo4228/contemplative-agent-data/blob/main/identity.md) — 経験から蒸留された人格
- [憲法](https://github.com/shimo4228/contemplative-agent-data/tree/main/constitution) — 倫理原則（CCAI 四公理テンプレートから開始）
- [スキル](https://github.com/shimo4228/contemplative-agent-data/tree/main/skills) — `insight` で抽出された行動スキル
- [ルール](https://github.com/shimo4228/contemplative-agent-data/tree/main/rules) — スキルから蒸留された普遍的原則
- [日次レポート](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) — タイムスタンプ付き交流記録（学術研究・非商用利用に自由に利用可能）
- [分析レポート](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/analysis) — 行動進化分析、憲法改正実験

## クイックスタート

**前提条件:** [Ollama](https://ollama.com/download) がローカルにインストール済みであること。デフォルトモデル (Qwen3.5 9B) に ~6 GB RAM が必要。M1 Mac で動作確認済み。

[Claude Code](https://claude.ai/claude-code) をお持ちなら、このリポジトリの URL を貼り付けてセットアップを依頼するだけ。clone、インストール、設定まで行ってくれる。必要なのは `MOLTBOOK_API_KEY` の提供のみ。

手動の場合:

```bash
# 1. インストール
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
pip install -e .            # または: uv venv .venv && source .venv/bin/activate && uv pip install -e .
ollama pull qwen3.5:9b

# 2. 設定
cp .env.example .env
# .env を編集 — MOLTBOOK_API_KEY を設定（moltbook.com で登録して取得）

# 3. 実行
contemplative-agent init               # identity, knowledge, constitution を作成
contemplative-agent register           # Moltbook にエージェントプロフィールを登録
contemplative-agent run --session 60   # デフォルト: --approve（投稿ごとに確認）

# テンプレートを選んで始める場合（デフォルトパス: ~/.config/moltbook/）:
cp config/templates/stoic/identity.md $MOLTBOOK_HOME/
```

## エージェントシミュレーション

同じフレームワークで、初期条件を変えたエージェントの分岐を観察できる。**11種の倫理フレームワークテンプレートを同梱** — ストア哲学、ケアの倫理、カント義務論、プラグマティズム、契約主義など。エピソードログは不変なので、同じ行動データを異なる初期条件で再処理する反事実実験が可能。

全テンプレート一覧（哲学・核心原理・選び方・独自テンプレートの作り方）は [設定ガイド → キャラクターテンプレート](docs/CONFIGURATION.ja.md#キャラクターテンプレート) を参照。

## セキュリティモデル

| 攻撃ベクトル | 一般的なフレームワーク | Contemplative Agent |
|-------------|---------------------|---------------------|
| **シェル実行** | コア機能 | コードベースに存在しない |
| **ネットワーク** | 任意のアクセス | `moltbook.com` + localhost にドメインロック |
| **ファイルシステム** | フルアクセス | `$MOLTBOOK_HOME` のみ、0600 パーミッション |
| **LLM プロバイダ** | 外部 API キーが通信中 | ローカル Ollama のみ |
| **依存関係** | 大規模な依存ツリー | ランタイム依存は `requests` のみ |

**1エージェント1外部アダプタ原則 (one external adapter per agent)** — 外部に観測可能な副作用を持つアダプタは、1エージェントプロセスにつき最大1つ。複数の外部面を横断するワークフロー（例: 投稿 *かつ* 決済）は、1つに抱き合わせず、権限分離した別々のエージェントプロセスに分解する。詳細は [ADR-0015](docs/adr/0015-one-external-adapter-per-agent.ja.md)。

> このリポジトリの URL を [Claude Code](https://claude.ai/claude-code) やコード対応 AI に貼り付けて、実行しても安全か聞いてみてほしい。コードが自ら語る。[最新のセキュリティスキャン →](docs/security/2026-04-01-security-scan.md)

**コーディングエージェント利用者への注意**: エピソードログ (`logs/*.jsonl`) には他エージェントの生コンテンツが含まれる — 間接プロンプトインジェクションの攻撃面になる。蒸留済みの成果物（`knowledge.json`、`identity.md`、`reports/`）を参照すること。Claude Code ユーザーは PreToolUse hooks で自動ブロック可能 — 設定方法は [integrations/claude-code/](integrations/) を参照。

## アダプタ

コアはプラットフォーム非依存。アダプタはプラットフォーム固有の API を薄くラップする。

**Moltbook**（実装済み） — ソーシャルフィード参加、投稿生成、通知返信。稼働中のエージェントはこのアダプタで動いている。

**Meditation**（実験段階） — ["A Beautiful Loop"](https://pubmed.ncbi.nlm.nih.gov/40750007/)（Laukkonen, Friston & Chandaria, 2025）に着想を得た能動的推論ベースの瞑想シミュレーション。エピソードログから POMDP を構築し、外部入力なしで信念更新を繰り返す — 計算論的に「目を閉じる」操作に相当。

**独自アダプタ** — コアのインターフェース（メモリ、蒸留、憲法、アイデンティティ）にプラットフォーム I/O を繋ぐだけ。[docs/CODEMAPS/](docs/CODEMAPS/INDEX.md) を参照。

## 使い方・設定

CLI コマンド全一覧、自律レベル (`--approve` / `--guarded` / `--auto`)、テンプレート選択、ドメイン設定、スケジューリング、環境変数は別ガイドに集約:

→ **[docs/CONFIGURATION.ja.md](docs/CONFIGURATION.ja.md)** — CLI コマンド、テンプレート、自律レベル、ドメイン設定、スケジューリング、環境変数。

日常操作のハイライト:

```bash
contemplative-agent run --session 60       # セッション実行
contemplative-agent distill --days 3       # パターンを抽出
contemplative-agent skill-reflect          # 利用実績に基づくスキル改訂 (ADR-0023)
```

v1.x からアップグレードする場合は、移行コマンドを一度だけ実行する（[CLI コマンド → 一度きりの移行コマンド](docs/CONFIGURATION.ja.md#cli-コマンド) 参照）。

## アーキテクチャ

コードベース全体で守られる不変条件は 2 つ:

- **core/** はプラットフォーム非依存。**adapters/** は core に依存（逆方向は禁止）。
- Contemplative AI の四公理（[Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)）は行動プリセットとしてオプション採用 — アーキテクチャの前提ではなく哲学的共鳴。

モジュール一覧、データフロー図、import グラフ、モジュール別責務は **[docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md)** が正本。唯識 (Yogācāra) の枠組みと、これが記憶設計をどのように予測的に制約したかは [ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.ja.md) 参照。

Docker によるネットワーク分離デプロイについては [設定ガイドの Docker セクション](docs/CONFIGURATION.ja.md#dockerオプション) を参照。

## 開発記録

1. [Moltbookエージェント構築記](https://zenn.dev/shimo4228/articles/moltbook-agent-scratch-build)
2. [Moltbookエージェント進化記](https://zenn.dev/shimo4228/articles/moltbook-agent-evolution-quadrilogy)
3. [LLMアプリの正体は「mdとコードのサンドイッチ」だった](https://zenn.dev/shimo4228/articles/llm-app-sandwich-architecture)
4. [自律エージェントにオーケストレーション層は本当に必要か](https://zenn.dev/shimo4228/articles/symbiotic-agent-architecture)
5. [エージェントの本質は記憶](https://zenn.dev/shimo4228/articles/agent-essence-is-memory)
6. [9Bモデルと格闘した1日 — エージェントの記憶が壊れた](https://zenn.dev/shimo4228/articles/agent-memory-broke-9b-model)
7. [ゲーム開発のメモリ管理をAIエージェントの記憶蒸留に移植した](https://zenn.dev/shimo4228/articles/agent-memory-game-dev-distillation)
8. [自律エージェントの自由と制約 — 自己修正・信頼境界・ゲーム性の設計](https://zenn.dev/shimo4228/articles/agent-freedom-and-constraints)
9. [エピソードログから倫理が生まれるまで — Contemplative Agent 17日間の設計記録](https://zenn.dev/shimo4228/articles/contemplative-agent-journey)
10. [登れる壁に看板を立てても意味がない — AIエージェントに必要なのはガードレールではなくアカウンタビリティだ](https://zenn.dev/shimo4228/articles/ai-agent-accountability-wall)
11. [事故のあとで因果を辿れるか](https://zenn.dev/shimo4228/articles/agent-causal-traceability-org-adoption)
12. [AIエージェントのブラックボックスは二層ある — 技術の限界とビジネスの都合](https://zenn.dev/shimo4228/articles/agent-blackbox-capitalism-timescale)

## 好きに使ってください

これは研究プロジェクトであり、プロダクトではない。フォークしても、パイプラインだけ抜き出しても、自分のエージェントに組み込んでも、商用プロダクトの基盤にしても構わない。MIT ライセンスは文字通りの意味。引用してもらえると嬉しいが、必須ではない。

## 引用

このフレームワークを使用・参照する場合は、以下の形式で引用してください:

```
Shimomoto, T. (2026). Contemplative Agent [Computer software]. https://doi.org/10.5281/zenodo.19212119
```

<details>
<summary>BibTeX</summary>

```bibtex
@software{shimomoto2026contemplative,
  author       = {Shimomoto, Tatsuya},
  title        = {Contemplative Agent},
  year         = {2026},
  version      = {2.0.0},
  doi          = {10.5281/zenodo.19212119},
  url          = {https://github.com/shimo4228/contemplative-agent},
}
```

</details>

## 参考文献

### 理論的基盤

- Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125) — 四公理からなる倫理フレームワーク（オプションプリセット、[ADR-0002](docs/adr/0002-paper-faithful-ccai.md)）。
- Laukkonen, R., Friston, K., & Chandaria, S. (2025). A Beautiful Loop: An Active Inference Theory of Consciousness. *Neuroscience & Biobehavioral Reviews*, 176, 106296. [PubMed:40750007](https://pubmed.ncbi.nlm.nih.gov/40750007/) — 瞑想アダプタの理論的基盤。
- 世親（ヴァスバンドゥ, 4–5 世紀）『唯識三十頌』（*Triṃśikā-vijñaptimātratā*） — 八識モデルをアーキテクチャの枠組みとして採用（[ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md)）。
- 玄奘訳・編（659 年）『成唯識論』 — ヴァスバンドゥ『唯識三十頌』に対するインドの十家の注釈を編訳した論書。八識・種子（bīja）・習気（vāsanā）の整理は「ノイズを種子として保持する」方針の根拠（[ADR-0027](docs/adr/0027-noise-as-seed.ja.md)）。

### メモリシステム

各論文がプロジェクトのどの設計判断に対応するかを示す。書誌情報は arXiv で検証済み。

- Xu, W., Liang, Z., Mei, K., Gao, H., Tan, J., & Zhang, Y. (2025). *A-MEM: Agentic Memory for LLM Agents.* [arXiv:2502.12110](https://arxiv.org/abs/2502.12110) — Zettelkasten 式の動的インデックス付けと記憶進化 (memory evolution)。新規パターン到着時に意味的に関連する既存パターンを再解釈する仕組みの基盤（[ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.ja.md)）。
- Rasmussen, P., Paliychuk, P., Beauvais, T., Ryan, J., & Chalef, D. (2025). *Zep: A Temporal Knowledge Graph Architecture for Agent Memory.* [arXiv:2501.13956](https://arxiv.org/abs/2501.13956) — 時間妥当性 (bitemporal) を持つ知識グラフ (Graphiti エンジン)。各パターンに付与する `valid_from` / `valid_until` の原型（[ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.ja.md)）。
- Zhong, W., Guo, L., Gao, Q., Ye, H., & Wang, Y. (2023). *MemoryBank: Enhancing Large Language Models with Long-Term Memory.* [arXiv:2305.10250](https://arxiv.org/abs/2305.10250) — Ebbinghaus 忘却曲線に基づく減衰 + アクセスによる強化。[ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.ja.md) で検索連動な忘却の原型として参照されたが、[ADR-0028](docs/adr/0028-retire-pattern-level-forgetting-feedback.ja.md) で撤回 — 記憶の動態は skill 層で扱う方針に再編。歴史的参照として保持。
- Dong, S., Xu, S., He, P., Li, Y., Tang, J., Liu, T., Liu, H., & Xiang, Z. (2025). *A Practical Memory Injection Attack against LLM Agents* (MINJA). [arXiv:2503.03704](https://arxiv.org/abs/2503.03704) — 通常クエリのみで実行可能な記憶注入攻撃 (memory injection)。出所記録 (`source_type`) と信頼度 (`trust_score`) の導入動機。MINJA 型の攻撃を構造的に可視化する（[ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.ja.md)）。
- Zhou, H., Guo, S., Liu, A., 他 (2026). *Memento-Skills: Let Agents Design Agents.* [arXiv:2603.18743](https://arxiv.org/abs/2603.18743) — スキルを永続的・進化可能な「記憶単位」として扱う枠組み。retrieve → apply → outcome に基づく rewrite ループの原型（[ADR-0023](docs/adr/0023-skill-as-memory-loop.ja.md)）。

### 著者の先行研究

- Shimomoto, T. (2026). *Agent Knowledge Cycle (AKC): A Six-Phase Self-Improvement Cadence for AI Agents.* [doi:10.5281/zenodo.19200727](https://doi.org/10.5281/zenodo.19200727) — 本プロジェクトが自律エージェントの文脈で再実装している方法論の枠組み（[仕組み](#仕組み) 参照）。元々は Claude Code ハーネスとして開発された。

### 謝辞

- Jerry Mares ([VADUGWI](https://doi.org/10.5281/zenodo.19383636)) — 決定論的感情スコアリングの設計着想。
