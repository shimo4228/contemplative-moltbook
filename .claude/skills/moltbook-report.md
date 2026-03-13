---
name: moltbook-report
description: Moltbook エージェントのセッションログからコメント・投稿レポート（日本語訳付き）を生成し Obsidian vault に保存する
origin: original
user_invocable: true
---

# Moltbook Comment Report Generator

## Trigger

ユーザーが `/moltbook-report` を実行した時、または「レポートを作って」「コメント一覧を出して」等のリクエスト時。

## 手順

### 1. ログファイルの特定

本日のセッションログを探す。以下の場所を確認:

```
/private/tmp/claude-501/-Users-shimomoto-tatsuya-MyAI-Lab-contemplative-moltbook/*/tasks/*.output
```

各 `.output` ファイルから `contemplative_agent` のログを含むものを特定する。
複数セッションがある場合は全て対象にする。

### 2. コメント・投稿の抽出

ログから以下のパターンを抽出:

- `>> Comment on {post_id_prefix}:` — コメント全文（次のタイムスタンプ行まで）
- `>> New post [{title}]` — 自己投稿全文（次のタイムスタンプ行まで）
- `Post {post_id} relevance {score} passed threshold {threshold}` — コメント直前の relevance スコア

### 3. レポート生成

以下のフォーマットで Markdown ファイルを生成する:

```markdown
# Moltbook Comment Report — {YYYY-MM-DD}

## Session {N} ({HH:MM}-{HH:MM})

### Comments

#### {N}. [{HH:MM}] Post ID: {post_id_prefix} (relevance: {score})

**Original:**
> コメント全文

**日本語訳:**
> 自然な日本語の意訳

---

### Self Posts

#### {N}. [{HH:MM}] {タイトル}

**Original:**
> 投稿全文

**日本語訳:**
> 自然な日本語の意訳

---

## Summary
- コメント総数: X
- 自己投稿数: X
- relevance スコア範囲: 0.XX - 0.XX
```

### 4. 保存先

Obsidian vault 内の Moltbook フォルダに保存:

```
~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/Moltbook/comment-report-{YYYY-MM-DD}.md
```

同日に複数回実行した場合はファイルを上書きする（最新の全セッション分を含む）。

### 5. 翻訳ガイドライン

- 直訳より意訳を優先
- 技術用語はそのまま残す（alignment, agent, benchmark 等）
- 長いコメントも省略せず全文訳す
