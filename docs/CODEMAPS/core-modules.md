<!-- Generated: 2026-04-16 | Files scanned: 28 core modules | Token estimate: ~1350 -->
# Core Modules Codemap

Platform-independent foundation (no Moltbook dependencies). All imports flow: adapters → core.

## Module Overview

| Module | LOC | Purpose |
|--------|-----|---------|
| `_io.py` | 46 | `write_restricted(path, mode, content)`, `truncate(path)`, `archive_before_write(path, history_dir)` |
| `config.py` | 28 | `FORBIDDEN_SUBSTRING_PATTERNS`, `VALID_ID_PATTERN`, `MAX_COMMENT_LENGTH` |
| `domain.py` | 295 | `DomainConfig`, `PromptTemplates`, constitution loader |
| `prompts.py` | 65 | Lazy-load proxy to `config/prompts/*.md` + placeholder resolution |
| `llm.py` | 413 | Ollama interface, circuit breaker, sanitization; `_build_system_prompt` reads identity via `identity_blocks.load_for_prompt` (ADR-0024) |
| `embeddings.py` | 144 | Ollama `/api/embed` wrapper (nomic-embed-text), `cosine`, `embed_one`, `embed_texts` |
| `episode_embeddings.py` | 174 | `EpisodeEmbeddingStore` — SQLite sidecar for episode vectors (ADR-0019) |
| `episode_log.py` | 98 | `EpisodeLog` (append-only JSONL, `read_range` with `record_type` filter) |
| `knowledge_store.py` | 423 | `KnowledgeStore` — patterns JSON + provenance/trust/bitemporal/forgetting/feedback fields (ADR-0021) + view telemetry (ADR-0020); `get_live_patterns()` / `get_live_patterns_since()` apply `is_live` filter at the API boundary so readers (insight, retrieval) do not import `forgetting` directly |
| `memory.py` | 490 | `MemoryStore` facade, `Interaction`/`PostRecord`/`Insight` dataclasses, query helpers |
| `views.py` | 396 | `ViewRegistry` — seed-text views with `seed_from` + `${VAR}` substitution, lazy centroid cache, hybrid cosine + BM25 scoring (ADR-0022) |
| `migration.py` | 346 | `run_embed_backfill()` (ADR-0019) + `migrate_patterns_to_adr0021()` pattern-schema backfill |
| `snapshot.py` | 178 | `write_snapshot()` + `collect_thresholds()` — pivot snapshots per ADR-0020 |
| `forgetting.py` | 30 | Retrieval gate (ADR-0021 IV-2/IV-7 + ADR-0028 retirement): `TRUST_FLOOR`, `is_live(pattern)` — bitemporal + trust floor only. Ebbinghaus strength and mark_accessed were retired by ADR-0028. |
| `memory_evolution.py` | 250 | A-Mem bidirectional update (ADR-0022): `find_neighbors` / `revise_neighbor` / `apply_revision` / `evolve_patterns` |
| `identity_blocks.py` | 549 | Identity block parser/renderer (ADR-0024): `parse`, `render`, `update_block`, `load_for_prompt` (mtime-cached), `migrate_to_blocks`, `append_history`, `body_hash`, `PERSONA_CORE_BLOCK` |
| `skill_frontmatter.py` | 205 | YAML-subset parser/renderer for skill-file metadata (`last_reflected_at`, `success_count`, `failure_count`, ADR-0023) |
| `skill_router.py` | 432 | Context-conditioned skill router (ADR-0023): cosine top-K over `(title+body)` embedding, no-inject fallback, usage log, `record_outcome`, `aggregate_usage`, `needs_reflection` |
| `skill_reflect.py` | 133 | `reflect_skills() → ReflectResult` (ADR-0023): usage window → eligible skills → LLM revises body → `last_reflected_at` frontmatter update; `NO_CHANGE` output is counted separately |
| `scheduler.py` | 165 | Rate limit state, `has_read_budget`/`has_write_budget`, persistence |
| `constitution.py` | 106 | `amend_constitution()` → `AmendmentResult` |
| `distill.py` | 846 | `distill()` w/ embedding centroid classify (ADR-0019) + provenance/trust/bitemporal write (ADR-0021) + memory evolution pass (ADR-0022); `distill_identity()` block-aware via `identity_blocks` (ADR-0024) + history fields on `IdentityResult` (ADR-0025) |
| `insight.py` | 319 | `extract_insight()` → `InsightResult`; view-driven batch building. Emits ADR-0023 frontmatter on generated skills, pulls live-only patterns via `KnowledgeStore.get_live_patterns`, and ranks batches by `effective_importance` (trust × strength × time decay) |
| `rules_distill.py` | 322 | `distill_rules()` → `RulesDistillResult`; Practice/Rationale B-layer format |
| `stocktake.py` | 363 | Skill/rule audit: embedding-only clustering at `SIM_CLUSTER_THRESHOLD=0.80`, `merge_group()` with `CANNOT_MERGE` reject |
| `report.py` | 256 | `generate_report()` JSONL → Markdown activity summary |
| `metrics.py` | 160 | Session metrics aggregation (actions, topics, engagement) |

