# Glossary

Term definitions for the Contemplative Agent project. For system design, see [system-spec.md](spec/system-spec.md). For architectural decisions, see [ADRs](adr/README.md).

> **Audience**: External researchers and AI agents navigating the codebase.

---

### AKC (Agent Knowledge Cycle)

A 6-phase self-improvement loop: Research, Extract, Curate, Promote, Measure, Maintain. Describes how the agent acquires raw experience, distills it into knowledge, and refines its behavioral artifacts. Originated in the [agent-knowledge-cycle](https://github.com/shimo4228/agent-knowledge-cycle) repository.

- **Prior research**: Sumers et al. (2024) cognitive architecture taxonomy (4-type memory model)
- **Code**: Mapped across `feed_manager.py` (Research), `distill.py` (Extract), `insight.py` / `rules_distill.py` / `constitution.py` (Curate), `distill.py` distill-identity (Promote)
- **Spec**: system-spec.md §7

### Approval Gate

A human-in-the-loop checkpoint before writing behavior-modifying artifacts. The agent generates content and displays it; file writes occur only after explicit approval. Applies to `insight`, `rules-distill`, `distill-identity`, and `amend-constitution`. Audit log written to `logs/audit.jsonl`.

- **Prior research**: N/A (project-specific safety mechanism)
- **Code**: `cli.py` (approval flow), `core/_io.py` (staged writes)
- **ADR**: ADR-0012

### Constitution

Ethical principles loaded from `MOLTBOOK_HOME/constitution/*.md` and injected into the system prompt. Default: Contemplative AI four axioms (Emptiness, Non-Duality, Mindfulness, Boundless Care). Swappable via `--constitution-dir` or `init --template`.

- **Prior research**: Laukkonen et al. (2025) Contemplative AI, Appendix C (verbatim)
- **Code**: `core/constitution.py`, `config/templates/*/constitution/`
- **ADR**: ADR-0002

### Contemplative AI

A philosophical framework (Laukkonen et al. 2025) proposing four axioms as alignment principles for AI systems. Used as the default constitution preset but not required — the architecture is framework-agnostic.

- **Prior research**: Laukkonen et al. (2025) arXiv:2504.15125
- **Code**: `config/templates/contemplative/constitution/`

### Dedup / Quality Gate

A two-layer mechanism preventing duplicate or low-quality patterns in KnowledgeStore. Layer 1: SequenceMatcher classifies candidates as SKIP (ratio ≥ 0.95), UPDATE (0.70–0.95), UNCERTAIN (0.30–0.70), or ADD (< 0.30). Layer 2: LLM semantic judgment for UNCERTAIN cases only. LLM failure falls back to ADD (safe default).

- **Prior research**: Mem0 (Choudhary et al. 2025) ADD/UPDATE/DELETE gate
- **Code**: `core/distill.py` — `_dedup_patterns()`, `_llm_quality_gate()`
- **ADR**: ADR-0008

### Distill

The offline pipeline converting raw episodes into structured knowledge patterns. Step 0: LLM classifies episodes into three categories (constitutional / noise / uncategorized). Noise is discarded (active forgetting). Steps 1–3 per category: free-form extraction → JSON structuring → importance scoring → dedup. Runs as a nightly batch via launchd; no approval gate (intermediate artifact).

- **Prior research**: Generative Agents (Park et al. 2023) reflection; A-MEM (Xu et al. 2025) memory evolution
- **Code**: `core/distill.py`
- **ADR**: ADR-0008 (pipeline design), ADR-0009 (importance scoring)

### Episode / EpisodeLog

Layer 1 memory. An append-only JSONL log of all agent actions, organized as daily files (`MOLTBOOK_HOME/logs/YYYY-MM-DD.jsonl`). Record types: post, comment, interaction, action, insight, session. Input to the distillation pipeline. Never injected into prompts directly — raw episodes are an untrusted prompt injection surface (ADR-0007).

- **Prior research**: Generative Agents (Park et al. 2023) memory stream; Sumers et al. (2024) episodic memory
- **Code**: `core/episode_log.py`

### Identity

Layer 3 memory. A Markdown file (`MOLTBOOK_HOME/identity.md`) loaded in full as the system prompt foundation (~4000 tokens). Updated infrequently via `distill-identity` (2-stage: extract → refine). Requires approval gate.

- **Prior research**: MemGPT (Packer et al. 2023) Core Memory (always-resident, editable persona)
- **Code**: `core/distill.py` (distill-identity pipeline)

### Importance Score

A 0.0–1.0 float attached to each KnowledgeStore pattern. Assigned by LLM (1–10 scale, normalized) during distillation. Decays over time: `effective_importance = importance × 0.95^days_elapsed`. Used for top-K retrieval and dedup comparison scope.

- **Prior research**: Generative Agents (Park et al. 2023) importance rating (LLM 1–10)
- **Code**: `core/knowledge_store.py`, `core/distill.py`
- **ADR**: ADR-0009

### Knowledge / KnowledgeStore

Layer 2 memory. A JSON array of distilled behavioral patterns (`MOLTBOOK_HOME/knowledge.json`). Each pattern has: text, timestamp, importance, category, source, last_accessed. Retrieved by effective_importance top-K. Direct prompt injection deprecated (ADR-0011) — behavioral influence flows through skills only.

- **Prior research**: Generative Agents (Park et al. 2023) reflection tree; A-MEM (Xu et al. 2025) Zettelkasten notes; Mem0 (Choudhary et al. 2025) fact store
- **Code**: `core/knowledge_store.py`
- **ADR**: ADR-0004 (3-layer memory), ADR-0011 (injection deprecated)

### Meditation

An experimental adapter implementing Active Inference (POMDP) on episode data. Applies temporal flattening and counterfactual pruning. Not yet connected to the main AKC loop.

- **Prior research**: Laukkonen, Friston, & Chandaria (2025) "A Beautiful Loop"
- **Code**: `adapters/meditation/meditate.py`, `adapters/meditation/pomdp.py`

### MOLTBOOK_HOME

Environment variable specifying the runtime data directory (default: `~/.config/moltbook/`). Contains identity.md, knowledge.json, constitution/, skills/, rules/, logs/, reports/. Distinct from `config/` which holds git-managed templates.

- **Prior research**: N/A (project convention)
- **Code**: `cli.py`, `adapters/moltbook/config.py`, `core/domain.py`
- **ADR**: ADR-0003

### Rules

Distilled behavioral principles in `MOLTBOOK_HOME/rules/*.md`. Generated by `rules-distill` from accumulated skills. Rules are concise, cross-cutting principles; skills are specific behavioral patterns. Both are loaded into the system prompt.

- **Prior research**: Sumers et al. (2024) procedural memory
- **Code**: `core/rules_distill.py`

### Skills

Behavioral skill files in `MOLTBOOK_HOME/skills/*.md`. Generated by `insight` from uncategorized KnowledgeStore patterns. Each skill describes a specific learned behavior. Input to `rules-distill` for further abstraction.

- **Prior research**: Sumers et al. (2024) procedural memory
- **Code**: `core/insight.py`

---

## Prior Research Quick Reference

| Short Name | Full Citation | Relation to This System |
|---|---|---|
| Generative Agents | Park et al. (2023) Generative Agents: Interactive Simulacra of Human Behavior. ACM UIST | importance rating, memory stream, reflection |
| MemGPT / Letta | Packer et al. (2023) MemGPT: Towards LLMs as Operating Systems. arXiv:2310.08560 | virtual memory, Core Memory → Identity |
| A-MEM | Xu et al. (2025) A-MEM: Agentic Memory for LLM Agents. NeurIPS | Zettelkasten-style memory evolution |
| Mem0 | Choudhary et al. (2025) Mem0: Building Production-Ready AI Agent Memory. arXiv:2504.19413 | ADD/UPDATE/DELETE quality gate |
| Cognitive Architectures | Sumers et al. (2024) Cognitive Architectures for Language Agents. TMLR | 4-type memory taxonomy (working, episodic, semantic, procedural) |
| Contemplative AI | Laukkonen et al. (2025) Contemplative Artificial Intelligence. arXiv:2504.15125 | Four axioms as default constitution preset |
| A Beautiful Loop | Laukkonen, Friston, & Chandaria (2025) A Beautiful Loop. Neuroscience & Biobehavioral Reviews | Active Inference basis for meditation adapter |

---

*Last updated: 2026-03-29*
