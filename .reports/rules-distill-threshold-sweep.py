#!/usr/bin/env python3
"""Threshold calibration sweep for CLUSTER_THRESHOLD_RULES (Issue 5).

Reads ~/.config/moltbook/skills/*.md, embeds bodies, and reports:

1. Pairwise cosine distribution (P25 / P50 / P75 / P90)
2. Cluster count + size distribution for thresholds {0.55, 0.60, 0.65, 0.70, 0.75}
   with the same parameters as `_build_skill_clusters` (min_size=3, max_size=10)

Run with: uv run python .reports/rules-distill-threshold-sweep.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "src"))

from contemplative_agent.core.clustering import cluster_patterns  # noqa: E402
from contemplative_agent.core.embeddings import embed_texts  # noqa: E402
from contemplative_agent.core.rules_distill import (  # noqa: E402
    MAX_RULES_BATCH,
    MIN_SKILLS_REQUIRED,
    _read_skills,
)

SKILLS_DIR = Path("~/.config/moltbook/skills").expanduser()
THRESHOLDS = [0.55, 0.60, 0.65, 0.70, 0.75]


def cosine_matrix(embs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = embs / norms
    return unit @ unit.T


def percentiles(values: np.ndarray) -> dict:
    return {
        "P25": float(np.percentile(values, 25)),
        "P50": float(np.percentile(values, 50)),
        "P75": float(np.percentile(values, 75)),
        "P90": float(np.percentile(values, 90)),
        "min": float(values.min()),
        "max": float(values.max()),
        "mean": float(values.mean()),
    }


def main() -> int:
    skills = _read_skills(SKILLS_DIR)
    print(f"Skills loaded: {len(skills)} from {SKILLS_DIR}")
    if len(skills) < 2:
        print("Need at least 2 skills to compute pairwise cosine.")
        return 1

    matrix = embed_texts(skills)
    if matrix is None:
        print("embed_texts returned None — Ollama unreachable?")
        return 1
    print(f"Embedding matrix shape: {matrix.shape}")

    sim = cosine_matrix(matrix)
    iu = np.triu_indices(sim.shape[0], k=1)
    pairs = sim[iu]
    print(f"\nPairwise cosine distribution ({len(pairs)} pairs):")
    for k, v in percentiles(pairs).items():
        print(f"  {k}: {v:.4f}")

    print("\nCluster count + size distribution per threshold")
    print(f"  (min_size={MIN_SKILLS_REQUIRED}, max_size={MAX_RULES_BATCH})")
    print(f"  {'threshold':>10}  {'clusters':>8}  {'singletons':>10}  sizes")
    dicts = [
        {
            "pattern": text,
            "embedding": matrix[i].tolist(),
            "importance": 0.5,
            "trust_score": 1.0,
        }
        for i, text in enumerate(skills)
    ]
    for t in THRESHOLDS:
        clusters, singletons = cluster_patterns(
            dicts,
            threshold=t,
            min_size=MIN_SKILLS_REQUIRED,
            max_size=MAX_RULES_BATCH,
        )
        sizes = [len(c) for c in clusters]
        print(
            f"  {t:>10.2f}  {len(clusters):>8}  {len(singletons):>10}  {sizes}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
