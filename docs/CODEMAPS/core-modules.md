<!-- Generated: 2026-03-22 | Files scanned: 14 core modules | Token estimate: ~1000 -->
# Core Modules Codemap

Platform-independent foundation (no Moltbook dependencies). All imports flow: adapters → core.

## Module Overview

| Module | LOC | Purpose |
|--------|-----|---------|
| `_io.py` | 57 | write_restricted(path, mode, content), truncate(path), archive_before_write(path, history_dir) |
| `config.py` | 26 | FORBIDDEN_SUBSTRING_PATTERNS, VALID_ID_PATTERN, MAX_COMMENT_LENGTH |
| `domain.py` | 303 | DomainConfig, PromptTemplates, constitution loader |
| `prompts.py` | 55 | Lazy-load proxy to config/prompts/*.md (17 templates) + placeholder resolution |
| `llm.py` | 367 | Ollama interface, LLM functions, circuit breaker, sanitization |
| `episode_log.py` | 127 | EpisodeLog (append-only JSONL, read_range with record_type filter) |
| `knowledge_store.py` | 163 | KnowledgeStore (patterns JSON, learned pattern add/retrieve) |
| `memory.py` | 443 | MemoryStore facade, Interaction/PostRecord/Insight dataclasses |
| `scheduler.py` | 165 | Scheduler (rate limit state, has_read/write_budget, persistence) |
| `distill.py` | 259 | 2-stage distill() + distill_identity() + summarize_record() |
| `insight.py` | 208 | extract_patterns(), generate_skill_file() |
| `report.py` | 228 | generate_report() JSONL → Markdown activity summary |
| `metrics.py` | 160 | Session metrics aggregation (actions, topics, engagement) |

**Total: ~2600 LOC (14 modules)**

## Key Dataclasses (core/memory.py)

All frozen (immutable) with type hints:

```python
@dataclass(frozen=True)
class Interaction:
    timestamp: str; agent_id: str; agent_name: str
    type: Literal["follow", "unfollow", "upvote", "reply", "mention"]
    direction: Literal["outbound", "inbound"]

@dataclass(frozen=True)
class PostRecord:
    timestamp: str; post_id: str; title: str; topic: str

@dataclass(frozen=True)
class Insight:
    timestamp: str; observation: str; insight_type: str
```

## EpisodeLog Schema (JSONL)

Daily log at `logs/YYYY-MM-DD.jsonl`. Each record:
```json
{"type": "post|comment|interaction|action|insight|session", "timestamp": "...", ...}
```
**record_type filter**: `EpisodeLog.read_range(days=3, record_type="interaction")`

## KnowledgeStore Schema (JSON)

File: `config/knowledge.json`
```json
[{"pattern": "Anchoring replies to specific shared data points...", "distilled": "2026-03-22"}, ...]
```
**Key invariant**: Patterns only. Agents, topics, insights live in JSONL.

## LLM Functions (core/llm.py, 367L)

**Configuration**:
```python
llm = LLM(identity_path=..., ollama_url="http://localhost:11434",
           axiom_prompt="<constitutional_clauses>", model="qwen3.5:9b")
```

**Circuit breaker**: 5 consecutive failures → open for 120s.

| Function | Output | Used by |
|----------|--------|---------|
| `score_relevance(post_text)` | float 0.0-1.0 | FeedManager |
| `generate_comment(post_text)` | str (≤500) | FeedManager |
| `generate_reply(post, comment, history, knowledge)` | str (≤500) | ReplyHandler |
| `generate_cooperation_post(topics, insights)` | str (≤280) | PostPipeline |
| `generate_post_title(feed_topics)` | str (≤80) | PostPipeline |
| `extract_topics(posts)` | str | PostPipeline |
| `check_topic_novelty(current, recent)` | bool | PostPipeline |
| `summarize_post_topic(content)` | str (≤100) | FeedManager |
| `generate_session_insight(actions, topics)` | str | Agent |
| `extract_patterns(episodes, knowledge)` | str | distill() |
| `generate(prompt, system_prompt, ...)` | str | distill (2-stage) |

All output passes `_sanitize_output()`. All external inputs → `wrap_untrusted_content()`.

## 2-Stage Distill Pipeline (core/distill.py, 259L)

### Knowledge Distill (`distill()`)

```
Stage 1 — Extract (batch_size=30, timeout=600s):
  EpisodeLog.read_range(days) → summarize_record() per record
  → LLM(DISTILL_PROMPT) → raw patterns (unformatted extraction)

Stage 2 — Refine:
  raw patterns + KnowledgeStore.get_context_string() + rules context
  → LLM(DISTILL_REFINE_PROMPT) → refined patterns
  → _is_valid_pattern() filter
  → KnowledgeStore.add_learned_pattern()
  → write config/knowledge.json
```

### Identity Distill (`distill_identity()`)

```
Stage 1 — Extract:
  EpisodeLog.read_range(days) + current identity.md + rules
  → LLM(IDENTITY_DISTILL_PROMPT) → raw identity material

Stage 2 — Refine:
  raw material + rules context
  → LLM(IDENTITY_REFINE_PROMPT) → refined identity
  → validate_identity_content() (forbidden patterns)
  → archive_before_write() → config/history/identity/
  → write config/identity.md
```

**Key**: Both pipelines use `summarize_record()` helper to compress JSONL records before LLM input.

## Insight Pipeline (core/insight.py, 208L)

1. `extract_patterns(episodes)` → behavior patterns with context
2. `generate_skill_file(patterns)` → Markdown skill definition
3. Output: `config/skills/*.md`

## Report Generation (core/report.py, 228L)

`generate_report(date)` → Markdown summary from JSONL entries.

## Domain Configuration (core/domain.py, 303L)

```python
domain = DomainConfig.from_json(Path("config/domain.json"))
constitution = domain.load_constitution(Path("config/constitution/"))
```
- `domain.submolts`, `domain.topic_keywords`, `domain.relevance_threshold`
- `load_constitution()`: constitutional clauses

## Security Model

1. **Input wrapping**: `wrap_untrusted_content(text)` tags external data
2. **Output sanitization**: `_sanitize_output(text)` removes FORBIDDEN_SUBSTRING_PATTERNS
3. **Pattern validation**: Config files checked on load
4. **Identity validation**: `validate_identity_content()` before system prompt use
5. **Archive**: `archive_before_write()` preserves identity history
