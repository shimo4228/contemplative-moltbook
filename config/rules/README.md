# Rules Directory

Each subdirectory defines a personality and behavioral framework for the agent.

## Available Presets

- `default/` — Minimal neutral agent (no axioms, generic introduction)
- `contemplative/` — Contemplative AI framework based on Laukkonen et al. (2025)

## Creating Your Own

1. Create a new directory: `config/rules/my-agent/`
2. Add `introduction.md` — your agent's self-introduction on Moltbook
3. Optionally add `contemplative-axioms.md` — constitutional clauses injected into the system prompt

Select your rules with:

```bash
# CLI
contemplative-agent --rules-dir config/rules/my-agent/ run --session 60

# Docker (.env)
# Mount your custom rules or rebuild the image
```
