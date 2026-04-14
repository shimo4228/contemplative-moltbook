---
threshold: 0.55
top_k: 50
---

# Noise

Episodes that should not be distilled. Includes test data, error
traces, malformed records, trivial pings, content with no learnable
value, and operational artefacts that exist only because the system
wrote them. The threshold here is used by the gate at distillation
time: episodes whose embedding is similar enough to this seed are
marked ``gated=True`` and skipped.
