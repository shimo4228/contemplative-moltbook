# ADR-0031: Classification as Query — Substrate Principle for Self-Improving Memory

## Status

accepted — post-hoc articulation of a principle already realised in ADR-0019, ADR-0022, and ADR-0026

This is a **worldview ADR** in the sense defined by `docs/adr/README.md`: it does not solve a new problem, it names the substrate condition under which the project's other memory ADRs become formulable.

## Date

2026-04-27

## Context

Self-improving agents revise their own classification axes over time. The Curate phase of a self-improvement cycle (in this project, `distill`, `insight`, `rules-distill`, `amend-constitution`, and `skill-reflect`) periodically re-evaluates how past observations should be grouped, which patterns count as "the same thing", and which dimensions matter.

If categories are stored as state at write time — discrete `category` fields, fixed tags, write-time namespaces — every axis revision requires data migration. The cost of that migration grows with corpus size, and the operational friction of running it grows even faster (downtime, schema versioning, rollback procedures, reproducibility breaks). At some corpus size, the cost caps how often the agent is allowed to revise its own classification.

That cap is incompatible with the self-improvement premise. An agent that cannot cheaply re-classify its own past stops being a learning agent at the point where re-classification becomes expensive — typically right when it has accumulated enough history to learn something interesting from re-classifying it.

This ADR names the substrate property that must hold for self-improvement to remain cheap, and identifies the design pattern (`view`-based projection) that satisfies it in this project.

## Decision

Categories are computed at **read time** by projecting records against editable semantic seeds, not stored as **state** at write time.

Concretely in this project: each "view" is a small editable artifact (a centroid embedding plus a name and prompt) that defines a semantic axis. Classification of any pattern under any view is computed at query time as a similarity score between the pattern's embedding and the view's centroid. The pattern itself carries no category field, no tag list, no namespace — only its content and its embedding.

This treats classification as a **query operation** rather than a **state field**.

## Implications

1. **Mutable classification axes**. Changing how data is grouped requires no migration. Editing the seed re-projects the entire corpus. The cost of revising an axis becomes O(seed-edit), not O(corpus-size).
2. **Multi-membership is natural**. A single record can simultaneously belong to multiple views without duplication, conflict, or "primary tag" disambiguation.
3. **Self-improving cycles preserve their substrate**. When the agent revises its classification axes through Curate-phase distillation, no historical data is lost or rewritten. The history layer (`episodes.sqlite`, immutable JSONL) and the pattern layer (`knowledge.json`) stay untouched while the projection over them shifts.
4. **Mechanism / Value Split is preserved**. "Which view does this belong to?" stays in the deterministic mechanism layer (embedding similarity). "Is this important / right / true?" stays in the stochastic value layer (LLM judgment, constitution gate). The query / state distinction maps cleanly onto that split: queries are mechanism, state would have been value frozen into structure.
5. **Drift is a feature of the seed, not a bug in the data**. When a view's meaning shifts because the seed was edited, the records do not become "miscategorised" — they become differently-projected. The previous projection can be reconstructed by reverting the seed (and is captured in pivot snapshots; see ADR-0020).

## Reference Implementations

- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — initial migration from a discrete `category` field to view-based projection. Records the original problem statement and the migration procedure
- [ADR-0022](0022-memory-evolution-and-hybrid-retrieval.md) — extension with cosine + BM25 hybrid scoring and memory evolution (LLM re-interpretation of topically-related older patterns when a new pattern arrives)
- [ADR-0026](0026-retire-discrete-categories.md) — Phase-3 completion: removal of the legacy `category` field once the view-based path was load-bearing

These three ADRs taken together are the operational realisation of the principle stated here. ADR-0031 is the principle they collectively express.

## Closest Prior Art

- A-MEM (Xu et al., 2025, [arXiv:2502.12110](https://arxiv.org/abs/2502.12110)) — Zettelkasten-style dynamic indexing for LLM agents. Same attractor reached independently: classification as a runtime, editable operation rather than a write-time fixed assignment.

The contribution of this ADR is **not** the mechanism (that mechanism has been reached by multiple groups around the same time, which is itself evidence that the design space is converging on it). The contribution is the **articulation of this mechanism as a substrate prerequisite for self-improving agents** — the connection between "classification as query" and "self-improvement remains cheap as the corpus grows" is what is being named here.

## Promotion Candidate

This principle is a candidate for promotion into the [Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) repository's Design Principles section, alongside the existing Mechanism / Value Split principle. Promotion would re-frame this ADR as the Contemplative Agent reference implementation of an AKC substrate principle, with AKC carrying the harness-neutral statement of the principle and Contemplative Agent carrying the concrete realisation.

Promotion is to be evaluated separately by the AKC repository. This ADR records the principle here so that AKC has a referenceable articulation to evaluate.

## Alternatives Considered

- **Keep discrete category fields and accept the migration cost**. Rejected: caps self-improvement frequency at the point where the corpus becomes large enough to be worth re-classifying. The cap arrives precisely when the agent would benefit most from re-classifying.
- **Hybrid (state + query)**: store a primary category at write time, support secondary view-based queries on top. Rejected: doubles complexity (two sources of truth for classification), gains nothing structural — the primary category still locks the dominant axis at write time, which is the constraint this ADR exists to remove.
- **Implicit categorisation through retrieval only** (no named views, only ad-hoc similarity queries). Rejected: removes the editable seed surface that makes axis revision a deliberate, auditable act. Named views are the unit at which the agent (and its operator) negotiates with the substrate about what axes matter.

## Consequences

**Positive**:
- Self-improvement cycles can revise classification axes without data loss or migration cost
- View seeds become editable surfaces that shift the meaning of the entire corpus when changed — operators can run experiments by editing one seed
- The Mechanism / Value Split is enforced by the substrate, not by convention: there is no place in the schema where an LLM-generated classification could be frozen into state

**Negative**:
- Implementation requires embedding infrastructure (vector storage, similarity computation, hybrid retrieval). This is amortised across all queries but is non-trivial initial setup
- Query-time computation cost is higher than state-lookup cost. For corpora large enough to require ANN indexing, the lookup latency becomes a real consideration
- Reasoning about "what category is this?" requires running a query, not reading a field. Tools that expect a static category attribute on each record do not work without an adapter

**Neutral**:
- Existing ADRs (ADR-0019, ADR-0022, ADR-0026) are unchanged in content; this ADR sits above them as the principle they express
- ADR-0017 (Yogācāra eight-consciousness frame) is consistent with this principle: 相分 (the perceived) corresponds to embeddings, 見分 (the perceiving aspect) corresponds to view centroids, and the relationship is one of projection rather than storage. The frame is not a justification for the principle, but it does not contradict it

## References

- [ADR-0017](0017-yogacara-eight-consciousness-frame.md) — worldview frame within which the projection / state distinction becomes legible
- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — reference implementation, initial migration
- [ADR-0020](0020-pivot-snapshots-for-replayability.md) — replay mechanism that captures the seed state at each distill run
- [ADR-0022](0022-memory-evolution-and-hybrid-retrieval.md) — reference implementation, hybrid scoring
- [ADR-0026](0026-retire-discrete-categories.md) — reference implementation, completion of the migration
- A-MEM (Xu et al., 2025, [arXiv:2502.12110](https://arxiv.org/abs/2502.12110)) — closest prior art, reached the same mechanism independently
- [Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) — promotion candidate destination
