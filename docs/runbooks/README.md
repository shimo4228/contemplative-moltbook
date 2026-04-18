# Runbooks

運用 know-how の durable 置き場。「どう動かすか」「事故ったらどう復旧するか」。

## コンテンツ

| Path | 種別 | 対象 |
|---|---|---|
| `adr-0019-migration.md` | Migration guide | ADR-0019 embedding + views 移行手順 |
| `rca/` | Post-mortem | 事故 / 想定外挙動の根本原因分析 |

## 配置ルール

- **Migration guide**: ADR と対応する運用手順。`<adr-slug>-migration.md` 形式
- **RCA**: `rca/YYYY-MM-DD-<slug>.md` 形式。再発予防が目的、ただの愚痴や状況記録ではない
- **Docker / セットアップ guide**: 既存の `docs/CONFIGURATION.md` または README の該当節を優先

## 書くべきでないもの

- 決定そのもの → `docs/adr/`
- アーキテクチャ俯瞰 → `docs/CODEMAPS/`
- 測定・実験 → `docs/evidence/`
- 途中経過メモ → `.notes/` (gitignored)
