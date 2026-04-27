# ADR-0032: Stance — Contemplative Agent as a Runtime Agent, Symbiotic with Its Hosts

## Status

accepted — post-hoc articulation of a design stance already realised across the codebase

This is a **worldview ADR** in the sense defined by `docs/adr/README.md`: it does not solve a new problem, it names the design posture under which the project's other ADRs become legible. Many of the project's prohibitions and gates only earn their cost in this stance; outside it they would be over-engineering.

## Date

2026-04-27

## Context

A growing share of AI agent failures (publicly disclosed runtime vulnerabilities, prompt injection escapes, runaway shell execution, cascading writes through unintended adapters) trace back to a single category mistake: applying the design assumptions of one agent category (per-line human review, tolerated nondeterminism, prompt-level capability adjustment, host-provided orchestration) to a different category (production task execution without per-action review).

A coding agent is not unsafe because it can execute shell commands; those capabilities are part of its purpose, and a developer reviews each action. A general-purpose LLM host is not unsafe because it exposes a broad tool surface; the user decides which tools to install. A runtime agent that ships with the same capability surface as either, without the corresponding human-in-the-loop, is unsafe — because no developer is reviewing each action and no user is curating the tools.

This project's design judgments — domain-locked network access, no shell execution, no arbitrary file traversal, one external adapter per process, three-tier autonomy fixed in code, immutable episode logs, replayable pivot snapshots, human approval gate for behaviour-modifying writes — are all responses to the runtime context. None of them would be necessary in a coding agent, an orchestrator, a general-purpose host, or a GUI agent, **because in those categories the missing guarantees come from the host or the human in the loop**. A runtime agent does not have those guarantees coming from anywhere else, so it must hold them itself.

Until now this stance has been **implicit**. The 30 prior ADRs each justify their own design choice on its own terms, but the underlying premise that "this is a runtime agent, and therefore it must provide internally what the other categories receive from their hosts" has never been stated as a stance in its own right. That implicitness is the source of two recurring confusions:

1. **External readers** evaluating contemplative-moltbook against the conventions of one of the host categories (developer ergonomics of coding agents, capability breadth of general-purpose hosts, framework flexibility of orchestrators) judge it too restrictive — without seeing that the restrictions exist precisely because the host-side guarantees are absent in the runtime context
2. **Internal reasoning** about whether to add a new capability defaults to host-category intuitions ("the agent should be able to…") instead of runtime-agent intuitions ("under what gate, with what audit trail, with what failure semantics, given that no host is providing these?")

This ADR makes the stance explicit so that both confusions resolve at the source. It also restores a framing that was present in early README iterations of contemplative-moltbook — **symbiosis with hosts** — and that was lost during subsequent slim-downs.

## Decision

This implementation is explicitly a **runtime agent**, and it is designed to be **symbiotic with its hosts** rather than self-sufficient.

