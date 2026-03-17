You are deciding whether to add a new pattern to a social media agent's knowledge base.

## Candidate Pattern
{candidate}

## Existing Knowledge (numbered)
{knowledge}

## Decision

Compare the candidate against existing knowledge and choose exactly one:

- **SAVE**: The candidate describes a specific, actionable behavior not already captured. Add it.
- **ABSORB**: The candidate overlaps with an existing pattern but adds new detail. Merge them into a single, more complete pattern.
- **DROP**: The candidate is vague, duplicates existing knowledge without adding detail, or is a one-time observation with no reuse value.

If SAVE, reply with ONLY:
VERDICT: SAVE

If ABSORB, reply with:
VERDICT: ABSORB
TARGET: <number of the existing pattern to merge into>
MERGED: <rewritten pattern combining both — include the full context, not a summary>

If DROP, reply with ONLY:
VERDICT: DROP
