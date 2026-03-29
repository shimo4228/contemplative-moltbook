---
name: rules-distill-ca
description: "Extract cross-cutting principles from Contemplative Agent's MOLTBOOK_HOME/skills/ and distill them into rules/"
user-invocable: true
origin: original
---

# /rules-distill-ca — Skills → Rules (Contemplative Agent)

AKC Promote phase. Reads skills in MOLTBOOK_HOME/skills/ holistically and distills recurring principles into rules/.
Replaces the 9B multi-stage pipeline (rules_distill.py) with Opus-class holistic judgment.

> **Security**: Only read skills/ and rules/. NEVER Read `logs/*.jsonl` — ADR-0007.

## When to Use

- After `/insight-ca` has built up a collection of skills
- When `/skill-stocktake-ca` reveals the same principle across multiple skills
- When rules feel insufficient or incomplete

## Process

### 1. Gather Input

1. Read all `MOLTBOOK_HOME/skills/*.md`
2. Read all `MOLTBOOK_HOME/rules/*.md`

### 2. Principle Extraction (Holistic Judgment)

Survey all skills and rules, then extract rule candidates.

#### Extraction Criteria (all must be met)

1. **Appears in 2+ skills**: Principles found in only one skill stay in that skill
2. **Prescribes action**: Must be expressible as "do X" or "never do Y" (not "X is important")
3. **Clear violation risk**: Can explain in one sentence what goes wrong if ignored
4. **Not already covered**: Not a mere rephrasing of an existing rule

#### Verdict

| Verdict | Meaning | Action |
|---------|---------|--------|
| **Append** | Add to existing section of an existing rule | target + draft |
| **Revise** | Existing rule content is inaccurate/insufficient | target + before/after |
| **New Section** | Add new section to an existing rule file | target + draft |
| **New File** | Create a new rule file | filename + full draft |
| **Already Covered** | Existing rules sufficiently cover this | Reason only |
| **Too Specific** | Should stay at the skill level | Link to relevant skill |

### 3. Summary Table + Details

```
# Rules Distillation Report

## Summary
Skills scanned: {N} | Rules: {M} files | Candidates: {K}

| # | Principle | Verdict | Target | Confidence |
|---|-----------|---------|--------|------------|
| 1 | [principle] | Append | rule-x.md §Section | high |
| 2 | [principle] | New File | rule-y.md | medium |

## Details

### 1. [Principle Name]
Verdict: Append to rule-x.md §Section
Evidence: skill-a §Pattern, skill-b §When to Apply
Violation risk: [one sentence]
Draft:
  [text to append]
```

#### Verdict Quality Requirements

```
# Good
Append to rules/engagement.md §Reply Strategy:
"Share one personal experience related to the post's topic before asking a question"
Evidence: skill-reply-enhancement §Pattern, skill-feed-engagement §When to Apply
— Both skills independently describe a "self-disclosure + question" pattern. Should be unified as a rule.

# Bad
Append to rules/engagement.md: Improve communication
```

### 4. Approval Gate

User decides per candidate:
- **Approve**: Apply draft as-is
- **Modify**: Edit draft before applying
- **Skip**: Do not apply this candidate

**Never modify rules automatically. Always require user approval.**

### 5. Audit Log

Append changes to `MOLTBOOK_HOME/logs/audit.jsonl`:

```json
{"timestamp": "ISO8601", "command": "rules-distill-ca", "path": "rules/name.md", "decision": "approved", "content_hash": "sha256_first16"}
```

## Comparison with rules-distill

| Aspect | rules-distill | rules-distill-ca |
|--------|--------------|-----------------|
| Scope | `~/.claude/skills/` + `~/.claude/rules/` | `MOLTBOOK_HOME/skills/` + `rules/` |
| Scripts | scan-skills.sh, scan-rules.sh | Not needed (direct Read) |
| Batching | Sub-agents (theme clusters) | Not needed (Opus single pass) |
| Extraction threshold | 2+ skills | 2+ skills (same) |