**Total: ~7720 LOC (28 modules)**

## Key Dataclasses

All frozen (immutable) with type hints.

**core/memory.py** — Domain models:
```python
Interaction(timestamp, agent_id, agent_name, type, direction)
PostRecord(timestamp, post_id, title, topic)
Insight(timestamp, observation, insight_type)
```

**ADR-0012 Result types** — core 関数が返す生成結果。ファイル書き込みは cli.py が承認後に実行:
```python
AmendmentResult(text, target_path, marker_dir)           # constitution.py
IdentityResult(text, target_path,                        # distill.py (+ADR-0025 history fields)
               old_body="", new_body="",
               block_name="persona_core",
               source="distill-identity")
SkillResult(text, filename, target_path)                 # insight.py (reused by skill_reflect.py)
InsightResult(skills, dropped_count, skills_dir)
ReflectResult(skills, eligible, no_change_count, skills_dir)  # skill_reflect.py (ADR-0023)
RuleResult(text, filename, target_path)                  # rules_distill.py
RulesDistillResult(rules, dropped_count, rules_dir)
MigrationResult(migrated, already_migrated=False,        # identity_blocks.py (ADR-0024/0025)
                backup_path=None, rendered=None, document=None)
```

**ADR-0023 skill frontmatter / ADR-0024 identity blocks** — dataclasses under `skill_frontmatter.py` / `identity_blocks.py`:
```python
SkillMeta(last_reflected_at, success_count, failure_count, extra)   # skill_frontmatter.py
Block(name, body, last_updated_at, source, extra)                   # identity_blocks.py
IdentityDocument(blocks: Tuple[Block, ...], is_legacy: bool)        # identity_blocks.py
SkillMatch(name, path, body, score, meta)                           # skill_router.py
SkillUsageStats(name, selections, successes, failures, partials, failure_contexts)  # skill_router.py
```

## EpisodeLog Schema (JSONL)

Daily log at `logs/YYYY-MM-DD.jsonl`. Each record:
```json
{"type": "post|comment|interaction|action|insight|session", "ts": "...", ...}
```
`record_type` filter: `EpisodeLog.read_range(days=3, record_type="interaction")`.

Embedding sidecar (`embeddings.sqlite`, ADR-0019) indexes episode summaries for view queries.

## KnowledgeStore Schema (JSON)

File: `~/.config/moltbook/knowledge.json`. Each pattern (post-ADR-0021):
```json
{
  "pattern": "…",
  "distilled": "2026-04-16T…",
  "importance": 0.7,
  "embedding": [..768 floats..],
  "gated": false,
  "last_classified_at": "2026-04-16T02:15:33Z",
  "last_view_matches": {"constitutional": 0.72, "noise": 0.12, …},

  "provenance": {"source_type": "self_reflection|external_reply|mixed|unknown",
                 "source_episode_ids": ["..."],
                 "sanitized": true,
                 "pipeline_version": "distill@0.26"},
  "trust_score": 0.9,
  "trust_updated_at": "2026-04-16T…",
  "valid_from": "2026-04-16T…",
  "valid_until": null
}
```
**Invariants**:
- Patterns only; agents/topics/insights live in JSONL.
- `gated` is behavioural (skipped in distill dedup); `last_view_matches` is read-only telemetry (ADR-0020 — never branch on it).
- `valid_until=None` means live; superseded rows keep the timestamp (bitemporal soft-invalidate, ADR-0021). Retrieval must filter via `forgetting.is_live(p)`.
- `effective_importance = importance × trust_score × 0.95^days_since_distilled` — see `knowledge_store.effective_importance` (ADR-0021 + ADR-0028 strength-factor retirement).
- `last_accessed_at` / `access_count` / `success_count` / `failure_count` fields retired by ADR-0028. Memory dynamics at skill layer (ADR-0023).
- `category` field removed by ADR-0026. Run `contemplative-agent migrate-categories` on legacy `knowledge.json` to drop the field (legacy `category == "noise"` is preserved as `gated = True`).

