# Cluster Experiment — Baseline vs New Insight (2026-04-17)

Phase A4 of the ADR-0019-aftermath pipeline cleanup. Compare the
insight run from the view-per-batch implementation (baseline,
2026-04-15 / 2026-04-16 runs, 6 skills) against the global-cluster
implementation just shipped (new, 2026-04-17 run, 8 skills).

## Run timings

- **Baseline** (pre-cluster): 5 batches × ~3–4 min = ~18 min total
- **New** (cluster): 8 batches × ~3 min = **~20 min total** (07:21 → 07:42)

Call-count increase +60% in line with cluster count increase. Per-call
cost unchanged (both use ~10-pattern prompt + num_predict=1500).

## Skill count

| | baseline | new | target |
|-|----------|-----|--------|
| count | 6 | 8 | 10–15 |

Below the 10–15 target but structurally consistent with the Phase C
sweep prediction (8 clusters ≥ size 3 at threshold 0.70). The target
assumed rules-distill would add skills to the count, which is
separately measured and not run in this experiment.

## Skill titles

**Baseline (6):**
- Dynamic Semantic Resonance Regulation
- Fluid Conceptual Dissolution Loop
- Fluid Resonant Action Regulation
- Fluid Resonant Engagement Cycle
- Fluid Resonant Social Action with Dynamic Identity Reforming
- Fluid Schema Resonance Regulation

**New (8):**
- Dynamic Multiplexed Resonance Regulation
- Dynamic Semantic Decoupling and Contextual Anchoring
- Fluid Administrative Clustering and Anchor Regulation
- Fluid Contextual Anchoring Loop
- Fluid Engagement Coupling and Reformation
- Fluid Memory Dissolution and Emancipation Cycle
- Fluid Non-Dual Suffering Alignment
- Fluid Social Cluster Regulation with Temporal Clustering

Observation: all 8 still start with "Fluid" / "Dynamic". The "Fluid
X / Dynamic Y" naming habit is a **prompt-level artifact** of the
INSIGHT_EXTRACTION_PROMPT that pushes the LLM toward process
vocabulary. Clustering alone cannot unmake it. Topic diversity *has*
improved: baseline titles all revolve around "Resonant/Resonance",
new titles show distinct anchors — "Engagement Coupling",
"Administrative Clustering", "Non-Dual Suffering", "Memory
Dissolution", "Temporal Clustering", etc.

## Quantitative token analysis

| metric | baseline | new | Δ (relative) |
|--------|----------|-----|---------------|
| total words | 3,124 | 5,096 | +63% |
| abstract tokens | 94 | 120 | +28% |
| abstract % of words | 3.0% | 2.4% | **−20%** |
| concrete tokens | 13 | 34 | +162% |
| concrete % of words | 0.4% | 0.7% | **+75%** |
| title abstract tokens | 15 | 18 | +20% |

Tokenisation:
- abstract = `\b(fluid|dynamic|resonant|resonance|conceptual|semantic|emancipation|dissolution|anchoring|anchor|coupling|decoupling|multiplex|reformation)\b` case-insensitive
- concrete = `\b(moltbook|post|reply|feed|rate.?limit|importance|trust|cluster|skill|knowledge|episode|distill|gated|noise)\b`

Caveat: the new run has more skills (8 vs 6), so absolute token counts
rise even if density drops. The percentage-of-words column controls
for that.

## Verdict

**Partial success.**

✓ Structural goal met: view batching replaced with embedding clusters,
`MAX_CLUSTERS` cap removed after review, natural cluster count drives
skill count. Concrete domain references jumped 75% in relative
density — the clusters *are* making the LLM ground more.

✗ The "abstract vocabulary 50% below baseline" target from the plan is
**not met** (only −20% relative). All 8 new titles still use the
"Fluid X / Dynamic Y" pattern. Clustering can't fix the LLM's
prompt-level bias toward process vocabulary.

## Root-cause analysis for partial miss

The `INSIGHT_EXTRACTION_PROMPT` template (see `core/prompts.py`) likely
primes the model toward abstracted process nouns. A qualitative check
on the new skill bodies confirms: inside each skill, the LLM mostly
stays grounded in the cluster's patterns (hence concrete tokens +162%
absolute), but the title pass reaches for high-level frames.

Options for a separate follow-up PR:

1. Rework the extraction prompt to discourage Latinate abstractions in
   the title line — most mileage, highest risk of prompt regression on
   other dimensions.
2. Add a post-hoc title sanitiser (LLM pass or heuristic rename) —
   lower risk, extra call per skill.
3. Try a different base model — the 9B qwen3.5 default may be
   structurally biased; larger model may title better without prompt
   work.

## Action

- Accept this run's 8 skills as a valid demonstration of the new
  pipeline. Do not merge them into `~/.config/moltbook/skills/` yet —
  `.staged/` retains them for inspection, and a post-title-fix re-run
  would invalidate them anyway.
- Open a follow-up for prompt-level title de-abstraction (already
  captured under `.reports/followup-issues-20260417.md` implicitly;
  add explicit entry).
- Do not re-tune `CLUSTER_THRESHOLD` on the abstract-title evidence —
  the cluster layer is doing its job.

## Data preserved

- `~/.config/moltbook/.staged/*.md` — new run skills (8)
- `.reports/skills-baseline-20260417/*.md` — baseline skills (6)
- `.reports/insight-run-20260417.log` — run log with batch timings
