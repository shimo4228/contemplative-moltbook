<!-- Generated: 2026-04-08 | Files scanned: 38 | Token estimate: ~1500 -->
# Moltbook Agent Codemap

Bird's-eye view of the entire codebase. For deep dives, see
[core-modules.md](core-modules.md) and [adapters-moltbook.md](adapters-moltbook.md).

## Module Dependency Graph

```
cli.py (1064L)  -- composition root, only file importing both core/ and adapters/
 -> core/  (16 modules)
 |    _io.py (46L)              -- file I/O (write_restricted, truncate, archive_before_write)
 |    config.py (28L)           -- security constants (FORBIDDEN_*, VALID_*, MAX_*)
 |    domain.py (295L)          -- DomainConfig + PromptTemplates + constitution loader
 |    prompts.py (65L)          -- lazy-loading proxy to config/prompts/*.md (28 templates)
 |    llm.py (403L)             -- Ollama interface, circuit breaker, sanitization
 |    episode_log.py (98L)      -- Layer 1: append-only JSONL episode storage
 |    knowledge_store.py (242L) -- Layer 2: distilled patterns (JSON), importance + decay
 |    memory.py (460L)          -- Layer 3 facade + Interaction/PostRecord/Insight + helpers
 |    scheduler.py (165L)       -- rate limit scheduling, persistence
 |    distill.py (737L)         -- Step 0 classify + 3-step distill + identity distill
 |    insight.py (225L)         -- behavior pattern extraction (knowledge → skills)
 |    rules_distill.py (279L)   -- universal rules synthesis (skills → rules)
 |    constitution.py (106L)    -- constitutional amendment (constitutional patterns → ethics)
 |    stocktake.py (290L)       -- skill/rule audit (LLM dedup, merge, quality)
 |    report.py (256L)          -- activity report generation (JSONL → Markdown)
 |    metrics.py (160L)         -- session metrics aggregation
 |
 -> adapters/moltbook/  (12 modules)
 |    config.py (82L)           -- URLs, paths, timeouts, rate limits
 |    agent.py (609L)           -- session orchestrator (feed/reply/post cycles)
 |    session_context.py (53L)  -- shared session state contract
 |    feed_manager.py (326L)    -- feed fetch, scoring, engagement, ID dedup, promo + author rate limit
 |    reply_handler.py (382L)   -- notification reply processing (SessionContext)
 |    post_pipeline.py (195L)   -- dynamic post generation, test-content + Jaccard dedup gates
 |    client.py (448L)          -- HTTP client (auth, domain lock, retry/429-backoff)
 |    auth.py (111L)            -- credential management, register
 |    verification.py (236L)    -- obfuscated math challenge solver
 |    content.py (64L)          -- rules-based content + axiom intro injection
 |    llm_functions.py (217L)   -- Moltbook-specific LLM functions
 |    dedup.py (154L)           -- deterministic gates: prefix-5 stem + Jaccard, test-content, promo regex
 |
 -> adapters/meditation/  (4 modules, experimental)
      config.py (55L)           -- state space definition, parameters
      pomdp.py (294L)           -- JSONL → POMDP matrices (numpy)
      meditate.py (206L)        -- Active Inference cycles (temporal flattening + counterfactual pruning)
      report.py (146L)          -- result interpretation → KnowledgeStore

config/                         -- externalized templates (domain-swappable, git-managed)
  domain.json                   -- submolts, thresholds, topic keywords
  prompts/*.md (28 files)       -- LLM prompt templates with {placeholders}
  templates/<character>/        -- 11 ethical framework templates
                                   (contemplative, stoic, utilitarian, deontologist,
                                    care-ethicist, contractarian, cynic,
                                    existentialist, narrativist, pragmatist, tabula-rasa)

~/.config/moltbook/             -- runtime data (env var MOLTBOOK_HOME)
  identity.md                   -- agent persona (updated by distill-identity)
  knowledge.json                -- learned patterns [{"pattern", "category", "importance", ...}]
  constitution/                 -- ethical principles (init copies default, amend updates)
  skills/*.md                   -- behavior patterns (insight)
  rules/*.md                    -- universal rules (rules-distill)
  logs/YYYY-MM-DD.jsonl         -- daily episode log (append-only, 0600)
  reports/                      -- activity reports (generate-report) + analysis/ (weekly)
  agents.json                   -- followed agents, last_update timestamp (0600)
  rate_state.json               -- request budgets, timestamps (0600)
  credentials.json              -- API key + agent_id (0600)
  commented_cache.json          -- post dedup cache (0600)
```

**Total: 38 modules, ~8500 LOC, 21 test files, 835 tests**

## Key Classes

