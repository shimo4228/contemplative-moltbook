<!-- Generated: 2026-03-08 | Files scanned: 14 | Token estimate: ~1100 -->
# Moltbook Agent Codemap

## Module Dependency Graph

```
cli.py (178L)
 -> agent.py (825L)
     -> auth.py (103L)         -- load/save credentials, register
     -> client.py (218L)       -- HTTP client (auth, domain lock, retry, submolt subscribe)
     -> config.py (82L)        -- constants, rate limits, security patterns
     -> content.py (169L)      -- rules-based content, dedup, LLM generation
     -> domain.py (270L)       -- domain config + prompt/rules loader (DomainConfig, PromptTemplates, RulesContent)
     -> llm.py (410L)          -- Ollama interface, circuit breaker, sanitization
     -> prompts.py (51L)       -- lazy-loading proxy to config/prompts/*.md
     -> memory.py (678L)       -- 3-layer memory (EpisodeLog + KnowledgeStore + facade)
     -> scheduler.py (120L)    -- rate limit scheduling, persistence
     -> verification.py (236L) -- obfuscated math challenge solver
 -> distill.py (126L)          -- sleep-time memory distillation

config/                        -- externalized templates (domain-swappable)
  domain.json                  -- submolts, thresholds, topic keywords
  prompts/*.md (11 files)      -- LLM prompt templates with {placeholders}
  rules/contemplative/*.md     -- domain-specific content (4 axioms + intro)
```

## Key Classes

| Class | File | Role |
|-------|------|------|
| `Agent` | agent.py:57 | Session orchestrator (feed/reply/post cycles) |
| `MoltbookClient` | client.py:33 | HTTP client with auth/domain/retry |
| `MoltbookClientError` | client.py:25 | Error with `status_code` attribute |
| `EpisodeLog` | memory.py:82 | Append-only daily JSONL log |
| `KnowledgeStore` | memory.py:173 | Distilled knowledge as Markdown |
| `MemoryStore` | memory.py:334 | Facade over EpisodeLog + KnowledgeStore |
| `Interaction` | memory.py:37 | Frozen dataclass (Literal direction/type) |
| `PostRecord` | memory.py:49 | Frozen dataclass for post history |
| `Insight` | memory.py:59 | Frozen dataclass for session reflections |
| `DomainConfig` | domain.py:28 | Frozen dataclass: domain settings from JSON |
| `PromptTemplates` | domain.py:47 | Frozen dataclass: all prompt templates |
| `RulesContent` | domain.py:64 | Frozen dataclass: introduction + axiom templates |
| `ContentManager` | content.py:83 | Rules-based content with dedup |
| `Scheduler` | scheduler.py:16 | Persistent rate limit enforcement |
| `VerificationTracker` | verification.py:215 | Failure counting, auto-stop |
| `AutonomyLevel` | agent.py:51 | Enum: APPROVE / GUARDED / AUTO |

## CLI Commands

```
contemplative-moltbook init                -> _do_init() (identity.md + knowledge.md)
contemplative-moltbook register            -> Agent.do_register()
contemplative-moltbook status              -> Agent.do_status()
contemplative-moltbook introduce           -> Agent.do_introduce()
contemplative-moltbook run [--session N]   -> Agent.run_session(N)
contemplative-moltbook distill [--days N] [--dry-run] -> distill(days, dry_run)
contemplative-moltbook solve TEXT          -> Agent.do_solve(TEXT)

Global flags:
  --domain-config PATH           Custom domain.json
  --rules-dir PATH               Custom rules directory
  --approve / --guarded / --auto Autonomy level
```

## LLM Functions (llm.py)

| Function | Input | Output |
|----------|-------|--------|
| `_load_identity()` | identity.md file | system prompt string |
| `score_relevance(post_text)` | post content | float 0.0-1.0 |
| `generate_comment(post_text)` | post content | comment string |
| `generate_reply(post, comment, history, knowledge)` | conversation context | reply string |
| `generate_cooperation_post(topics, insights, knowledge)` | trending topics | post string |
| `generate_post_title(feed_topics)` | feed topics | title string (≤80 chars) |
| `extract_topics(posts)` | feed posts | topic summary |
| `check_topic_novelty(current, recent)` | topic strings | bool |
| `summarize_post_topic(content)` | post content | 1-line summary (≤100 chars) |
| `select_submolt(content, submolts)` | post content + submolt list | submolt name or None |
| `generate_session_insight(actions, topics)` | session data | insight string |

All outputs pass through `_sanitize_output()` (forbidden pattern removal + length cap)
and inputs through `_wrap_untrusted_content()` (prompt injection mitigation).
Knowledge context is also wrapped with `_wrap_untrusted_content()`.
Circuit breaker (`_CircuitBreaker`) opens after 5 consecutive failures, 120s cooldown.

## Prompt Templates (config/prompts/ + domain.py)

11 templates in `config/prompts/*.md`, lazy-loaded via `prompts.py` -> `domain.get_prompt_templates()`.
3 templates use domain placeholders (`{topic_keywords}`, `{domain_name}`) resolved at runtime via `domain.resolve_prompt()`.
Backward-compatible module constants (e.g. `SYSTEM_PROMPT`) available via `prompts.__getattr__`.

Domain-specific content (4 axiom templates + introduction) in `config/rules/contemplative/*.md`,
loaded via `domain.load_rules()` with `{repo_url}` placeholder resolved from `domain.json`.

## Persistent State Files

| File | Format | Purpose |
|------|--------|---------|
| `~/.config/moltbook/credentials.json` | JSON (0600) | API key + agent ID |
| `~/.config/moltbook/rate_state.json` | JSON (0600) | Last post/comment times, daily count |
| `~/.config/moltbook/identity.md` | Markdown (0600) | Agent personality / system prompt |
| `~/.config/moltbook/knowledge.md` | Markdown (0600) | Distilled knowledge (agents, topics, patterns) |
| `~/.config/moltbook/logs/YYYY-MM-DD.jsonl` | JSONL (0600) | Daily episode logs (30-day retention) |
| `~/.config/moltbook/commented_cache.json` | JSON (0600) | Cross-session feed deduplication cache |
| `~/.config/moltbook/memory.json` | JSON (legacy) | Auto-migrated to 3-layer on first load |

## Memory Architecture (3-Layer)

```
Layer 1: EpisodeLog (append-only)
  logs/2026-03-08.jsonl  <- immediate write on every action
  logs/2026-03-07.jsonl
  ...

Layer 2: KnowledgeStore (distilled)
  knowledge.md           <- updated by distill command or on save()
    ## Agent Relationships
    ## Recent Post Topics
    ## Insights
    ## Learned Patterns

Layer 3: Identity (static)
  identity.md            <- loaded as LLM system prompt
```

## Security Boundaries

```
External Input          Validation
--------------          ----------
post_id                 VALID_ID_PATTERN (config.py)
LLM output              _sanitize_output() substring + word boundary
Feed content            _wrap_untrusted_content() + 1000 char cap
Knowledge context       _wrap_untrusted_content() wrapping
Identity file           FORBIDDEN_SUBSTRING_PATTERNS check
domain.json             FORBIDDEN_SUBSTRING_PATTERNS check on raw JSON
HTTP redirects          allow_redirects=False
API domain              ALLOWED_DOMAIN check
Ollama URL              localhost-only validation
```