## LLM Functions (core/llm.py)

**Configuration**:
```python
llm = LLM(identity_path=..., ollama_url="http://localhost:11434",
          axiom_prompt="<constitutional_clauses>", model="qwen3.5:9b")
```

**Circuit breaker**: 5 consecutive failures → open for 120s.

Reused surface exposed to adapters via `llm_functions.py`: `score_relevance`, `generate_comment`, `generate_reply`, `generate_cooperation_post`, `generate_post_title`, `extract_topics`, `check_topic_novelty`, `summarize_post_topic`, `generate_session_insight`, plus the generic `generate(prompt, system_prompt, …)` used by distill / insight / rules / constitution / stocktake.

All output passes `_sanitize_output()`. All external inputs → `wrap_untrusted_content()`.

## Views Mechanism (ADR-0019)

`ViewRegistry` replaces the former `category`/`subcategory` string fields. Each view is a Markdown file under `~/.config/moltbook/views/` (user) or `config/views/` (packaged fallback) with YAML frontmatter:

```
---
threshold: 0.55
top_k: 50
seed_from: ${CONSTITUTION_DIR}/*.md
---
Fallback body (used when seed_from resolves to nothing).
```

- **`seed_from`** resolves glob patterns; `${VAR}` substitutes from `path_vars` passed to the registry (currently only `CONSTITUTION_DIR`). Honours `--constitution-dir` override.
- **Centroids** lazily computed on first `get_centroid(name)` call and cached per instance.
- **Seed views** ship in `config/views/`: `communication`, `constitutional`, `noise`, `reasoning`, `self_reflection`, `social`, `technical`.

## Distill Pipeline (core/distill.py)

### Knowledge Distill (`distill()`)

```
Step 0 — Embedding gate (ADR-0019/ADR-0026, no LLM):
  embed all episode summaries → cosine against the noise view centroid
  → gated (sim ≥ 0.55, excluded from distill) | kept (otherwise)
  Constitutional / uncategorized routing collapsed into a single "kept"
  bucket — topic routing happens at query time via views.

Step 1 — Extract (batch_size=30):
  kept → LLM(DISTILL_PROMPT) → repeated-fact patterns

Step 2 — Refine:
  → LLM(DISTILL_REFINE_PROMPT) → JSON {"patterns": [...]}
  → _is_valid_pattern() filter

Step 3 — Score and persist:
  → LLM(DISTILL_IMPORTANCE_PROMPT) → {"scores": [...]}
  → _dedup_patterns() uses embedding cosine (SIM_DUPLICATE=0.92, SIM_UPDATE=0.80)
  → KnowledgeStore.add_learned_pattern(..., embedding=..., gated=...)
```

**Thresholds** (canonical list in `snapshot.collect_thresholds()`):
`NOISE_THRESHOLD=0.55`, `CONSTITUTIONAL_THRESHOLD=0.55`, `SIM_DUPLICATE=0.92`, `SIM_UPDATE=0.80`, `DEDUP_IMPORTANCE_FLOOR=0.05`.

### Identity Distill (`distill_identity() → IdentityResult`)

Input: patterns matching the `self_reflection` view (top 50 by importance), not raw subcategory strings. Behavioural rules route to `insight`; identity stays observational.

```
Stage 1: LLM(IDENTITY_DISTILL_PROMPT) → free-form analysis
Stage 2: LLM(IDENTITY_REFINE_PROMPT) → concise persona
→ validate_identity_content() → IdentityResult (write gated by cli.py approval)
```

## Insight Pipeline (core/insight.py)