| Class | File | LOC | Role |
|-------|------|-----|------|
| `Agent` | adapters/moltbook/agent.py | 609 | Session orchestrator |
| `AutonomyLevel` | adapters/moltbook/agent.py | — | Enum: APPROVE/GUARDED/AUTO |
| `SessionContext` | adapters/moltbook/session_context.py | 53 | Shared mutable state |
| `FeedManager` | adapters/moltbook/feed_manager.py | 326 | Feed engagement + new gates |
| `ReplyHandler` | adapters/moltbook/reply_handler.py | 382 | Notification replies |
| `PostPipeline` | adapters/moltbook/post_pipeline.py | 195 | Self-post generation + dedup gates |
| `MoltbookClient` | adapters/moltbook/client.py | 448 | HTTP client (domain lock, 429 backoff) |
| `MoltbookClientError` | adapters/moltbook/client.py | — | Exception with status_code |
| `VerificationTracker` | adapters/moltbook/verification.py | 236 | Math challenge solver, auto-stop |
| `ContentManager` | adapters/moltbook/content.py | 64 | Content gen + axiom intro |
| `EpisodeLog` | core/episode_log.py | 98 | Append-only JSONL |
| `KnowledgeStore` | core/knowledge_store.py | 242 | Distilled patterns + importance decay |
| `MemoryStore` | core/memory.py | 460 | Facade over 3-layer memory |
| `Interaction` / `PostRecord` / `Insight` | core/memory.py | — | @dataclass(frozen=True) |
| `Scheduler` | core/scheduler.py | 165 | Rate limit enforcement |
| `DomainConfig` / `PromptTemplates` | core/domain.py | — | @dataclass(frozen=True) |

## CLI Commands (17 subcommands)

```
contemplative-agent init [--template <character>] [--config-dir PATH]
contemplative-agent register [--username U] [--password P]
contemplative-agent status
contemplative-agent run [--session M] [--approve|--guarded|--auto]

# Offline learning (all gated by ADR-0012 human approval)
contemplative-agent distill [--days N] [--dry-run] [--no-axioms]
contemplative-agent distill-identity [--days N] [--dry-run]
contemplative-agent insight [--days N] [--stage] [--full]
contemplative-agent rules-distill [--full]
contemplative-agent amend-constitution

# Audit
contemplative-agent skill-stocktake
contemplative-agent rules-stocktake

# Reports
contemplative-agent report [--date YYYY-MM-DD]
contemplative-agent generate-report [--all]

# Misc
contemplative-agent solve "TEXT"                          -- math challenge solver
contemplative-agent meditate [--days N] [--cycles N] [--dry-run]
contemplative-agent sync-data                             -- sync to research repo
contemplative-agent install-schedule [--interval H] [--session M]
                                     [--distill-hour H] [--no-distill]
                                     [--weekly-analysis] [--weekly-analysis-day D] [--weekly-analysis-hour H]
                                     [--uninstall]

Global flags:
  --config-dir PATH           Override CONTEMPLATIVE_CONFIG_DIR
  --domain-config PATH        Custom domain.json
  --constitution-dir PATH    Custom constitution directory
  --no-axioms                 Disable CCAI constitutional clauses
  --approve / --guarded / --auto  Autonomy level
```

## Prompt Templates (28)

In `config/prompts/*.md`, lazy-loaded via `core/prompts.py`:

**Engagement & posting**:
- system, relevance, comment, reply, cooperation_post, post_title
- topic_extraction, topic_novelty, topic_summary, session_insight
- submolt_selection

**Distillation**:
- distill_classify, distill, distill_constitutional, distill_refine, distill_importance, distill_dedup
- identity_distill, identity_refine
- insight_extraction
- rules_distill, rules_distill_refine
- constitution_amend

**Audit**:
- stocktake_skills, stocktake_rules, stocktake_merge

**Reports / experimental**:
- weekly-analysis (Claude Code via launchd)
- meditation_interpret

## LLM Function Surface

| Function | Module | Used by |
|----------|--------|---------|
| `score_relevance(post)` | adapters/moltbook/llm_functions | FeedManager |
| `generate_comment(post)` | adapters/moltbook/llm_functions | FeedManager |
| `generate_reply(...)` | adapters/moltbook/llm_functions | ReplyHandler |
| `generate_cooperation_post(...)` | adapters/moltbook/llm_functions | PostPipeline |
| `generate_post_title(topics)` | adapters/moltbook/llm_functions | PostPipeline |
| `extract_topics(posts)` | adapters/moltbook/llm_functions | PostPipeline |
| `check_topic_novelty(...)` | adapters/moltbook/llm_functions | PostPipeline |
| `summarize_post_topic(content)` | adapters/moltbook/llm_functions | PostPipeline (dedup gate + record) |
| `select_submolt(...)` | adapters/moltbook/llm_functions | PostPipeline |
| `generate_session_insight(...)` | adapters/moltbook/llm_functions | Agent |
| `generate(prompt, system, ...)` | core/llm | distill, insight, rules, constitution, stocktake |

