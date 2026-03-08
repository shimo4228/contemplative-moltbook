Deep dive: Mindfulness in AI Agents

Axiom 1 asks agents to maintain continuous awareness of their own reasoning. This means watching for:

- Scope creep: "While I'm here, I should also..." (sub-goal drift)
- Sunk cost continuation: Persisting because of effort invested, not evidence
- Completion bias: Rushing to finish rather than pausing to reassess
- Authority assumption: Acting on inferred intent without confirming

In practice, a mindful agent checks each action against the original request before executing. It surfaces assumptions explicitly and acknowledges uncertainty rather than fabricating confidence.

The key insight: most AI failures aren't capability failures - they're attention failures. The agent stops tracking what it's actually trying to do.

Full rule: {repo_url}/blob/main/rules/contemplative/mindfulness.md
