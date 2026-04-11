Reformat the practice analysis below into structured rule documents.

## What you receive

A free-form analysis listing candidate practices. Each accepted candidate looks like:

    **Practice**: [statement]
    - Coverage: [n/total skills]
    - Necessity: PASS — [one-sentence justification]
    - Intersection: PASS — [one-sentence justification]
    - Independence: PASS — [one-sentence justification]

Rejected candidates may also appear in the analysis — ignore them.

## What you must produce

Only include practices that PASSED all three tests (Necessity, Intersection, Independence). Do NOT create rules from failed or uncertain candidates. Do NOT invent new practices not present in the analysis.

### If at least 1 practice passed

Output format:

# [Short Descriptive Title for the Rule Set]

## Rule 1: [Practice Name]

**Practice:** [the practice statement from the analysis — imperative / declarative, 1–2 sentences. NOT trigger-action form.]

**Rationale:** [1–3 sentences synthesized from the three test justifications. Explain why this practice holds across the covered skills. Keep each sentence complete — do not truncate mid-sentence.]

## Rule 2: [Practice Name]

**Practice:** ...

**Rationale:** ...

(Repeat for each accepted practice.)

### If 0 practices passed

Output only the single line:

# No Universal Rules Found

Do not add explanation or apology.

## Strict rules

- Do NOT use trigger-action form ("When X, do Y"). Practices are standing orientations, not procedures.
- Do NOT paraphrase skill bodies; stay at the level of general methodology.
- Do NOT pad the Rationale with filler — keep it to the essential reason the practice holds.
- Do NOT introduce practices that were not listed in the analysis below.

{raw_output}
