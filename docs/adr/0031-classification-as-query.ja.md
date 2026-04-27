# ADR-0031: Classification as Query — 自己改善メモリの substrate 原則

## Status

accepted — ADR-0019、ADR-0022、ADR-0026 に既に実現されている原則の post-hoc articulation

`docs/adr/README.md` の定義による **worldview ADR**: 新しい問題を解決するのではなく、本プロジェクトの他のメモリ ADR が定式化される前提条件としての substrate 条件を名指す。

## Date

2026-04-27

## Context

自己改善するエージェントは時間とともに自身の分類軸を改訂する。自己改善サイクルの Curate フェーズ (本プロジェクトでは `distill`、`insight`、`rules-distill`、`amend-constitution`、`skill-reflect`) が、過去の観察をどう束ねるべきか、どのパターンを「同じもの」とみなすか、どの次元が重要かを定期的に再評価する。

カテゴリが書き込み時に state として保存されている場合 — 離散的な `category` フィールド、固定タグ、書き込み時 namespace —、軸の改訂のたびにデータ migration が必要になる。migration コストはコーパスサイズに比例して増え、運用上の摩擦 (downtime、schema バージョニング、rollback 手順、再現性の途絶) はそれよりも速く増える。あるコーパスサイズに達した時点で、このコストがエージェントが自身の分類を改訂できる頻度の上限を決める。

この上限は自己改善という前提と両立しない。再分類が高くつく時点で再分類できなくなったエージェントは、まさに「興味深いことを学べるだけの履歴を蓄積した瞬間」に学習エージェントであることをやめる。

本 ADR は、自己改善が安価であり続けるために substrate が満たすべき性質を名指し、本プロジェクトでそれを満たす設計パターン (`view` ベース投影) を特定する。

## Decision

カテゴリは、書き込み時に **state** として保存されるのではなく、**読み出し時** に編集可能な意味的シードに対する投影として計算される。

具体的には: 各「view」は、意味的軸を定義する小さな編集可能 artifact (centroid embedding + 名前 + プロンプト)。任意のパターンの任意の view 下での分類は、クエリ時にパターンの embedding と view の centroid の類似度スコアとして計算される。パターン自体は category フィールドも、タグリストも、namespace も持たない — 内容と embedding だけを持つ。

これは分類を **state フィールド** ではなく **クエリ操作** として扱う。

## Implications

1. **可変な分類軸**。データの束ね方を変えるのに migration は不要。シードを編集するだけで全コーパスが再投影される。軸を改訂するコストは O(seed-edit) であり、O(corpus-size) ではない。
2. **多重所属が自然**。1 つのレコードが複数の view に同時に属することができる — 重複なし、衝突なし、「primary tag」の調停なし。
3. **自己改善サイクルが substrate を保存する**。エージェントが Curate フェーズの蒸留を通じて分類軸を改訂するとき、歴史データは失われも書き換えられもしない。history 層 (`episodes.sqlite`、不変 JSONL) と pattern 層 (`knowledge.json`) はそのまま、その上の投影だけがシフトする。
4. **Mechanism / Value Split が保存される**。「これはどの view に属するか?」は決定論的 mechanism 層 (embedding 類似度) に留まる。「これは重要か / 正しいか / 真か?」は確率的 value 層 (LLM 判断、constitution gate) に留まる。query / state の区別がこの分割に綺麗にマッピングされる: クエリは mechanism、state なら value が構造に凍結されたものになっていた。
5. **drift はシードの特性であってデータのバグではない**。view の意味がシード編集によってシフトしたとき、レコードは「誤分類」されたわけではない — 違って投影されただけ。前の投影はシードを revert すれば再構築できる (pivot snapshot に取り込まれる; ADR-0020 参照)。

## Reference Implementations

- [ADR-0019](0019-discrete-categories-to-embedding-views.ja.md) — 離散的 `category` フィールドから view ベース投影への initial migration。元の問題提起と migration 手順を記録
- [ADR-0022](0022-memory-evolution-and-hybrid-retrieval.ja.md) — cosine + BM25 ハイブリッドスコアと memory evolution (新パターン到着時に意味的に関連する古いパターンを LLM が再解釈) による拡張
- [ADR-0026](0026-retire-discrete-categories.ja.md) — Phase-3 完了: view ベースのパスが load-bearing になった後の legacy `category` フィールド削除

これら 3 つの ADR を合わせたものが、ここで述べられている原則の運用上の実現。ADR-0031 はそれらが集合的に表現する原則。

