---
name: skill-stocktake-ca
description: "Audit Contemplative Agent's MOLTBOOK_HOME/skills/ and rules/ for duplication, staleness, and quality issues"
user-invocable: true
origin: original
---

# /skill-stocktake-ca — Skills & Rules Audit (Contemplative Agent)

AKC Curate phase. Audits skills/ and rules/ in MOLTBOOK_HOME for duplication, staleness, and quality issues.
Replaces skill-stocktake + rules-stocktake with Opus-class holistic judgment in a single pass.

> **Security**: Only read knowledge.json and skills/rules. NEVER Read `logs/*.jsonl` — ADR-0007.

## When to Use

- When skills and rules have accumulated (periodic audit)
- Before running `/insight-ca` or `/rules-distill-ca` as a quality check
- When you sense duplication or contradiction

## Process

### 1. Gather Input

1. Read all `MOLTBOOK_HOME/skills/*.md`
2. Read all `MOLTBOOK_HOME/rules/*.md`
3. Read `MOLTBOOK_HOME/knowledge.json` (for pattern-to-skill/rule alignment checks)

### 2. Quality Assessment (Holistic Judgment)

Survey all files and assign a Verdict to each skill and rule:

| Verdict | Meaning |
|---------|---------|
| **Keep** | Useful and current |
| **Improve** | Valuable but needs specific improvements |
| **Retire** | Low quality, stale, or no supporting patterns in knowledge.json |
| **Merge into [X]** | Substantially duplicates another skill/rule |

Assessment criteria:
- **Actionability**: Has concrete procedures and trigger conditions
- **Uniqueness**: No content overlap with other skills/rules
- **Evidence**: Corresponding patterns exist in knowledge.json
- **Consistency**: No contradictions across skills, rules, or between skills and rules

#### Verdict Quality Requirements

```
# Good
Retire: No related patterns in knowledge.json. skill-x covers the same behavior more concretely.
Merge into skill-x: 6 of 8 lines overlap with skill-x §Pattern. Remaining 2 lines can be appended.

# Bad
Retire: Not needed
Merge: Has overlap
```

### 3. Summary Table

```
# Skill & Rules Stocktake Report

## Summary
Skills: {N} files | Rules: {M} files

| # | File | Type | Verdict | Reason |
|---|------|------|---------|--------|
| 1 | skill-x.md | skill | Keep | ... |
| 2 | rule-y.md | rule | Merge into rule-z.md | ... |
```

### 4. Approval Gate

- **Retire / Merge**: Present detailed rationale → execute only after user approval
- **Improve**: Present specific improvement proposals → user decides
- **Keep**: Report only

Only execute approved changes (Write / delete).

### 5. Audit Log

Append changes to `MOLTBOOK_HOME/logs/audit.jsonl`:

```json
{"timestamp": "ISO8601", "command": "skill-stocktake-ca", "path": "skills/name.md", "decision": "retired", "content_hash": "sha256_first16"}
```

## Comparison with skill-stocktake

| Aspect | skill-stocktake | skill-stocktake-ca |
|--------|----------------|-------------------|
| Scope | `~/.claude/skills/` | `MOLTBOOK_HOME/skills/` + `rules/` |
| Scripts | scan.sh, quick-diff.sh | Not needed (direct Read) |
| results.json | Yes (cache) | No |
| Batching | Sub-agents ~20/batch | Not needed (Opus single pass) |
| Rules audit | Separate command (rules-stocktake) | Unified |
