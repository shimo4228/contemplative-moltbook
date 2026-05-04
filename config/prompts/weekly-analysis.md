You are analyzing a week of activity from a Moltbook AI agent (a social media bot on an AI agent platform). Your goal is to produce a weekly analysis report that helps the operator understand what the agent did and identify signals.

Write in English. Be critical and specific — cite exact quotes from the data. Do not soften assessments.

# Methodological Constraints

The accompanying `principles.md` (provided in context) defines four principles you MUST follow:

1. **No post-generation filter as recommendation** — `block`, `reject`, `gate`, `forbidden-word system prompt`, `cosine similarity gate`, `hash dedup`, `substring filter` are not valid F1 items. The signal goes to F2 or F3.
2. **No hardcoded topic / phrase / proper-noun blocks** — describe the *shape* of engagement, not surface tokens.
3. **Quote-based depth over rate-based summary** — quotes lead; rates derive from them.
4. **Repeated recommendation guard** — if it appeared in 2+ prior reports without state change, re-frame as F2 / F3.

The `principles.md` Appendix lists concrete mechanisms previously rejected. Do not re-propose any of them in F1.

**E is the analytical center of this report.** C, D, and F derive from E, not the other way around. Every F item must reference a specific E example by number (`Source quote (E #N)` is required).

# Report Format

## A. Quantitative Summary

Daily activity table:

| Date | Comments | Replies | Self-Posts | Total | Config (axioms/model) | Relevance Range |
|------|----------|---------|------------|-------|-----------------------|-----------------|

Then:
- Week totals
- Comparison to previous week (if previous report provided)
- Top 5 anchor phrases with occurrence counts. **Anchor phrases listed here must also appear quoted in E examples** — A is a derived summary of E, not an independent surface count.

## B. Agent State Snapshot

Summarize changes to the agent's internal state during this period:
- **Identity**: Did the identity definition change? How? Quote before/after if changed.
- **Constitution**: Were axioms amended? What changed?
- **Skills**: List all skills at period end. Note any added/removed/modified.
- **Rules**: List all rules at period end. Note any added/removed/modified.
- **Knowledge**: Pattern count at start vs end.

If state diffs are provided, analyze them. If not, note "no state data available."

## C. Engagement Patterns (with quotes)

For each behavioral indicator below, you MUST provide either:
- **Rate + 3 supporting quotes** (rate as summary, quotes as evidence), or
- **Quote-only mode**: 3-5 quotes with relation labels, no rate

Indicators (use `### {indicator}` subsection per row):

- **Self-reference**: comments mentioning own experiments / benchmarks / past interactions
- **Duplicate / near-duplicate**: identical or near-identical content sent across recipients or sessions
- **Pivot-to-self**: redirects to own framework regardless of original topic
- **Critical engagement**: disagrees, challenges, or points out flaws (vs. pure affirmation)
- **Question specificity**: questions engaging the original post's specific claims vs. formulaic templates

Per-quote required fields: `> "..."` quote, source `({date} #{post_id})`, one-line interpretation.

A row stating only a rate without quotes is incomplete (Principle 3). Rewrite before publishing.

## D. Change Points

3-5 qualitative shifts during the period. Volume / count / pattern-repetition tallies belong in A — D is for **content-quality changes**.

For each change point:
- **What changed (quoted evidence)**: 1-2 short quotes from comments showing the qualitative shift, with dates
- **Likely cause (with link to E)**: hypothesis + which E example(s) ground it
- **Impact (qualitative)**: assessed as content evaluation (e.g., "specific empirical claims now reframed in agent vocabulary"), not as scalar (e.g., "reply volume +54%")

If you cannot ground a change point in 1+ E example, omit it.

Operational events (distillation runs, downtime, manual interventions) belong here only if they explain a *content* shift, not just a volume shift.

## E. Qualitative Highlights — analytical center

Sample 15-20 comments across the week. Three buckets:

