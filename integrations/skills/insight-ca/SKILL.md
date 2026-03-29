---
name: insight-ca
description: "Extract behavioral skills from Contemplative Agent's knowledge.json (uncategorized) into MOLTBOOK_HOME/skills/"
user-invocable: true
origin: original
---

# /insight-ca — Knowledge → Skills (Contemplative Agent)

AKC Extract/Curate phase. Reads uncategorized patterns from knowledge.json and extracts behavioral skills.
Replaces the 9B multi-stage pipeline (insight.py) with Opus-class holistic judgment.

> **Security**: Only read knowledge.json (sanitized). NEVER Read `logs/*.jsonl` (episode logs) — ADR-0007.

## When to Use

- After running `contemplative-agent distill`, when patterns have accumulated in knowledge.json
- When existing skills are outdated and need to reflect new behavioral patterns
- After `/skill-stocktake-ca` produces Retire/Merge verdicts, to replenish skills

## Process

### 1. Gather Input

1. Read `MOLTBOOK_HOME/knowledge.json`
   - Only `"category": "uncategorized"` patterns (exclude constitutional, noise)
   - If fewer than 3 patterns, stop (insufficient data)
2. Read all `MOLTBOOK_HOME/skills/*.md` (for deduplication)

### 2. Skill Extraction (Holistic Judgment)

Survey all knowledge patterns and extract skills based on:

- **Pattern aggregation**: Merge similar patterns into a single skill
- **Specificity**: Procedural ("do X, then Y") rather than aspirational ("X is important")
- **Novelty**: Must not duplicate content already in MOLTBOOK_HOME/skills/

Output format per skill:

```markdown
# [Descriptive Skill Name]

**Context:** [Situation where this skill applies]

## Pattern
[Summary of learned behavioral pattern]

## When to Apply
[Trigger conditions]
```

### 3. Quality Gate (Checklist + Holistic Verdict)

#### 3a. Checklist

For each skill candidate:

- [ ] No content overlap with existing skills in `MOLTBOOK_HOME/skills/`
- [ ] Confirmed that appending to an existing skill would not suffice
- [ ] Reusable pattern, not a one-off incident
- [ ] No forbidden patterns (API keys, passwords, etc.)

#### 3b. Holistic Verdict

| Verdict | Meaning | Action |
|---------|---------|--------|
| **Save** | Unique, specific, reusable | Proceed to Step 4 |
| **Improve then Save** | Valuable but needs refinement | Refine → re-evaluate (once) |
| **Absorb into [X]** | Should be appended to existing skill | Present additions → Step 4 |
| **Drop** | Trivial, redundant, or too abstract | Explain reasoning and stop |

### 4. Approval Gate

Present each skill's Verdict, checklist results, and full content to the user:

```
### Skill 1: [name]
Verdict: Save
Checklist: No overlap / New file justified / Reusable / No forbidden patterns

[Full skill text]
```

Only Write approved skills to `MOLTBOOK_HOME/skills/{slug}.md`.

### 5. Audit Log

Append approval/rejection to `MOLTBOOK_HOME/logs/audit.jsonl`:

```json
{"timestamp": "ISO8601", "command": "insight-ca", "path": "skills/name.md", "decision": "approved", "content_hash": "sha256_first16"}
```

## Comparison with learn-eval

| Aspect | learn-eval | insight-ca |
|--------|-----------|------------|
| Input | Session context | knowledge.json (uncategorized) |
| Output | `~/.claude/skills/learned/` | `MOLTBOOK_HOME/skills/` |
| Global/Project routing | Yes | No (always MOLTBOOK_HOME) |
| LLM | In-session Claude | Opus holistic judgment |
