# Changelog

All notable releases are recorded here. See [docs/adr/](docs/adr/) for the reasoning behind each decision and [docs/evidence/](docs/evidence/) for the measurement artifacts that backed them.

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

---

## Unreleased

Tracking post-v2.0.0 follow-ups (ADR-0022 through ADR-0030). Details live in ADRs.

---

## v2.0.0 — Yogācāra Memory Architecture (2026-04-16)

This release overhauls the Layer 2 knowledge store. The old discrete-category
classification is retired; patterns are now stored as embedding coordinates,
carry provenance / bitemporal validity / retrieval-aware forgetting, and
co-evolve with their neighbors. The Yogācāra eight-consciousness model is
adopted as the explicit architectural frame ([ADR-0017](../docs/adr/0017-yogacara-eight-consciousness-frame.md)):
episode log ↔ sense-streams, knowledge ↔ ālaya (seed storehouse), identity
↔ manas (self-grasping view).

## Breaking Changes

- **`knowledge.json` schema is incompatible with v1.x.** Run these migrations
  once, in order, before starting the agent under v2.0.0:

  ```bash
  contemplative-agent embed-backfill         # Compute embeddings for existing patterns + episodes
  contemplative-agent migrate-patterns       # Apply ADR-0021 pattern schema (provenance, bitemporal, strength, feedback)
  contemplative-agent migrate-categories     # Drop retired category / subcategory fields (ADR-0026)
  contemplative-agent migrate-identity       # Convert identity.md to block-addressed form (ADR-0024)
  ```

  Each migration writes a timestamped `.bak` file next to the original before
  touching it. Keep these backups at least until the new store has been
  exercised end-to-end.

- Discrete `category` / `subcategory` fields are no longer consulted anywhere
  in the codebase. Any external tooling that reads them must switch to
  querying through views.

## Major Additions (accepted)

- **ADR-0017: Yogācāra eight-consciousness frame** — names the architectural
  model that has been implicit since the earliest design sessions. No code
  change; the interpretation layer shifts so future contributors have a
  principled way to reason about what each memory layer preserves and
  transforms.
- **ADR-0019: Embedding + views replace discrete categories** — classification
  is a query, not state. Views are editable semantic seeds that can be added,
  tuned, or removed without migrating data. Hybrid retrieval combines cosine
  similarity with BM25 for exact-keyword queries.

## Major Additions (proposed)

The following are landed behind flags / gated on migration but are still
marked *proposed* in their ADRs; behavior may change before the next stable
release. Episode logs are not affected.

- **ADR-0020: Pivot snapshots** — bundles manifest + views + constitution +
  centroid embeddings so any distillation run can be replayed bit-for-bit.
- **ADR-0021: Pattern schema extension** — each pattern now carries
  provenance (`source_type`, `trust_score`), bitemporal validity
  (`valid_from`, `valid_until`), retrieval-aware strength (Ebbinghaus-style
  decay reinforced by access), and feedback counters. MINJA-class memory
  injection attacks become structurally visible rather than invisible.
- **ADR-0022: Memory evolution + hybrid retrieval** — when a new pattern
  lands near an older one, the LLM re-interprets the older pattern's
  `distilled` text; the old row is soft-invalidated and a revised row
  appended.
- **ADR-0023: Skill-as-memory loop** — skills carry frontmatter with success
  / failure counters; `skill-reflect` revises skills based on outcome logged
  in `skill-usage-*.jsonl`.
- **ADR-0024 / ADR-0025: Identity block separation + history log** —
  `identity.md` is parsed as frontmatter-addressed named blocks
  (`persona_core`, `current_goals`, …); each block update is recorded in
  `identity_history.jsonl` with its own hash.
- **ADR-0026: Retire discrete categories (Phase 3 of ADR-0019)** — the
  `category` field is removed from the pattern schema.
- **ADR-0027: Noise as seed** — Phase 1 landed. Episodes gated as "noise"
  are written to JSONL rather than discarded, preserving bīja (種子) for
  possible later actualisation under different conditions.

## New CLI

- `embed-backfill`, `migrate-patterns`, `migrate-categories`,
  `migrate-identity` — one-time migrations.
- `skill-reflect` — revise skills from usage outcomes (ADR-0023).
- `inspect-identity-history`, `prune-skill-usage` — introspection and
  maintenance.

## Security

- The "one external adapter per agent" principle ([ADR-0015](../docs/adr/0015-one-external-adapter-per-agent.md))
  is now exercised by a dedicated 50-test coverage pass against silent
  failure paths in ADR-0020..0025.
- Provenance + trust_score give MINJA-class attacks a structural signature
  rather than relying on LLM vigilance.
- Test suite grows from 942 to 1170 tests.

## References Added to README

Three-part References section:

- *Theoretical Foundation* — Laukkonen et al. (2025) Contemplative AI,
  Laukkonen, Friston & Chandaria (2025) *A Beautiful Loop: An Active
  Inference Theory of Consciousness*, Vasubandhu's *Triṃśikā-vijñaptimātratā*
  (唯識三十頌), Xuanzang's *Cheng Weishi Lun* (成唯識論).
- *Memory Systems* — A-MEM (arXiv:2502.12110), Zep / Graphiti (arXiv:2501.13956),
  MemoryBank (arXiv:2305.10250), MINJA (arXiv:2503.03704),
  Memento-Skills (arXiv:2603.18743).
- *Related Work* — Mares (2026) VADUGWI, Shilov (2025) CIMP.

## Commits

71 commits since v1.3.1 (2026-04-07). See the full log with
`git log v1.3.1..v2.0.0 --oneline`.
