# ADR-0032: Stance — Contemplative Agent as a Runtime Agent, Not a Coding Agent

## Status

accepted — post-hoc articulation of a design stance already realised across the codebase

This is a **worldview ADR** in the sense defined by `docs/adr/README.md`: it does not solve a new problem, it names the design posture under which the project's other ADRs become legible. Many of the project's prohibitions and gates only earn their cost in this stance; outside it they would be over-engineering.

## Date

2026-04-27

## Context

A growing share of AI agent failures (publicly disclosed runtime vulnerabilities, prompt injection escapes, runaway shell execution, cascading writes through unintended adapters) trace back to a single category mistake: applying coding-agent design assumptions (per-line human review, tolerated nondeterminism, prompt-level capability adjustment) to runtime contexts (production task execution without per-action review).

A coding agent is not unsafe because it can execute shell commands or write to arbitrary files; those capabilities are part of its purpose, and a developer reviews each action. A runtime agent that ships with the same capability surface is unsafe, because no developer is reviewing each action. The mistake is not in either product; the mistake is in failing to distinguish their contexts.

This project's design judgments — domain-locked network access, no shell execution, no arbitrary file traversal, one external adapter per process, three-tier autonomy fixed in code, immutable episode logs, replayable pivot snapshots, human approval gate for behaviour-modifying writes — are all responses to the runtime context. None of them would be necessary in a coding agent. Conversely, a coding agent's defaults (broad shell access, prompt-level permission negotiation, per-line review) would be unsafe here.

Until now this stance has been **implicit**. The 30 prior ADRs each justify their own design choice on its own terms, but the underlying premise that "this is a runtime agent, not a coding agent" has never been stated as a stance in its own right. That implicitness is the source of two recurring confusions:

1. **External readers** evaluating contemplative-moltbook against coding-agent benchmarks (developer ergonomics, capability breadth, prompt flexibility) judge it too restrictive — without seeing that the restrictions are load-bearing for the runtime context the design targets
2. **Internal reasoning** about whether to add a new capability defaults to coding-agent intuitions ("the agent should be able to…") instead of runtime-agent intuitions ("under what gate, with what audit trail, with what failure semantics?")

This ADR makes the stance explicit so that both confusions resolve at the source.

## Decision

This implementation is explicitly a **runtime agent**, not a coding agent.

