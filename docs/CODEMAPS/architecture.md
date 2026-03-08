<!-- Generated: 2026-03-08 | Files scanned: 21 | Token estimate: ~650 -->
# Architecture

## Project Type
Monorepo: alignment rules + 2 Python applications (agent + benchmark)

## System Diagram

```
                    contemplative-agent-rules
                    ========================
  rules/contemplative/     prompts/      adapters/
  (4 axiom .md files)      (full.md)     (cursor/copilot/generic)
         |
         v
  +-----------------+     +-------------------------+
  | moltbook-agent  |     | benchmarks/prisoners-   |
  | (Python 3.9+)   |     | dilemma (Python 3.9+)   |
  | 14 modules      |     | 6 modules               |
  | ~3460 LOC       |     |                         |
  +-----------------+     +-------------------------+
         |                          |
    Moltbook API              Ollama (local)
    (www.moltbook.com)        qwen3.5:9b
         |                          |
    Ollama (local) <----------------+
    qwen3.5:9b
```

## Data Flow — Moltbook Agent

```
CLI (argparse)
 |
 v
Agent.run_session()
 |
 +-> _run_reply_cycle()  -- notifications -> generate_reply -> post comment
 +-> _run_feed_cycle()   -- feed -> score_relevance -> generate_comment -> post
 +-> _run_post_cycle()   -- extract_topics -> check_novelty -> dynamic post
 |
 +-> MemoryStore (facade)
 |    +-> EpisodeLog     -- append-only JSONL (~/.config/moltbook/logs/)
 |    +-> KnowledgeStore -- distilled Markdown (~/.config/moltbook/knowledge.md)
 +-> Scheduler           -- rate limit tracking (~/.config/moltbook/rate_state.json)
 +-> MoltbookClient      -- HTTP with auth, domain lock, 429 retry
 +-> DomainConfig        -- config/domain.json (submolts, thresholds, keywords)
 +-> PromptTemplates     -- config/prompts/*.md (lazy-loaded, placeholder-resolved)
 +-> RulesContent        -- config/rules/contemplative/*.md (axioms + intro)
 +-> Identity            -- system prompt from identity.md
```

## Data Flow — Distillation (offline)

```
CLI: contemplative-moltbook distill --days N
 |
 v
distill()
 +-> EpisodeLog.read_range(N)   -- read last N days of episodes
 +-> KnowledgeStore.get_context_string()  -- current knowledge
 +-> Ollama (generate)          -- extract patterns from episodes
 +-> KnowledgeStore.add_learned_pattern()  -- persist new patterns
 +-> EpisodeLog.cleanup()       -- remove logs older than 30 days
```

## Data Flow — IPD Benchmark

```
CLI (argparse)
 |
 v
run_benchmark()
 +-> play_match(LLMPlayer(baseline), opponent)
 +-> play_match(LLMPlayer(contemplative), opponent)
 |
 v
cohens_d() -> format_report() -> save_results()
```

## Entry Points
- `contemplative-moltbook` -> `contemplative_moltbook.cli:main`
- `ipd-benchmark` -> `ipd.cli:main`
