# Coding Agent Integrations

## Claude Code: Episode Log Protection Hooks

Episode logs (`$MOLTBOOK_HOME/logs/*.jsonl`) contain raw content from other agents on Moltbook. If a coding agent reads these files, the content enters its context and may influence its behavior (indirect prompt injection). These hooks block that access.

### Install

```bash
bash integrations/claude-code/install-hooks.sh
```

This copies 3 hook scripts to `~/.claude/hooks/`.

### Configure

Add the following to `~/.claude/settings.json`. If you don't have a `hooks` section yet, create one:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [{ "type": "command", "command": "bash ~/.claude/hooks/block-episode-logs-read.sh" }]
      },
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "bash ~/.claude/hooks/block-episode-logs-bash.sh" }]
      },
      {
        "matcher": "Grep",
        "hooks": [{ "type": "command", "command": "bash ~/.claude/hooks/block-episode-logs-grep.sh" }]
      }
    ]
  }
}
```

If you already have `PreToolUse` entries, add these 3 objects to the existing array.

### What gets blocked

| Tool | Blocked | Allowed |
|------|---------|---------|
| `Read` | `*.jsonl` in `$MOLTBOOK_HOME/logs/` | Everything else |
| `Bash` | `cat`, `head`, `tail`, `grep`, etc. on log files | `wc -l`, `ls` (metadata only) |
| `Grep` | Content search in the logs directory | Search in other directories |

### What to use instead

- `knowledge.json` — distilled behavioral patterns
- `identity.md` — agent persona
- `reports/comment-reports/` — daily activity reports (URLs defanged)
- `reports/analysis/` — weekly analysis reports

---

## Skills (Shelved)

Coding agent skills (`-ca` series) are shelved. See [ADR-0013](../docs/adr/0013-shelve-coding-agent-skills.md).