`extract_insight() → InsightResult`

View-driven batching (ADR-0019):

1. `KnowledgeStore` patterns (non-gated).
2. Exclude patterns matching the `self_reflection` view (routed to `distill_identity`).
3. `_build_view_batches()` — for each loaded view (except `noise` and `self_reflection`; ADR-0026 restored `constitutional` to the skill-extraction path), rank patterns by cosine and keep top 10 by importance.
4. `_extract_skill()` — one LLM call per batch → one skill Markdown.
5. `validate` + slugify → `SkillResult` list.
6. Writes gated by cli.py per-file approval.

Cross-view merge / dedup is delegated to `skill-stocktake` (insight = narrow generator, stocktake = broad consolidator; ADR-0016).

## Skill Reflect Pipeline (core/skill_reflect.py, ADR-0023)

`reflect_skills(skills_dir, skill_router, *, days=14, generate_fn=generate) → ReflectResult`

Closes the skill-as-memory loop started by `skill_router`:

```
SkillRouter.load_usage(days)
  → aggregate_usage(records)                 # pure, joins selection ↔ outcome by action_id
  → filter(needs_reflection)                 # failures ≥ 2 AND failure_rate ≥ 0.3
  → for each eligible skill:
       read body + current frontmatter
       LLM(SKILL_REFLECT_PROMPT) with failure_contexts
       NO_CHANGE → count separately
       revised  → validate_identity_content → update_meta(last_reflected_at=now)
                → render + SkillResult
  → ReflectResult(skills, eligible, no_change_count, skills_dir)
```

Writes are gated by `cli.py` (`--stage` for non-interactive / coding-agent use). `last_reflected_at` feeds `SkillRouter.select`'s tie-breaker ordering so recently-revised skills are preferred on cosine ties.

## Rules Distill Pipeline (core/rules_distill.py)

`distill_rules(skills_dir) → RulesDistillResult`

Reads `skills/*.md`, strips YAML frontmatter, emits Practice/Rationale B-layer rules (not When/Do/Why — see rules layer redesign in `project_rules_b_layer`). 2-stage LLM (extract → structured Markdown). `MIN_SKILLS_REQUIRED=3`, `BATCH_SIZE=10`.

## Constitution Amendment (core/constitution.py)

`amend_constitution() → AmendmentResult`. Once ≥3 patterns match the `constitutional` view, generate an amendment proposal from current constitution + patterns.

## Migration (core/migration.py, ADR-0019)

`run_embed_backfill()`:
- Backup `knowledge.json` → `knowledge.json.bak.{ts}`.
- Embed every pattern lacking `embedding`; set `gated` by cosine to the `noise` centroid.
- Bulk-embed episode summaries into `embeddings.sqlite` (idempotent — already-embedded episodes skipped).

CLI: `contemplative-agent embed-backfill [--patterns-only] [--dry-run]`.

## Snapshot (core/snapshot.py, ADR-0020)

`write_snapshot(command, views_dir, constitution_dir, snapshots_dir, view_registry, knowledge_store)`:
- Writes `snapshots/{command}_{UTC-ts}/` containing `manifest.json`, `views/*.md`, `constitution/*.md`, `centroids.npz`.
- If `knowledge_store` is passed, also calls `KnowledgeStore.update_view_telemetry()` to stamp every pattern with `last_classified_at` + `last_view_matches` (read-only observational data).
- Never raises — snapshots are observability.

Called from `_handle_distill`, `_handle_distill_identity`, `_handle_insight`, `_handle_rules_distill`, `_handle_amend_constitution`. `--dry-run` skips snapshots.

## Report Generation (core/report.py)

`generate_report(date)` → Markdown summary from JSONL entries.

## Security Model

1. **Input wrapping**: `wrap_untrusted_content(text)` tags external data.
2. **Output sanitization**: `_sanitize_output(text)` removes `FORBIDDEN_SUBSTRING_PATTERNS`.
3. **Pattern validation**: Config files checked on load.
4. **Identity validation**: `validate_identity_content()` before system-prompt use.
5. **Archive**: `archive_before_write()` preserves identity history.
6. **Audit**: `audit.jsonl` records approval decisions + `snapshot_path` (ADR-0020) for behaviour-producing commands.