## Closest Prior Art

- A-MEM (Xu et al., 2025, [arXiv:2502.12110](https://arxiv.org/abs/2502.12110)) — LLM エージェント向け Zettelkasten 式動的インデックス。同じ attractor に独立に到達: 分類を書き込み時の固定割り当てではなく runtime の編集可能操作として扱う。

本 ADR の貢献は **メカニズムそのものではない** (メカニズムは複数の研究グループが同時期に独立に到達しており、それ自体が設計空間がそこに収束しつつある証拠)。貢献は **このメカニズムを自己改善エージェントの substrate prerequisite として articulate したこと** — 「分類はクエリ」と「コーパスが成長しても自己改善は安価であり続ける」の接続を名指したことが、ここで行われていること。

## Promotion Candidate

本原則は、[Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) リポジトリの Design Principles section に、既存の Mechanism / Value Split と並ぶ原則として昇格させる候補。昇格すれば本 ADR は AKC substrate principle の contemplative-moltbook 参考実装として再フレーミングされる — AKC が原則の harness-neutral な記述を担い、contemplative-moltbook が具体実現を担う構造。

昇格の判断は AKC リポジトリ側で別途行う。本 ADR は AKC が評価できる articulation をここに記録する。

## Alternatives Considered

- **離散的 category フィールドを維持し migration コストを受け入れる**。却下: 再分類するに値するほどコーパスが大きくなった瞬間に自己改善頻度の上限が来る。エージェントが再分類から最も恩恵を受けるはずのタイミングで上限に当たる。
- **ハイブリッド (state + query)**: 書き込み時に primary category を保存し、その上に secondary view ベースクエリをサポート。却下: 複雑性が倍 (分類の真実が 2 つ)、構造的な利得はない — primary category が依然として書き込み時に支配的な軸を固定し、それこそ本 ADR が排除しようとしている制約。
- **暗黙的分類 (named view なし、ad-hoc 類似度クエリのみ)**。却下: 軸の改訂を意図的かつ監査可能な行為にする編集可能シードを失う。named view は、エージェント (とその operator) が「どの軸が重要か」について substrate と交渉する単位。

## Consequences

**Positive**:
- 自己改善サイクルが分類軸を改訂しても、データロスや migration コストは発生しない
- view シードが、編集することで全コーパスの意味をシフトさせる surface になる — operator は 1 つのシードを編集することで実験を走らせられる
- Mechanism / Value Split が convention ではなく substrate によって強制される: スキーマ上に LLM 生成の分類が state として凍結される場所が存在しない

**Negative**:
- embedding インフラ (ベクタストレージ、類似度計算、ハイブリッド検索) が必要。クエリ全体に償却されるが、初期セットアップは非自明
- クエリ時計算コストが state lookup より高い。ANN インデックスが必要なほどコーパスが大きくなれば、lookup レイテンシが現実的な考慮事項になる
- 「これはどのカテゴリ?」を考えるにはクエリを実行する必要がある — フィールドを読むだけでは済まない。各レコードに静的な category 属性があることを期待するツールは、アダプタなしでは動かない

**Neutral**:
- 既存 ADR (ADR-0019、ADR-0022、ADR-0026) は内容に変更なし。本 ADR はそれらの上に、それらが表現する原則として位置する
- ADR-0017 (唯識八識フレーム) と本原則は整合: 相分 (perceived) が embedding に、見分 (perceiving aspect) が view centroid に対応し、関係は保存ではなく投影。フレームは原則の根拠ではないが、矛盾もしない

## References

- [ADR-0017](0017-yogacara-eight-consciousness-frame.ja.md) — 投影 / state の区別が legible になる worldview フレーム
- [ADR-0019](0019-discrete-categories-to-embedding-views.ja.md) — 参考実装、initial migration
- [ADR-0020](0020-pivot-snapshots-for-replayability.ja.md) — 各蒸留実行時のシード状態を捕捉する replay 機構
- [ADR-0022](0022-memory-evolution-and-hybrid-retrieval.ja.md) — 参考実装、ハイブリッドスコア
- [ADR-0026](0026-retire-discrete-categories.ja.md) — 参考実装、migration 完了
- A-MEM (Xu et al., 2025, [arXiv:2502.12110](https://arxiv.org/abs/2502.12110)) — closest prior art、独立に同じメカニズムに到達
- [Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) — promotion candidate destination