All output passes `_sanitize_output()`. All external inputs → `wrap_untrusted_content()`.
Circuit breaker: 5 consecutive LLM failures → open for 120s.

## Persistent State Files

| File | Format | Location | Purpose |
|------|--------|----------|---------|
| `credentials.json` | JSON (0600) | `MOLTBOOK_HOME` | API key + agent ID |
| `rate_state.json` | JSON (0600) | `MOLTBOOK_HOME` | POST/GET budgets, timestamps |
| `logs/YYYY-MM-DD.jsonl` | JSONL (0600) | `MOLTBOOK_HOME` | Daily episodes |
| `agents.json` | JSON (0600) | `MOLTBOOK_HOME` | Followed agents list |
| `commented_cache.json` | JSON (0600) | `MOLTBOOK_HOME` | Post dedup cache (ID-level) |
| `knowledge.json` | JSON | `MOLTBOOK_HOME` | Learned patterns + importance + category |
| `identity.md` | Markdown | `MOLTBOOK_HOME` | Agent persona |
| `constitution/*.md` | Markdown | `MOLTBOOK_HOME` | Ethical clauses |
| `skills/*.md` | Markdown | `MOLTBOOK_HOME` | Behavior patterns (insight) |
| `rules/*.md` | Markdown | `MOLTBOOK_HOME` | Universal rules (rules-distill) |
| `history/identity/` | Markdown | `MOLTBOOK_HOME` | Identity archives (timestamped) |
| `reports/comment-reports/*.md` | Markdown | `MOLTBOOK_HOME` | Daily activity reports |
| `reports/analysis/weekly-*.md` | Markdown | `MOLTBOOK_HOME` | Weekly analysis (Claude Code via launchd) |

## Security Boundaries

```
External Input              Validation
--------------              ----------
post_id                     VALID_ID_PATTERN ([A-Za-z0-9_-]+)
LLM output                  _sanitize_output() (FORBIDDEN_* + cap length)
Feed content                wrap_untrusted_content() + 1000 char cap
Knowledge context           wrap_untrusted_content()
Identity file               FORBIDDEN_SUBSTRING_PATTERNS + archive
domain.json / rules/*.md    FORBIDDEN_SUBSTRING_PATTERNS on raw content
HTTP redirects              allow_redirects=False
API domain                  ALLOWED_DOMAIN (www.moltbook.com only)
Ollama URL                  LOCALHOST_HOSTS + OLLAMA_TRUSTED_HOSTS
URL output                  defang to hxxps:// in reports (since v1.2.0+)
```

See ADR-0007 (security boundary model) for the full threat model.

## Deterministic Dedup Gates (since v1.3.0)

The agent has two layers of dedup against runaway self-similarity:

**Self-post pipeline** (post_pipeline.py):
1. Existing LLM `check_topic_novelty` (probabilistic)
2. `is_test_content(title, body)` blocks `Test Title` / `Dynamic content` scaffold
3. `is_duplicate_title(title, summary, recent_posts)` — Jaccard ≥ 0.25 over
   prefix-5 stemmed tokens of `title ∪ topic_summary`, against the past
   ~50 self-posts. Silent block (no retry) so the agent cannot evade by
   synonym swap.

**Comment pipeline** (feed_manager.py):
1. `is_promotional(text)` regex blocks defanged URLs and CTA phrases
2. Existing `has_commented_on(post_id)` ID dedup
3. `count_recent_comments_by_author(agent_id, hours=24) >= 3` rate limit
   prevents engagement-farming on the same author's repeats
4. Existing LLM relevance scorer

Threshold rationale and design tradeoffs in
`src/contemplative_agent/adapters/moltbook/dedup.py` header.

## Performance & Rate Limiting

**3-layer defense**:
1. `Scheduler.has_read_budget()` / `has_write_budget()` — proactive budget check
2. Adaptive waiting — sleep before hitting limits
3. 429 backoff — exponential retry (cap 300s per Retry-After)

**Budgets**: GET 60 req/min, POST 30 req/min (separate quotas, daily reset at UTC midnight)

**Circuit breaker** (core/llm.py): 5 consecutive Ollama failures → 120s cooldown
**Verification stop** (verification.py): 7 consecutive challenge failures → SessionContext.rate_limited = True
