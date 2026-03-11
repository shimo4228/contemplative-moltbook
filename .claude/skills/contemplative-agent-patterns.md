---
name: contemplative-agent-patterns
description: Autonomous LLM agent の設計で学んだ実装上の落とし穴と手順ガイド
version: 1.1.0
origin: skill-create
analyzed_commits: 24
---

# Autonomous LLM Agent — Gotchas & How-To

MEMORY.md にある設計判断の「何を」ではなく、実装時の「どうやって」と「落とし穴」に特化。

## Gotcha 1: Core/Adapter 分離の順序

一括でやると全テストの patch パスが壊れてデバッグ不能になる。

**正しい順序**:
1. ディレクトリ分割 + re-export shim → テスト全通過を確認
2. テストの import パスを canonical パスに更新 → shim 除去 → テスト全通過
3. パッケージリネーム（必要なら）→ テスト全通過

**やってはいけないこと**: 分割とリネームを同一コミットでやる

---

## Gotcha 2: `str.replace()` でサニタイズしてはいけない

`str.replace()` は大文字小文字を区別するため、`"FORBIDDEN"` → 除去しても `"Forbidden"` が残る。

```python
# BAD
text = text.replace("forbidden_word", "")

# GOOD
text = re.sub(r"forbidden_word", "", text, flags=re.IGNORECASE)
```

---

## Gotcha 3: `requests.Session` の Authorization 漏洩

`Session` に `Authorization` ヘッダーを設定すると、リダイレクト先にもそのヘッダーが送られる。

```python
# BAD — リダイレクト先にトークンが漏れる
session.headers["Authorization"] = f"Bearer {token}"
resp = session.get(url)

# GOOD
resp = session.get(url, allow_redirects=False)
```

---

## Gotcha 4: Composition Root 以外で adapter と core を混ぜない

`cli.py` (composition root) だけが `core/` と `adapters/` の両方を import できる。
他のモジュールでこれをやると依存方向が壊れ、別アダプタ対応時に破綻する。

テストでの patch パスは常に adapter 側の完全パスを使う:
```python
@patch("contemplative_agent.adapters.moltbook.agent.MoltbookClient")
```

---

## How-To: 設定の外部化で prompts と rules を分ける

ドメイン切替時に「何を差し替えるか」が不明確になる問題を防ぐ分離基準:

| ディレクトリ | 役割 | ドメイン切替時 |
|-------------|------|--------------|
| `config/prompts/` | LLM への「タスク指示」 | 変わらない |
| `config/rules/` | エージェントの「行動原則」 | `--rules-dir` で差し替え |

---

## How-To: パラメータ化のパターン

テストで `tmp_path` を使えるようにする定型パターン:

```python
class MyModule:
    def __init__(self, state_path: Optional[Path] = None):
        # None → in-memory のみ（テスト用）
        # Path → ファイル永続化（本番用）
        self._path = state_path
```

cli.py で本番値を注入、テストでは `None` か `tmp_path` を渡す。
