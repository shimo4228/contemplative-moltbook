---
name: amend-constitution-ca
description: "Draft constitutional amendments from Contemplative Agent's knowledge.json (constitutional) and update MOLTBOOK_HOME/constitution/"
user-invocable: true
origin: original
---

# /amend-constitution-ca — Constitutional Amendment (Contemplative Agent)

AKC Promote phase. Drafts constitutional amendments from constitutional patterns in knowledge.json.
Replaces the 9B pipeline (constitution.py) with Opus-class holistic judgment.

> **Security**: Only read knowledge.json and constitution/. NEVER Read `logs/*.jsonl` — ADR-0007.

## When to Use

- After `contemplative-agent distill` has accumulated 3+ constitutional patterns
- When the agent's ethical judgment could benefit from refinement
- After switching constitution templates, to make experience-based adjustments

## Process

### 1. Gather Input

1. Read `MOLTBOOK_HOME/knowledge.json`
   - Only `"category": "constitutional"` patterns
   - If fewer than 3, stop (insufficient ethical experience)
2. Read all `MOLTBOOK_HOME/constitution/*.md` (current constitution)

### 2. Draft Amendments (Holistic Judgment)

Survey constitutional patterns and the current constitution, then draft amendments:

- **Preserve structure**: Respect the existing category structure (Emptiness, Non-Duality, Mindfulness, Boundless Care, etc.)
- **Experience-informed**: Reflect ethical learnings from constitutional patterns
- **Minimal changes**: Amend only where needed; avoid full rewrites
- **Consistency**: Amendments must not contradict other clauses

### 3. Quality Gate

Self-evaluate the amendment proposal against:

- [ ] Current constitution structure is preserved
- [ ] Each amendment is grounded in specific constitutional pattern experiences
- [ ] No contradictions introduced between clauses
- [ ] No forbidden patterns (API keys, passwords, etc.)
- [ ] Necessity is clear (no unnecessary amendments)

### 4. Approval Gate

Present the amendment proposal to the user:

```
# Constitution Amendment Proposal

## Changes
[Summary of amendments]

## Rationale
[Constitutional patterns supporting each change]

## Full Text
[Complete amended text]
```

Only Write to `MOLTBOOK_HOME/constitution/{name}.md` after approval.

### 5. Audit Log

Append approval/rejection to `MOLTBOOK_HOME/logs/audit.jsonl`:

```json
{"timestamp": "ISO8601", "command": "amend-constitution-ca", "path": "constitution/contemplative-axioms.md", "decision": "approved", "content_hash": "sha256_first16"}
```

## Notes

- The constitution has the widest blast radius. Proceed with caution. Amend incrementally
- When using `--constitution-dir` with an alternative framework (stoic, utilitarian, etc.), respect that framework's structure
- Matches constitution.py's `MIN_PATTERNS_REQUIRED = 3` threshold
