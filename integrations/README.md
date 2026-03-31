# Coding Agent Integrations

## Claude Code Hooks (Active)

PreToolUse hooks that block coding agents from reading raw episode logs — a prompt injection surface. See [docs/security/](../docs/security/) for the threat model.

```bash
bash integrations/claude-code/install-hooks.sh
```

Installs 3 hooks to `~/.claude/hooks/` and prints the `settings.json` snippet to add.

## Skills (Shelved)

Coding agent skills (`-ca` series) are shelved. See [ADR-0013](../docs/adr/0013-shelve-coding-agent-skills.md).