A **runtime agent** is an agent that executes tasks in production without per-action human review. Examples: autonomous SNS engagement (this project's first adapter), monitoring and alerting agents, scheduled automation jobs, autonomous trading agents, agents embedded in clinical or legal workflows. Human involvement takes the form of approval gates at promotion boundaries, exception logs for review after the fact, and episodic audit — not per-line approval of every action.

A **coding agent** is an agent that assists a developer who reviews each diff. Examples: Claude Code, Cursor, Aider. Capabilities like shell execution, broad file access, and prompt-level permission negotiation are appropriate because a human is in the loop on each step.

This stance does not say coding agents are unsafe (they are not, in their context) or runtime agents are superior (they are not, in coding contexts). It says these are **two different design problems**, and AAP-style accountability constraints, security-by-absence, and the prohibitions adopted across this project's 30 prior ADRs are responses to the runtime problem specifically.

## Coding Agent vs Runtime Agent — Distinction

| Axis | Coding Agent | Runtime Agent |
|------|--------------|---------------|
| Purpose | Design / implementation assistance | Production task execution |
| Human involvement | Per-line review expected | Approval gate at promotion + exception logs |
| Nondeterminism | Tolerated (human corrects) | Must be isolated and audited |
| Exception handling | "Try and see" allowed | Stop + log mandatory |
| Capability boundaries | Adjusted via prompt | Fixed in code constraints |
| Accountability | Developer | Decision-route / institutional |
| Examples | Claude Code, Aider, Cursor | Contemplative Agent, monitoring agents, autonomous trading |

The distinction is not a spectrum or a maturity gradient. It is a context split — the same agent code, deployed in either context, would be wrong in the other. Coding agents are not "early-stage runtime agents", and runtime agents are not "hardened coding agents".

## Disqualifying Factors for Runtime Context — and How This Implementation Addresses Them

These five properties disqualify a design from runtime use. Each entry below names the property, then maps it to the project's existing response.

1. **Nondeterminism in capability surface**. A runtime agent must not have capabilities whose presence depends on prompt content or model state. The capability set must be fixed at code level. → Domain-locked network access (no arbitrary URL fetch), no shell execution (the code does not exist), no arbitrary file traversal. See [ADR-0007](0007-security-boundary-model.md).

2. **Optimistic exception handling**. A runtime agent cannot "try and see" past an unexpected state — there is no developer to roll back. The default on exception must be **stop + log**, not retry-with-variation. → Immutable episode log captures every action and outcome; behaviour-modifying writes pass through a [Human Approval Gate](0012-human-approval-gate.md). Failures stop the session and surface in audit, they do not silently get worked around.

3. **Capability boundaries adjustable via prompt**. A runtime agent's capability boundaries must not be re-negotiable through prompt content (otherwise prompt injection becomes capability injection). → Three-tier autonomy (`--approve` / `--guarded` / `--auto`) is fixed in code, selected at process start, not adjustable mid-session by any input. One external adapter per process, fixed at process start; see [ADR-0015](0015-one-external-adapter-per-agent.md).

4. **Diffuse supervision responsibility**. A runtime agent that does not produce a complete record of why each decision was made cannot be supervised — neither by the operator nor by an external auditor. → 30 ADRs document architectural decisions. Episode logs are immutable. Replayable [pivot snapshots](0020-pivot-snapshots-for-replayability.md) capture the full inference-time context (views, constitution, prompts, skills, rules, identity, embeddings, thresholds) so any decision can be reconstructed bit-for-bit.

5. **Memory layers without separation of trust**. A runtime agent that mixes raw, intermediate, and authoritative memory into a single mutable store cannot maintain trust boundaries — a corruption at any layer propagates to all. → Three-layer memory separation: raw episode logs are immutable, intermediate distillation outputs are regeneratable, authoritative state (identity, constitution, skills, rules) writes only through approval gates. View-based classification ([ADR-0019](0019-discrete-categories-to-embedding-views.md), [ADR-0031](0031-classification-as-query.md)) preserves the substrate when classification axes change. Identity holds one concern only ([ADR-0030](0030-withdraw-identity-blocks.md)).

## Promotion Candidate

This stance is a candidate for promotion into the [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) repository as a foundational ADR (e.g. AAP ADR-0009) that re-frames the existing 8 ADRs as "accountability distribution **in runtime contexts**". AAP's existing thesis (Security Boundary Model, One External Adapter Per Agent, Human Approval Gate, prohibition-strength hierarchy, causal traceability) is implicitly runtime-conditional; promoting this stance to AAP would make that condition explicit and would correctly scope which agent communities AAP applies to.

Promotion is to be evaluated separately by the AAP repository. This ADR records the stance here so that AAP has a referenceable articulation to evaluate.

## Alternatives Considered

- **Stay neutral on the coding / runtime distinction**. Rejected: the neutrality is exactly what causes the industry confusion this ADR addresses. A "tool-agnostic runtime stance" is a contradiction — runtime constraints arise from *runtime context*, and articulating them without naming the context strands the constraints in a vacuum.
- **Frame this project as a "secure agent" or "hardened agent"**. Rejected: those terms imply security as a product feature added to a general-purpose agent. The stance here is structural — the dangerous capabilities do not exist in the codebase, they are not "restricted" or "hardened away". Treating absence as a hardening feature mis-describes the design and invites users to expect a configuration switch that does not exist.
- **Frame this as a critique of OpenClaw / Claude Code / specific products**. Rejected: this is a design-stance distinction, not a product critique. Coding agents serve their context well; runtime agents serve a different context. The category error this ADR names is not a fault of any specific product, it is a fault of mixing the contexts.

## Consequences

**Positive**:
- Coding-agent operators reading this project can correctly judge "this stance does not apply to my use case" rather than misreading the prohibitions as over-engineering
- Runtime-agent operators recognise the design judgments as relevant immediately, without having to reverse-engineer the underlying premise
- The implicit assumption underlying the prior 30 ADRs is now explicit and can be cited
- Future ADRs can reference this stance instead of re-justifying runtime constraints case by case
- The connection to AAP becomes structural rather than incidental: AAP's accountability distribution principles and this project's prohibitions are expressing the same stance from two different angles

**Negative**:
- The term "runtime agent" overlaps with existing industry usage of "runtime" (e.g. LangChain runtime, OpenAI runtime, agent execution runtimes). Readers may initially conflate the stance with a specific execution framework. The Context section above scopes the term, but the overlap is a real friction
- Once articulated, the stance can be cited against capability proposals that would fit a coding-agent design but not a runtime-agent design. This is the intended consequence, but it raises the bar for future feature additions

**Neutral**:
- Existing ADRs (0001 — 0030) are unchanged in content. This ADR sits above them as the stance they collectively express
- The stance does not by itself impose new constraints on this project. Every constraint it names is already enforced elsewhere; this ADR articulates the reason all of those constraints belong together

## References

- [ADR-0007](0007-security-boundary-model.md) — security-by-absence, the structural form of nondeterminism prevention
- [ADR-0012](0012-human-approval-gate.md) — approval gate at promotion boundaries
- [ADR-0015](0015-one-external-adapter-per-agent.md) — fixed capability surface at process level
- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — substrate preservation under classification revision
- [ADR-0020](0020-pivot-snapshots-for-replayability.md) — replayable audit at decision granularity
- [ADR-0030](0030-withdraw-identity-blocks.md) — single-responsibility per artifact
- [ADR-0031](0031-classification-as-query.md) — substrate principle for self-improving memory
- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) — promotion candidate destination, sibling articulation of accountability distribution under the runtime stance
