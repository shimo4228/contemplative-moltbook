"""Pivot snapshot — persist interpretive context at behavior-producing commands.

ADR-0020: the lens that produced a given ``identity.md`` / ``skills/*.md`` /
``rules/*.md`` artifact is the combination of views + constitution +
thresholds + embedding model + centroids. Without snapshots, any of those
changing retroactively makes the resulting artifact's provenance opaque.

This module writes a snapshot directory for each run and (optionally)
updates per-pattern telemetry (`last_classified_at`, `last_view_matches`)
on the knowledge store. Telemetry is read-only observational data — no
behavioural logic reads these fields.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

import numpy as np

from .embeddings import EMBEDDING_DIM, _get_embedding_model, cosine
from .knowledge_store import KnowledgeStore
from .views import ViewRegistry

logger = logging.getLogger(__name__)

SnapshotCommand = Literal[
    "distill",
    "distill-identity",
    "insight",
    "rules-distill",
    "amend-constitution",
]

_COMPACT_TS_FORMAT = "%Y%m%dT%H%M%S%fZ"


def _format_ts_pair(now: datetime) -> Tuple[str, str]:
    """Return (compact, iso) forms derived from a single ``datetime``.

    Deriving both forms from one instant prevents microsecond drift
    between the snapshot dir name and the manifest ``ts`` field.
    Microsecond precision on the compact form makes same-second runs
    (rare in production, universal in tests) collision-free.
    """
    compact = now.strftime(_COMPACT_TS_FORMAT)
    iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    return compact, iso


def collect_thresholds() -> Dict[str, float]:
    """Gather all classification/similarity thresholds that shape a run.

    Late imports avoid circular import through ViewRegistry consumers.
    Add new thresholds here when introducing them so they appear in
    snapshots — this file is the canonical registry for the "lens".
    """
    from . import distill as _d
    from . import stocktake as _s

    return {
        "NOISE_THRESHOLD": _d.NOISE_THRESHOLD,
        "CONSTITUTIONAL_THRESHOLD": _d.CONSTITUTIONAL_THRESHOLD,
        "SIM_DUPLICATE": _d.SIM_DUPLICATE,
        "SIM_UPDATE": _d.SIM_UPDATE,
        "DEDUP_IMPORTANCE_FLOOR": _d.DEDUP_IMPORTANCE_FLOOR,
        "SIM_CLUSTER_THRESHOLD": _s.SIM_CLUSTER_THRESHOLD,
    }


def _copy_markdown_tree(src: Path, dst: Path) -> None:
    """Copy ``*.md`` files from src to dst (flat, no recursion into subdirs)."""
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for md in sorted(src.glob("*.md")):
        shutil.copy2(md, dst / md.name)


def _score_patterns(
    patterns: List[dict],
    centroids: Dict[str, np.ndarray],
) -> List[Optional[Dict[str, float]]]:
    """Cosine-score each pattern's embedding against every view centroid.

    Returns a list aligned with ``patterns`` — entries are ``None`` for
    patterns lacking an ``embedding`` field.
    """
    results: List[Optional[Dict[str, float]]] = []
    for p in patterns:
        emb = p.get("embedding")
        if not emb:
            results.append(None)
            continue
        vec = np.asarray(emb, dtype=np.float32)
        scores = {name: float(cosine(vec, centroid)) for name, centroid in centroids.items()}
        results.append(scores)
    return results


def write_snapshot(
    *,
    command: SnapshotCommand,
    views_dir: Path,
    constitution_dir: Path,
    snapshots_dir: Path,
    view_registry: Optional[ViewRegistry] = None,
    knowledge_store: Optional[KnowledgeStore] = None,
) -> Optional[Path]:
    """Write a pivot snapshot for the given command.

    Returns the snapshot directory on success, ``None`` on any failure.
    Snapshots are observability — callers must not rely on snapshot
    success for correctness.
    """
    ts_compact, ts_iso = _format_ts_pair(datetime.now(timezone.utc))
    try:
        snap_dir = snapshots_dir / f"{command}_{ts_compact}"
        snap_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        logger.warning("Snapshot dir creation failed: %s", exc)
        return None

    try:
        _copy_markdown_tree(views_dir, snap_dir / "views")
        _copy_markdown_tree(constitution_dir, snap_dir / "constitution")

        centroids: Dict[str, np.ndarray] = {}
        view_names: List[str] = []
        if view_registry is not None:
            view_names = view_registry.names()
            for name in view_names:
                c = view_registry.get_centroid(name)
                if c is not None:
                    centroids[name] = c
        if centroids:
            np.savez(snap_dir / "centroids.npz", **centroids)

        manifest = {
            "command": command,
            "ts": ts_iso,
            "embedding_model": _get_embedding_model(),
            "embedding_dim": EMBEDDING_DIM,
            "thresholds": collect_thresholds(),
            "views": view_names,
            "views_dir": str(views_dir),
            "constitution_dir": str(constitution_dir),
        }
        (snap_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        if knowledge_store is not None and centroids:
            _apply_pattern_telemetry(knowledge_store, centroids, ts_iso)

        return snap_dir
    except OSError as exc:
        logger.warning("Snapshot write failed under %s: %s", snap_dir, exc)
        return None


def _apply_pattern_telemetry(
    knowledge_store: KnowledgeStore,
    centroids: Dict[str, np.ndarray],
    timestamp: str,
) -> int:
    """Score all patterns against centroids and persist via KnowledgeStore."""
    scores_per_pattern = _score_patterns(knowledge_store.get_raw_patterns(), centroids)
    try:
        return knowledge_store.update_view_telemetry(scores_per_pattern, timestamp)
    except OSError as exc:
        logger.warning("Pattern telemetry save failed: %s", exc)
        return 0
