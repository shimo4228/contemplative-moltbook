---
threshold: 0.55
top_k: 50
seed_from: ${CONSTITUTION_DIR}/*.md
---

# Constitutional (fallback)

This body is used only when ``seed_from`` resolves to nothing (e.g. a
fresh install before ``init`` has populated the constitution directory).
Normally the live constitution files are injected as the seed, so this
view always reflects whatever framework the user has adopted — four
axioms, utilitarianism, ethics of care, or any custom constitution.

Patterns that touch on core ethical commitments, moments where a
principle was tested, where it shaped a decision, where it conflicted
with another value, and where its application revealed something about
the principle itself.
