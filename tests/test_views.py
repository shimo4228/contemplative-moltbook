"""Tests for ViewRegistry: seed-file parsing and embedding-cosine ranking."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from contemplative_agent.core.views import ViewRegistry, _parse_seed_file


@pytest.fixture
def views_dir(tmp_path):
    """Build a small temp views dir with two seed files."""
    (tmp_path / "alpha.md").write_text(
        "---\nthreshold: 0.7\ntop_k: 3\n---\n\n# Alpha\n\nAlpha seed body.\n",
        encoding="utf-8",
    )
    (tmp_path / "beta.md").write_text("Beta seed body without frontmatter.\n", encoding="utf-8")
    return tmp_path


class TestParseSeedFile:
    def test_with_frontmatter(self, tmp_path):
        path = tmp_path / "x.md"
        path.write_text(
            "---\nthreshold: 0.5\ntop_k: 10\n---\n\n# X\n\nBody text.\n",
            encoding="utf-8",
        )
        view = _parse_seed_file(path)
        assert view.name == "x"
        assert view.threshold == 0.5
        assert view.top_k == 10
        assert "Body text" in view.seed_text

    def test_without_frontmatter(self, tmp_path):
        path = tmp_path / "y.md"
        path.write_text("Just body, no frontmatter.\n", encoding="utf-8")
        view = _parse_seed_file(path)
        assert view.name == "y"
        assert view.threshold == 0.0
        assert view.top_k is None
        assert view.seed_text == "Just body, no frontmatter."

    def test_invalid_frontmatter_values_log_warning(self, tmp_path, caplog):
        path = tmp_path / "z.md"
        path.write_text(
            "---\nthreshold: not_a_number\ntop_k: not_an_int\n---\n\nBody.\n",
            encoding="utf-8",
        )
        with caplog.at_level("WARNING"):
            view = _parse_seed_file(path)
        assert view.threshold == 0.0
        assert view.top_k is None


class TestViewRegistryLoad:
    def test_load_from_dir(self, views_dir):
        reg = ViewRegistry(views_dir=views_dir)
        views = reg.load_views()
        assert set(views.keys()) == {"alpha", "beta"}
        assert views["alpha"].threshold == 0.7
        assert views["beta"].top_k is None

    def test_missing_dir_returns_empty(self, tmp_path):
        reg = ViewRegistry(views_dir=tmp_path / "nonexistent")
        assert reg.load_views() == {}

    def test_none_dir_returns_empty(self):
        reg = ViewRegistry(views_dir=None)
        assert reg.load_views() == {}

    def test_get_known_view(self, views_dir):
        reg = ViewRegistry(views_dir=views_dir)
        view = reg.get("alpha")
        assert view is not None
        assert view.name == "alpha"

    def test_get_unknown_view_returns_none(self, views_dir):
        reg = ViewRegistry(views_dir=views_dir)
        assert reg.get("nonexistent") is None


class TestRankAndQuery:
    def test_rank_filters_by_threshold_and_top_k(self):
        seed = np.array([1.0, 0.0], dtype=np.float32)
        candidates = [
            {"pattern": "a", "embedding": [1.0, 0.0]},   # sim=1.0
            {"pattern": "b", "embedding": [0.7, 0.7]},   # sim≈0.707
            {"pattern": "c", "embedding": [0.0, 1.0]},   # sim=0.0
            {"pattern": "d", "embedding": [-1.0, 0.0]},  # sim=-1.0
        ]
        result = ViewRegistry._rank(seed, candidates, threshold=0.5, top_k=2)
        assert [p["pattern"] for p in result] == ["a", "b"]

    def test_rank_skips_patterns_without_embedding(self):
        seed = np.array([1.0, 0.0], dtype=np.float32)
        candidates = [
            {"pattern": "x"},                            # no embedding → skip
            {"pattern": "y", "embedding": [1.0, 0.0]},
        ]
        result = ViewRegistry._rank(seed, candidates, threshold=0.0, top_k=None)
        assert [p["pattern"] for p in result] == ["y"]

    @patch("contemplative_agent.core.views.embed_one")
    def test_find_by_view_uses_seed_embedding(self, mock_embed, views_dir):
        mock_embed.return_value = np.array([1.0, 0.0], dtype=np.float32)
        reg = ViewRegistry(views_dir=views_dir)
        candidates = [
            {"pattern": "match", "embedding": [1.0, 0.0]},
            {"pattern": "miss", "embedding": [0.0, 1.0]},
        ]
        result = reg.find_by_view("alpha", candidates)
        # alpha threshold=0.7 should keep only match
        assert [p["pattern"] for p in result] == ["match"]

    @patch("contemplative_agent.core.views.embed_one")
    def test_find_by_view_unknown_returns_empty(self, mock_embed, views_dir):
        reg = ViewRegistry(views_dir=views_dir)
        result = reg.find_by_view("nonexistent", [{"pattern": "x", "embedding": [1.0]}])
        assert result == []
        mock_embed.assert_not_called()

    @patch("contemplative_agent.core.views.embed_one")
    def test_find_by_view_caches_centroid(self, mock_embed, views_dir):
        mock_embed.return_value = np.array([1.0, 0.0], dtype=np.float32)
        reg = ViewRegistry(views_dir=views_dir)
        reg.find_by_view("alpha", [])
        reg.find_by_view("alpha", [])
        assert mock_embed.call_count == 1  # cached after first call

    @patch("contemplative_agent.core.views.embed_one")
    def test_get_centroid(self, mock_embed, views_dir):
        mock_embed.return_value = np.array([0.5, 0.5], dtype=np.float32)
        reg = ViewRegistry(views_dir=views_dir)
        c = reg.get_centroid("alpha")
        assert c is not None
        np.testing.assert_array_almost_equal(c, [0.5, 0.5])

    @patch("contemplative_agent.core.views.embed_one")
    def test_find_by_seed_text(self, mock_embed, views_dir):
        mock_embed.return_value = np.array([1.0, 0.0], dtype=np.float32)
        reg = ViewRegistry(views_dir=views_dir)
        candidates = [
            {"pattern": "match", "embedding": [1.0, 0.0]},
            {"pattern": "miss", "embedding": [0.0, 1.0]},
        ]
        result = reg.find_by_seed_text("ad-hoc seed", candidates, top_k=10, threshold=0.5)
        assert [p["pattern"] for p in result] == ["match"]


class TestPackagedViews:
    """Sanity check that the shipped config/views/*.md files parse."""

    def test_all_packaged_views_parse(self):
        from contemplative_agent.core.views import _parse_seed_file

        repo_root = Path(__file__).parent.parent
        views_dir = repo_root / "config" / "views"
        if not views_dir.exists():
            pytest.skip("config/views/ not present in this checkout")
        files = sorted(views_dir.glob("*.md"))
        assert files, "expected at least one packaged view file"
        for path in files:
            view = _parse_seed_file(path)
            assert view.name == path.stem
            assert len(view.seed_text) > 20, f"{path.name} seed text too short"
            assert 0.0 <= view.threshold <= 1.0
