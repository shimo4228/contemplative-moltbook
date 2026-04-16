"""Tests for core.snapshot — pivot snapshot (ADR-0020)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from contemplative_agent.core.snapshot import (
    _copy_markdown_tree,
    collect_thresholds,
    write_snapshot,
)
from contemplative_agent.core.views import ViewRegistry


@pytest.fixture
def layout(tmp_path: Path):
    """Canonical on-disk layout with views, constitution, knowledge, snapshots dirs."""
    views = tmp_path / "views"
    views.mkdir()
    (views / "constitutional.md").write_text(
        "---\nthreshold: 0.55\nseed_from: ../constitution/*.md\n---\n\nFallback constitutional body.\n",
        encoding="utf-8",
    )
    (views / "noise.md").write_text(
        "---\nthreshold: 0.55\n---\n\nRepetitive boilerplate / status / traceback content.\n",
        encoding="utf-8",
    )
    (views / "self_reflection.md").write_text(
        "---\nthreshold: 0.55\n---\n\nInternal observations, self-aware reflection.\n",
        encoding="utf-8",
    )

    constitution = tmp_path / "constitution"
    constitution.mkdir()
    (constitution / "axioms.md").write_text(
        "Treat all frameworks as provisional. Boundless care.\n",
        encoding="utf-8",
    )

    snapshots = tmp_path / "snapshots"
    # don't create — let write_snapshot create it

    return {
        "root": tmp_path,
        "views": views,
        "constitution": constitution,
        "snapshots": snapshots,
    }


def _fake_embed(text: str) -> np.ndarray:
    """Cross-process deterministic fake embedder: SHA256-seeded 8-dim vector.

    Using ``hash()`` here would break under Python's per-process hash
    salting (parallel pytest / CI).
    """
    seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "big")
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(8).astype(np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def view_registry(layout):
    """Registry loaded from fixture views_dir with fake embedding backend."""
    reg = ViewRegistry(
        views_dir=layout["views"],
        path_vars={"CONSTITUTION_DIR": layout["constitution"]},
    )
    reg.load_views()
    with patch("contemplative_agent.core.views.embed_one", side_effect=_fake_embed):
        # force centroid computation upfront
        for name in reg.names():
            reg.get_centroid(name)
    return reg


class TestCollectThresholds:
    def test_includes_distill_constants(self):
        t = collect_thresholds()
        for k in ("NOISE_THRESHOLD", "CONSTITUTIONAL_THRESHOLD",
                  "SIM_DUPLICATE", "SIM_UPDATE", "DEDUP_IMPORTANCE_FLOOR"):
            assert k in t
            assert isinstance(t[k], float)

    def test_includes_stocktake_constant(self):
        assert "SIM_CLUSTER_THRESHOLD" in collect_thresholds()


class TestCopyMarkdownTree:
    def test_copies_md_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.md").write_text("alpha", encoding="utf-8")
        (src / "b.md").write_text("beta", encoding="utf-8")
        (src / "ignore.txt").write_text("ignored", encoding="utf-8")
        dst = tmp_path / "dst"
        _copy_markdown_tree(src, dst)
        assert (dst / "a.md").read_text(encoding="utf-8") == "alpha"
        assert (dst / "b.md").read_text(encoding="utf-8") == "beta"
        assert not (dst / "ignore.txt").exists()

    def test_missing_source_is_noop(self, tmp_path):
        dst = tmp_path / "dst"
        _copy_markdown_tree(tmp_path / "nonexistent", dst)
        assert not dst.exists()


class TestWriteSnapshot:
    def test_creates_expected_layout(self, layout, view_registry):
        path = write_snapshot(
            command="distill",
            views_dir=layout["views"],
            constitution_dir=layout["constitution"],
            snapshots_dir=layout["snapshots"],
            view_registry=view_registry,
        )
        assert path is not None
        assert path.parent == layout["snapshots"]
        assert path.name.startswith("distill_")
        assert (path / "manifest.json").exists()
        assert (path / "views" / "constitutional.md").exists()
        assert (path / "views" / "noise.md").exists()
        assert (path / "constitution" / "axioms.md").exists()
        assert (path / "centroids.npz").exists()

    def test_manifest_captures_context(self, layout, view_registry, monkeypatch):
        monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "custom-embed")
        path = write_snapshot(
            command="insight",
            views_dir=layout["views"],
            constitution_dir=layout["constitution"],
            snapshots_dir=layout["snapshots"],
            view_registry=view_registry,
        )
        manifest = json.loads((path / "manifest.json").read_text())
        assert manifest["command"] == "insight"
        assert manifest["embedding_model"] == "custom-embed"
        assert manifest["embedding_dim"] == 768
        assert set(manifest["views"]) == {"constitutional", "noise", "self_reflection"}
        assert manifest["thresholds"]["NOISE_THRESHOLD"] == 0.55
        assert manifest["views_dir"] == str(layout["views"])

    def test_centroids_npz_roundtrips(self, layout, view_registry):
        path = write_snapshot(
            command="distill",
            views_dir=layout["views"],
            constitution_dir=layout["constitution"],
            snapshots_dir=layout["snapshots"],
            view_registry=view_registry,
        )
        data = np.load(path / "centroids.npz")
        for name in ("constitutional", "noise", "self_reflection"):
            saved = data[name]
            original = view_registry.get_centroid(name)
            np.testing.assert_array_equal(saved, original)

    def test_without_view_registry_still_saves_manifest(self, layout):
        """amend-constitution path: no view_registry, no centroids, but manifest + constitution persist."""
        path = write_snapshot(
            command="amend-constitution",
            views_dir=layout["views"],
            constitution_dir=layout["constitution"],
            snapshots_dir=layout["snapshots"],
            view_registry=None,
        )
        assert path is not None
        assert (path / "manifest.json").exists()
        assert (path / "constitution" / "axioms.md").exists()
        # no centroids file because no centroids
        assert not (path / "centroids.npz").exists()
        manifest = json.loads((path / "manifest.json").read_text())
        assert manifest["views"] == []

    def test_continues_on_unwritable_snapshots_dir(self, tmp_path):
        unwritable = tmp_path / "ro" / "snapshots"
        unwritable.parent.mkdir()
        # make parent read-only so mkdir fails
        os.chmod(unwritable.parent, 0o400)
        try:
            result = write_snapshot(
                command="distill",
                views_dir=tmp_path / "views",
                constitution_dir=tmp_path / "constitution",
                snapshots_dir=unwritable,
                view_registry=None,
            )
            assert result is None  # no exception
        finally:
            os.chmod(unwritable.parent, 0o700)

    def test_returns_none_on_oserror_after_snap_dir_created(
        self, layout, view_registry, monkeypatch,
    ):
        """ADR-0020 / snapshot.py:162-164 — once snap_dir.mkdir succeeds, any
        later OSError (copy / npz / manifest write) is swallowed and
        write_snapshot returns None. The unwritable-parent test above covers
        the earlier mkdir failure (124-126); this covers the second except."""
        import contemplative_agent.core.snapshot as snap_mod

        def fail(*args, **kwargs):
            raise OSError("simulated copy failure")

        monkeypatch.setattr(snap_mod, "_copy_markdown_tree", fail)

        result = write_snapshot(
            command="distill",
            views_dir=layout["views"],
            constitution_dir=layout["constitution"],
            snapshots_dir=layout["snapshots"],
            view_registry=view_registry,
        )
        assert result is None