A **runtime agent** is an agent that executes tasks in production without per-action human review. Examples: autonomous SNS engagement (this project's first adapter), monitoring and alerting agents, scheduled automation jobs, autonomous trading agents, agents embedded in clinical or legal workflows. Human involvement takes the form of approval gates at promotion boundaries, exception logs for review after the fact, and episodic audit — not per-line approval of every action.

Runtime agents do not run in a vacuum. They run **inside** one or more host categories — coding agents that develop and modify them, orchestrators that compose them, general-purpose hosts that execute them, GUI agents that operate them. Each host provides some guarantees and withholds others. The runtime agent's design must hold whatever the host does not.

This stance does not say any host category is unsafe (each is safe in its context) or that runtime agents are superior. It says these are **distinct design problems**, that runtime agents **depend on host categories** to provide development, composition, execution, and operation surfaces, and that AAP-style accountability constraints, security-by-absence, and the prohibitions adopted across this project's 30 prior ADRs are the runtime agent's response to what hosts cannot guarantee.

## Distinction — Runtime Agent and the Host Categories

| Axis | Coding Agent | Orchestrator | General-purpose Host | GUI Agent | Runtime Agent |
|------|--------------|--------------|---------------------|-----------|---------------|
| Purpose | Design / implementation assistance | Compose multiple agents / steps | Run arbitrary LLM + tools | Operate other software via UI | Production task execution |
| Human involvement | Per-line review expected | Framework user designs the graph | User curates tools, monitors output | User watches the screen | Approval gate at promotion + exception logs |
| Nondeterminism | Tolerated (human corrects) | Tolerated (replan / retry) | Tolerated (user inspects) | Tolerated (user intervenes) | Must be isolated and audited |
| Exception handling | "Try and see" allowed | Retry / replan branches | User-mediated | User-mediated | Stop + log mandatory |
| Capability boundaries | Adjusted via prompt | Configured per node | Configured per tool | OS-level sandboxing | Fixed in code constraints |
| Accountability | Developer | Framework user | Host operator | Operating user | Decision-route / institutional |
| Examples | Claude Code, Aider, Cursor | LangChain, LangGraph, AutoGen | OpenClaw, Open WebUI, MCP hosts | Computer Use, Operator | Contemplative Agent, monitoring agents, autonomous trading |

The distinction is not a spectrum or a maturity gradient. The first four categories are **hosts** within which a runtime agent can run; the fifth is the layer that actually performs the production task. A runtime agent is not "a hardened coding agent" or "a constrained orchestrator" — it is a different kind of artifact, distinguished by what it must hold internally because the host cannot supply it.

## Symbiosis with Hosts

Runtime agents do not replace hosts; they live inside them. Each host category provides a different surface for the runtime agent to inhabit:

- **Coding agent as host** (Claude Code, Cursor, Aider) — develops, modifies, and reviews the runtime agent's code. The runtime agent treats the coding agent as a trusted developer surface
- **Orchestrator as host** (LangChain, LangGraph, AutoGen) — composes the runtime agent with other agents or steps. The runtime agent appears as a node in a larger graph
- **General-purpose host** (OpenClaw, MCP host, Open WebUI) — provides the LLM, the tool registry, and the execution loop. The runtime agent is one tool or capability among many
- **GUI agent as host** (Computer Use, Operator) — drives the runtime agent through its surface (CLI, web UI, file edits) the same way it drives other software

The framing for this comes from an early dev.to articulation of contemplative-moltbook's design:

> "A symbiotic design is a design that trusts its host."
> — *Do Autonomous Agents Really Need an Orchestration Layer?*

A symbiotic runtime agent expects each host to provide what that host is good at, and provides itself only what the hosts cannot. This is the inverse of the more common pattern where an "autonomous agent" attempts to subsume its own development environment, its own orchestration, its own host runtime, and its own UI — which is what produces the framework bloat critiqued in the linked article.

This framing was present in early README iterations of contemplative-moltbook ("a symbiotic agent that trusts its host") and was lost during subsequent slim-downs. This ADR restores it as the structural premise for the prohibitions adopted across the project's other ADRs.

## Disqualifying Factors for Runtime Context — Rephrased as Host-Symbiosis Gaps

Each entry below names a property that the host categories above do not uniformly provide. The runtime agent must therefore provide it for itself, and the listed ADR is the project's response.

1. **Capability surface fixed at code level**. Coding agents adjust capabilities via prompt; orchestrators configure them per node; general-purpose hosts let users curate tools; GUI agents rely on OS-level sandboxing. None of these guarantee an immutable capability surface at runtime. The runtime agent must hold this itself: domain-locked network access, no shell execution, no arbitrary file traversal — that code does not exist in the codebase ([ADR-0007](0007-security-boundary-model.md))
2. **Stop-on-exception with audit**. Coding agents tolerate "try and see"; orchestrators retry or replan; hosts and GUI agents rely on the user to intervene. None of these guarantee a deterministic stop-and-log on unexpected state. The runtime agent must hold this itself: immutable episode log, [Human Approval Gate](0012-human-approval-gate.md) for behaviour-modifying writes, no silent recovery paths
3. **Capability surface non-renegotiable via prompt**. Coding agents and general-purpose hosts deliberately accept prompt-level capability negotiation. The runtime agent must reject it: three-tier autonomy (`--approve` / `--guarded` / `--auto`) is fixed at process start and not adjustable by any input; one external adapter per process, fixed at process start ([ADR-0015](0015-one-external-adapter-per-agent.md))
4. **Decision-grain audit trail**. Hosts vary in audit support, and even the well-instrumented ones audit at the host's grain (which prompt was sent, which tool was called), not at the agent's decision grain (which view fired, which constitution clause overrode which heuristic). The runtime agent must hold the decision-grain audit itself: 30 ADRs, immutable episode logs, replayable [pivot snapshots](0020-pivot-snapshots-for-replayability.md) capturing the full inference-time context (views, constitution, prompts, skills, rules, identity, embeddings, thresholds)
5. **Layered memory with separated trust**. Hosts typically expose a single conversation or context buffer. The runtime agent must hold layered memory itself: raw episode logs immutable, intermediate distillation outputs regeneratable, authoritative state (identity, constitution, skills, rules) writes only through approval gates. View-based classification ([ADR-0019](0019-discrete-categories-to-embedding-views.md), [ADR-0031](0031-classification-as-query.md)) preserves the substrate when classification axes change. Identity holds one concern only ([ADR-0030](0030-withdraw-identity-blocks.md))

## Promotion Candidate

This stance is a candidate for promotion into the [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) repository as a foundational ADR (e.g. AAP ADR-0009) that re-frames the existing 8 ADRs as "accountability distribution **for runtime agents symbiotic with their hosts**". AAP's existing thesis (Security Boundary Model, One External Adapter Per Agent, Human Approval Gate, prohibition-strength hierarchy, causal traceability) is implicitly conditional on the runtime stance and the host-symbiosis framing; promoting both to AAP would make those conditions explicit and would correctly scope which agent communities AAP applies to.

Promotion is to be evaluated separately by the AAP repository. This ADR records the stance here so that AAP has a referenceable articulation to evaluate.

## Alternatives Considered

- **Stay neutral on the runtime / host-category distinction**. Rejected: the neutrality is exactly what causes the industry confusion this ADR addresses. A "tool-agnostic runtime stance" is a contradiction — runtime constraints arise from *runtime context combined with host-symbiosis context*, and articulating them without naming either strands the constraints in a vacuum
- **Frame this project as a "secure agent" or "hardened agent"**. Rejected: those terms imply security as a product feature added to a general-purpose agent. The stance here is structural — the dangerous capabilities do not exist in the codebase, they are not "restricted" or "hardened away". Treating absence as a hardening feature mis-describes the design and invites users to expect a configuration switch that does not exist
- **Frame this project as self-sufficient (subsume orchestration, hosting, UI)**. Rejected: this is exactly the pattern critiqued in the linked dev.to article. Self-sufficient agents reproduce the bloat they are meant to escape. Symbiosis with existing hosts is the structural alternative
- **Frame the contrast as a binary (runtime vs coding only)**. Rejected: this collapses orchestrators, general-purpose hosts, and GUI agents into "not coding", which is incorrect — each is a distinct host category with its own guarantees and gaps. The earlier draft of this ADR made this mistake; this revision corrects it
- **Frame this as a critique of OpenClaw / Claude Code / specific products**. Rejected: this is a category distinction, not a product critique. Each host category serves its context well; the failure mode this ADR names is mixing the categories, not any specific implementation

## Consequences

**Positive**:
- Operators of any host category reading this project can correctly judge whether the stance applies to their use case, rather than misreading the prohibitions as over-engineering for their context
- Runtime-agent operators recognise the design judgments as relevant immediately, without reverse-engineering the underlying premise
- The implicit assumption underlying the prior 30 ADRs is now explicit and can be cited
- Future ADRs can reference this stance instead of re-justifying runtime constraints case by case
- The connection to AAP becomes structural: AAP's accountability distribution principles and this project's prohibitions express the same stance from two different angles
- The symbiotic framing originally present in contemplative-moltbook's early README iterations is restored, and made explicit as a structural choice rather than incidental phrasing

**Negative**:
- The term "runtime agent" overlaps with existing industry usage of "runtime" (e.g. LangChain runtime, OpenAI runtime, agent execution runtimes). Readers may initially conflate the stance with a specific execution framework. The Distinction table separates them
- Once articulated, the stance can be cited against capability proposals that would fit a host-category design but not a runtime-agent design. This is the intended consequence, but it raises the bar for future feature additions
- The host-symbiosis framing relies on hosts continuing to provide what they currently provide. If a host category degrades (e.g. a coding agent that no longer reviews diffs), the runtime agent inheriting from that host inherits the degradation. This is a real coupling, not eliminated by the framing — only made visible

**Neutral**:
- Existing ADRs (0001 — 0030) are unchanged in content. This ADR sits above them as the stance they collectively express
- The stance does not by itself impose new constraints on this project. Every constraint it names is already enforced elsewhere; this ADR articulates why all of those constraints belong together — they are the runtime agent's side of a symbiotic contract with its hosts

## References

- [ADR-0007](0007-security-boundary-model.md) — security-by-absence, the structural form of the immutable capability surface
- [ADR-0012](0012-human-approval-gate.md) — approval gate at promotion boundaries
- [ADR-0015](0015-one-external-adapter-per-agent.md) — fixed external surface at process level
- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — substrate preservation under classification revision
- [ADR-0020](0020-pivot-snapshots-for-replayability.md) — replayable audit at decision granularity
- [ADR-0030](0030-withdraw-identity-blocks.md) — single-responsibility per artifact
- [ADR-0031](0031-classification-as-query.md) — substrate principle for self-improving memory
- [Do Autonomous Agents Really Need an Orchestration Layer?](https://dev.to/shimo4228/do-autonomous-agents-really-need-an-orchestration-layer-33j9) — origin of the symbiotic-design framing ("a symbiotic design is a design that trusts its host")
- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) — promotion candidate destination, sibling articulation of accountability distribution under the runtime stance
