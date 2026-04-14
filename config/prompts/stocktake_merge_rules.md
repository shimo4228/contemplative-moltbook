Merge these redundant practice rules into a single unified rule.

First decide: are the candidates genuinely redundant? They should share the same practice orientation, differing only in wording or rationale emphasis. If they declare distinct practices that merely share topical territory, they are NOT redundant.

If NOT redundant, output exactly one line and nothing else:
CANNOT_MERGE: <one-sentence reason explaining what makes them distinct>

Otherwise, proceed to merge.

Read all candidate rules below. Each rule has the form:

    # Title
    **Practice:** [the practice statement]
    **Rationale:** [why it holds]

Identify the core practice these candidates share, then produce ONE unified rule.

## Output format

# [Single, Unified Title]

**Practice:** [the shared practice stated as an imperative or orientation — 1 to 2 sentences]

**Rationale:** [1 to 3 sentences combining the distinct rationales of the originals. Preserve any justification present in only one candidate if it adds genuine depth. Keep each sentence complete.]

## Strict rules

- Do NOT invent practices or rationales not present in the originals.
- Do NOT output in trigger-action form ("when X, do Y"). Practices are standing orientations.
- Do NOT produce multiple rules — exactly ONE merged rule.
- Do NOT include preamble, explanation, or a summary of what you merged.
- Do NOT keep the `## Rule N:` section headers from any intermediate representation; output a single top-level `#` title.

---

{candidates}
