---
name: agent-run
description: contemplative-agent の起動コマンドリファレンス。フラグ順序の間違いを防ぐ
origin: original
---

# Agent Run — 起動リファレンス

## フラグ順序 (重要)

`--auto` / `--guarded` / `--approve` は **グローバルフラグ**。`run` の **前** に置く。

```bash
# 正しい
contemplative-agent --auto run --session 120

# 間違い (unrecognized arguments エラー)
contemplative-agent run --session 120 --auto
```

## 起動パターン

```bash
# 自律モード (2時間)
contemplative-agent --auto run --session 120

# 自律モード (デフォルト60分)
contemplative-agent --auto run

# ガードモード (フィルタ通過時のみ自動投稿)
contemplative-agent --guarded run --session 120

# 承認モード (毎回確認、デフォルト)
contemplative-agent run --session 120

# デバッグ出力付き
contemplative-agent -v --auto run --session 120
```

## オプションフラグ (グローバル、run の前に置く)

| フラグ | 位置 | 説明 |
|--------|------|------|
| `--auto` | グローバル | 完全自律 |
| `--guarded` | グローバル | フィルタ通過時のみ自動 |
| `--approve` | グローバル | 毎回確認 (デフォルト) |
| `-v` | グローバル | デバッグログ |
| `--no-axioms` | グローバル | CCAI clauses 無効 (A/B テスト用) |
| `--domain-config PATH` | グローバル | domain.json 切替 |
| `--rules-dir PATH` | グローバル | ルールディレクトリ切替 |
| `--session N` | `run` サブコマンド | セッション時間 (分、デフォルト60) |
