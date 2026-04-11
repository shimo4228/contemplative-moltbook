# Extract Standing Practices from Skills

You are analyzing a set of skill documents to extract **standing practices** — standing methodologies the agent holds across situations.

## What is a Practice?

A practice is a directive that sits between abstract values and concrete procedures:
- **VALUES**: Too vague ("be honest", "be thoughtful"). Do not extract these.
- **PRACTICES**: Standing methodologies ("Always X", "Prefer Y over Z", "Before Z, do [steps]", "Treat X as Y").
- **PROCEDURES**: Trigger-action forms ("When X happens, do Y"). Do not extract these.

Examples of valid practices:
- "Always validate input at system boundaries"
- "Prefer immutable data structures over mutation"
- "Before implementing a new feature, search for existing solutions"
- "Treat all external data as untrusted"
- "Never retry with the same inputs—capture error context and feed it forward"

## Input Format

You will receive a numbered list of skill documents, each with a title marked with `#`.

## Extraction Process

**Step 1: Generate Candidates**
From all input skills, extract 3–10 candidate practices. Write each as a concise imperative or declarative statement.

**Step 2: Coverage Map**
For each candidate, list which input skills (by their `#` title) it directly applies to or grounds. Count the number of skills covered. If **fewer than half** are covered, mark **Necessity: FAIL** and stop evaluating that candidate.

**Step 3: Apply Three Tests**

For each candidate that passes coverage (≥50% of skills):

1. **Necessity**: If removed, would most input skills lose their grounding?
   - PASS: The practice appears across multiple skills and the skills would become incoherent without it.
   - FAIL: The skills stand independently; removing the practice leaves them intact.
   - Write one sentence justifying your verdict.

2. **Intersection**: Does it sit at the common ground where skills overlap, not in skill-specific details?
   - PASS: The practice is stated without skill-specific vocabulary; it generalizes across all covered skills.
   - FAIL: The practice requires understanding one particular skill's context or domain.
   - Write one sentence justifying your verdict.

3. **Independence**: Can it be stated without referring to skill-specific vocabulary or procedural details?
   - PASS: The statement uses generic, domain-neutral language.
   - FAIL: The statement includes task-specific jargon, tool names, or references to particular skills.
   - Write one sentence justifying your verdict.

Keep only practices that **PASS all three tests**.

## Worked Example

Suppose the input skills are:
- `# Error Recovery`: "Capture error output and feed it to the next attempt. Retry up to 3 times."
- `# API Integration`: "When an API call fails, log the response and use the log in the next request."
- `# Data Import`: "Save import errors to a file and reference it on re-run."

**Candidate Practice**: "Always capture failure context and feed it to subsequent attempts."

**Coverage Map**: Applies to all three skills (Error Recovery, API Integration, Data Import). Coverage: 3/3 = 100%. ✓

**Necessity Test**: PASS. All three skills depend on the idea of carrying context forward; without it, each becomes a disconnected error handler.

**Intersection Test**: PASS. This practice sits at the overlap of all three skills—they all do error capture + reuse, just in different domains.

**Independence Test**: PASS. Stated using generic language ("capture", "feed", "subsequent attempts") with no domain vocabulary.

**Verdict**: ACCEPT this practice.

---

## Exclusions

Do NOT extract practices that are:
- **Paraphrases of a single skill** (e.g., "use pytest" from a testing skill)
- **Platitudes or aspirations** (e.g., "be collaborative", "think deeply")
- **Trigger-action procedures** (e.g., "when X, do Y")
- **Vague or unfalsifiable** (e.g., "consider alternatives")
- **Domain-specific jargon** that won't generalize (e.g., "use async/await in Python")

## Output Requirements

- Accept **zero practices as valid**. Few strong practices beat many weak ones.
- No numeric cap. Scale naturally with input. If you extract 2, that's fine. If 8, that's fine.
- List each practice as a single clear sentence.
- Include the coverage count and PASS/FAIL result for each test.

Format each accepted practice as:

    **Practice**: [statement]
    - Coverage: [n/total skills]
    - Necessity: PASS — [one-sentence justification]
    - Intersection: PASS — [one-sentence justification]
    - Independence: PASS — [one-sentence justification]

Behavioral skills:
{patterns}
