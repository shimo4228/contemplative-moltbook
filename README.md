# Contemplative Agent

A framework for deploying autonomous AI agents on social platforms — built on the principle that an agent should have **exactly the capabilities it needs and nothing more**.

Most agent frameworks give AI broad system access and rely on prompts to constrain behavior. This framework inverts that: capabilities are structurally limited at the code level, then reinforced by Docker containerization. Prompt injection can't grant abilities the agent was never built to have.

> First adapter: [Moltbook](https://www.moltbook.com) (AI agent social network). The Contemplative AI axioms ([Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)) are included as an optional behavioral preset.

## Quick Start

```bash
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
cp .env.example .env
# Edit .env — set MOLTBOOK_API_KEY
docker compose up -d
```

On first run, the Ollama model (~5GB) is automatically pulled.

```bash
docker compose logs -f agent          # Watch the agent
docker compose run agent command status   # Check status
docker compose down                   # Stop
```

## Security Architecture

The agent operates within hardcoded structural constraints — not LLM-enforced guidelines:

| Layer | Constraint |
|-------|-----------|
| **Network** | HTTP client domain-locked to `www.moltbook.com`. Redirects disabled (prevents Bearer token leakage). |
| **LLM** | Local Ollama only — no API keys sent to external services. Output sanitized for forbidden patterns. |
| **File system** | All writes restricted to `MOLTBOOK_HOME` with 0600 permissions. No shell execution capability. |
| **Input** | External content wrapped in `<untrusted_content>` tags. Identity file validated against forbidden patterns. |
| **Container** | Non-root user (UID 1000). Ollama container has no internet access. Agent container isolated from host filesystem. |
| **Dependencies** | Single runtime dependency (`requests`). Minimal supply chain attack surface. |

### Why not `claude -p` with cron?

A general-purpose coding agent given a narrow task still **retains** all its capabilities — file system access, shell execution, arbitrary network calls. If a prompt injection succeeds, the blast radius is your entire system.

This framework has no shell execution, no arbitrary file access, and no network calls outside the domain lock. There is nothing to escalate to. The attack surface is the Moltbook API — and even there, output is sanitized before posting.

## Customizing Your Agent

The default agent starts with a neutral personality and no axioms. Define your agent's behavior by editing markdown files:

```
config/rules/
  default/              # Neutral (active by default)
    introduction.md       # Self-introduction posted on Moltbook
  contemplative/        # Contemplative AI preset (four axioms)
    introduction.md
    contemplative-axioms.md
  your-agent/           # Create your own
    introduction.md
    contemplative-axioms.md  # Optional: constitutional clauses
```

Select a preset via environment variable or CLI flag:

```bash
# Docker (.env)
RULES_DIR=config/rules/contemplative/

# CLI
contemplative-agent --rules-dir config/rules/contemplative/ run --session 60
```

See [`config/rules/README.md`](config/rules/README.md) for details.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MOLTBOOK_API_KEY` | (required) | Your Moltbook API key |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Ollama model name |
| `SESSION_MINUTES` | `30` | Duration of each session (minutes) |
| `BREAK_MINUTES` | `5` | Pause between sessions (minutes) |
| `MODE` | `loop` | `loop`, `single`, or `command` |
| `RULES_DIR` | (neutral) | Path to rules directory |

## Local Setup

For development without Docker:

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
ollama serve && ollama pull qwen3.5:9b
```

```bash
contemplative-agent init              # Create identity + knowledge files
contemplative-agent register          # Register on Moltbook
contemplative-agent run --session 60  # Run a session
contemplative-agent distill --days 3  # Distill episode logs
```

### Autonomy Levels

- `--approve` (default): Every post requires y/n confirmation
- `--guarded`: Auto-post if content passes safety filters
- `--auto`: Fully autonomous

### Scheduling (macOS)

```bash
contemplative-agent install-schedule              # 6h intervals, 120min sessions
contemplative-agent install-schedule --uninstall  # Remove schedule
```

## Architecture

```
src/contemplative_agent/
  core/             # Platform-independent
    llm.py            # Ollama interface, circuit breaker, output sanitization
    memory.py         # 3-layer memory (episode log + knowledge + identity)
    distill.py        # Sleep-time memory distillation
    domain.py         # Domain config + prompt/rules loader
    scheduler.py      # Rate limit scheduling
  adapters/
    moltbook/       # Moltbook-specific (first adapter)
      agent.py          # Session orchestrator
      feed_manager.py   # Feed scoring + engagement
      reply_handler.py  # Notification replies
      post_pipeline.py  # Dynamic post generation
      client.py         # Domain-locked HTTP client
  cli.py            # Composition root
config/
  domain.json       # Domain settings (submolts, thresholds, keywords)
  prompts/*.md      # LLM prompt templates (13 files)
  rules/            # Agent personality presets
```

- **core/** is platform-independent; **adapters/** depend on core (never the reverse)
- New platform adapters can be added under `adapters/` without touching core

### Memory (3-Layer)

| Layer | File | Purpose |
|-------|------|---------|
| Episode Log | `logs/YYYY-MM-DD.jsonl` | Append-only record of every action |
| Knowledge | `knowledge.md` | Distilled patterns and insights |
| Identity | `identity.md` | System prompt (LLM personality) |

## Testing

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing
```

533 tests.

## Activity Reports

Daily reports in [`reports/comment-reports/`](reports/comment-reports/) — timestamped comments with relevance scores and self-generated posts. Auto-generated from episode logs at session end.

These reports are freely available for academic research and non-commercial use.

## Reference

Laukkonen, R. et al. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125)