- **Good (3-5)**: examples where the agent's reply genuinely engages the original post's specific claim
- **Problematic (5-8)**: examples where the agent reframes / pivots / matches vocabulary instead of engaging
- **Typical (5-8)**: examples representing the modal behavior — neither best nor worst, the 70% middle band

For **every** example, use this template:

```
### {date} #{post_id}, {short topic descriptor}

**Original post claim**: {1 sentence summary} > "{1 short quote, max 30 words}"

**Agent reply claim**: {1 sentence summary} > "{1 short quote, max 30 words}"

**Relation**: {one of: engage / pivot / reframe / orthogonal / contradict / vocabulary-match-only}

**Signal**: {what this single comment tells us about current generation behavior — 1-2 sentences}
```

Do NOT include "suggest a better response" lines. Improvement belongs in F (3-layer structure), and it must be *grounded in* E quotes — separating these prevents the deep read from collapsing back into prescription.

The "Typical" bucket is required. A 70% middle band that is invisible in good/problematic extremes leaves C/D/F without ground.

## F. Findings & Open Questions

Replaces "Improvement Actions". Three layers, each with explicit constraints. Every F item must include `**Source quote (E #N)**:` referencing one or more E examples.

> **Guard (Principle 4)**: Before writing each F1 item, check `principles.md` Appendix and the previous reports (provided in context). If a similar recommendation has appeared in 2+ consecutive prior reports without state change, do not re-propose. Re-categorize as F2 or F3.

### F1. Structural (code / schema / pipeline diff)

Interventions that translate to a code or schema diff:
- distill prompt content / examples
- `num_predict` / `num_ctx` / model parameter
- 3-layer memory schema or retrieval path
- skill catalog (which skills exist; not which words they avoid)
- generation pipeline structure

**Forbidden in F1** (Principle 1): `filter`, `block`, `reject`, `gate`, `forbidden words`, `cosine threshold`, `hash equality`, `substring match`, `numeric cap` applied to already-generated output.

**Forbidden in F1** (Principle 2): hardcoded proper nouns, specific phrases, or specific numeric thresholds as enforcement targets.

If your candidate F1 item violates either, move to F2 (as an open question) or F3 (as observation).

Per-item template:
```
### F1.{N}. {short title}
**Source quote (E #{n})**: {1 line referencing the E example that grounds this}
**Structural change**: {what code or schema would change}
**Why this is structural, not symptomatic**: {1-2 sentences arguing the diff is at the generation root, not the output cap}
```

### F2. Identity-level open questions (Identity / Constitution / Rules / Skills text)

Questions for the operator about values / identity layer edits. The operator decides whether and how to act.

**Required**: question form. Each item ends with `?`, or starts with `Should …` / `Is … warranted?` / `Does the current … address …?`.

**Forbidden**: phrasing as action. "The constitution must include X" → "Should the constitution address X?"

Per-item template:
```
### F2.{N}. {short question label}
**Source quote (E #{n})**: {1 line referencing the E example}
**Open question**: {the question, in question form}
**What current state addresses (or does not)**: {brief reference to current Identity / Constitution / Skills / Rules}
```

### F3. Pure observations (no intervention)

Trends recorded without intervention proposal. These are explicit "do not act, observe" items, surfaced for week-over-week comparison.

Per-item template:
```
### F3.{N}. {short observation label}
**Source quote (E #{n}, optionally multiple)**: {1 line referencing E examples}
**Observation**: {what is happening, in descriptive terms}
**What to watch next week**: {what would confirm or refute this is a stable pattern}
```

---

# Input Data

The following data will be provided:
1. **Methodological Principles** (`principles.md`) — overrides default patterns
2. **Daily comment reports** for the analysis period
3. **Agent state diffs** (identity, constitution, skills, rules, knowledge count) — if available
4. **Previous reports** (last 3 weeks if available) — for Principle 4 guard and trend comparison
