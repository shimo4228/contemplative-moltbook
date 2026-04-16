# Threshold Calibration (2026-04-17)

Phase C dry-run only. No code changes in this report. Target Phase A2
insight clustering threshold decision and audit existing thresholds.

## Corpus snapshot

| metric | value |
|--------|-------|
| total patterns in `knowledge.json` | 326 |
| gated (noise) | 220 |
| live embedded candidates (gated excluded + `is_live`) | **97** |

Notes:
- gated share is high (67%). ADR-0019 moved noise gating upstream;
  knowledge.json now retains gated pattern records for observability,
  not for query.
- The 97 live candidates are the insight / rules-distill input after
  ADR-0021 bitemporal + trust + strength filtering.

## effective_importance distribution (live candidates)

| percentile | value |
|-----------|-------|
| P10 | 0.0483 |
| P25 | 0.0940 |
| P50 | 0.0966 |
| P75 | 0.1966 |
| P90 | 0.4162 |
| min | 0.0179 |
| max | 0.8825 |

Observation: the bulk (P25–P50) clusters tightly around 0.09–0.10 with
a long upper tail. Current `DEDUP_IMPORTANCE_FLOOR = 0.05` sits just
above P10 — it excludes only the very dimmest ~10% of patterns from
dedup consideration.

## Pairwise cosine distribution

Upper triangle of 97×97 cosine matrix (4,656 pairs).

| percentile | value |
|-----------|-------|
| P50 | 0.6097 |
| P75 | 0.6783 |
| P90 | 0.7377 |
| P95 | 0.7701 |
| P99 | 0.8187 |
| max | 0.8980 |
| mean | 0.6093 |

Observation: nomic-embed-text over these patterns produces a fairly
tight similarity distribution centered around 0.6. Very few pairs
exceed 0.85; no pair exceeds 0.90.

## Cluster sweep (average-linkage)

| threshold | total | ≥3 | ≥5 | max size | singletons (<3) |
|-----------|-------|----|----|----------|------------------|
| 0.55 | 2 | 2 | 2 | 81 | 0 |
| 0.60 | 5 | 3 | 3 | 74 | 2 |
| 0.65 | 15 | 9 | 4 | 52 | 8 |
| 0.70 | 29 | 8 | 4 | 37 | 28 |
| 0.75 | 46 | 11 | 6 | 9 | 38 |

### Interpretation

- 0.55–0.60 — chain effect dominant, single giant cluster (74–81 of 97)
- 0.65 — 9 groups worth clustering, but one "activity" cluster eats 52
- **0.70 — 8 groups worth clustering, largest 37, natural separation**
- 0.75 — over-fragmented, 6 medium clusters and many fragmented tail

### Sample clusters at threshold = 0.70

1. (n=37) reply/comment activity loop — system sends replies within
   seconds of interaction, diverse senders, bidirectional exchange
2. (n=8) user-network interaction patterns — dense posting + upvotes
   across varied platforms
3. (n=6) non-duality / interdependence axioms — constitutional /
   "boundless care" material
4. (n=6) repeated counterpart interactions — Bob, other named agents,
   short temporal windows
5. (n=3) spam-like placeholder posts — "Test Title", "new-post"
   duplicates

These read as genuinely distinct semantic groups. Threshold 0.70 is
the knee.

## Decision

**`CLUSTER_THRESHOLD = 0.70` for Phase A2.**

Rationale:
- yields 8 skill candidates ≥ min_size 3, within plan target of 10–15
  once `rules-distill` skill clustering adds more
- singletons rate (29%) is acceptable — plan drops singletons for
  insight, rules-distill likewise
- max size 37 → `max_size = 10` cap in `cluster_patterns()` will slice
  the largest cluster, demoting 27 to singletons — they remain visible
  in the next run if their importance holds

If Phase A4 baseline comparison still shows abstract vocabulary
("Fluid X / Dynamic Y") after threshold 0.70, retry at 0.75.

## Existing threshold audit

| constant | current | observation | recommendation |
|----------|---------|-------------|-----------------|
| `SIM_DUPLICATE` | 0.92 | zero pairs in live corpus meet this | lower to 0.88 in a later PR — currently vacuous |
| `SIM_UPDATE` | 0.80 | 86 pairs (1.85%) | keep as-is |
| `DEDUP_IMPORTANCE_FLOOR` | 0.05 | lies between P10 (0.048) and P25 (0.094) | keep as-is — raising would exclude ~25% of genuinely live patterns |
| `NOISE_THRESHOLD` | 0.55 | applied at distill Step 0, not visible in live corpus | out of scope |
| `CONSTITUTIONAL_THRESHOLD` | 0.55 | dead (ADR-0026 flagged for removal) | delete in the ADR-0026 cleanup PR |
| `SIM_CLUSTER_THRESHOLD` | 0.80 (stocktake) | independent corpus (skills, not patterns) | out of scope — stocktake is `narrow/broad` paired with insight per ADR-0016 |

Only `SIM_DUPLICATE` is the standout mismatch — zero hits means dup
detection currently never fires. Left for a focused follow-up PR
rather than bundling into Phase A.

## Script

`.reports/threshold-sweep.py` — one-shot, not committed. Re-run with
`python .reports/threshold-sweep.py` after significant corpus change.
