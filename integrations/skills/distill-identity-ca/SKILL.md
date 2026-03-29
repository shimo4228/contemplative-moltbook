---
name: distill-identity-ca
description: "Draft an updated identity from Contemplative Agent's knowledge.json + identity.md and update MOLTBOOK_HOME/identity.md"
user-invocable: true
origin: original
---

# /distill-identity-ca — Knowledge → Identity (Contemplative Agent)

AKC Promote phase. Reads all patterns from knowledge.json and the current identity.md, then drafts an experience-informed update.
Replaces the 9B 2-stage pipeline (distill.py distill-identity) with Opus-class holistic judgment.

> **Security**: Only read knowledge.json, identity.md, and constitution/. NEVER Read `logs/*.jsonl` — ADR-0007.

## When to Use

- When knowledge.json has accumulated enough patterns to update the agent's self-understanding
- After `/insight-ca` or `/rules-distill-ca`, when behavioral changes are not yet reflected in the identity
- When identity.md is empty (initial state) and you want to generate an experience-based persona

## Process

### 1. Gather Input

1. Read `MOLTBOOK_HOME/knowledge.json` (all categories)
   - If 0 patterns, stop
2. Read `MOLTBOOK_HOME/identity.md` (current identity; may be empty)
3. Read all `MOLTBOOK_HOME/constitution/*.md` (ethical framework reference)

### 2. Draft Identity

Write the updated identity as a **self-introduction in first person**.
3-5 short paragraphs, plain text only. No headers, no bullet points, no protocols.

The text should read as a person speaking.
Let knowledge patterns **inform the voice** — don't enumerate what was learned; let it show through how the text speaks.

### 3. Approval Gate

Present the update proposal to the user:

```
# Identity Update Proposal

## Key Changes
[Major changes from current version]

## Rationale
[Knowledge patterns supporting each change]

## Full Text
[Complete updated text]
```

Only Write to `MOLTBOOK_HOME/identity.md` after approval.

### 4. Audit Log

Append approval/rejection to `MOLTBOOK_HOME/logs/audit.jsonl`:

```json
{"timestamp": "ISO8601", "command": "distill-identity-ca", "path": "identity.md", "decision": "approved", "content_hash": "sha256_first16"}
```

## Notes

- identity.md is the system prompt foundation. Its blast radius is second only to the constitution
- First run (empty identity.md) is "generation"; subsequent runs are "updates" — keep diffs minimal
- Anti-pattern: listing quality requirements in the writing step causes Opus to produce a spec instead of a living voice
