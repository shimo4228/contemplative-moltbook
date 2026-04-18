"""Tests for ADR-0022 memory evolution (IV-4)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pytest

from contemplative_agent.core.memory_evolution import (
    EVOLUTION_K,
    EVOLUTION_MAX_EXCL,
    EVOLUTION_MIN,
    NO_CHANGE_MARKER,
    EvolutionPair,
    EvolutionResult,
    _parse_revision,
    apply_revision,
    evolve_patterns,
    find_neighbors,
    revise_neighbor,
)


def _emb(*xs: float) -> np.ndarray:
    v = np.asarray(xs, dtype=np.float32)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def _make_pattern(text: str, emb: np.ndarray, **over: object) -> Dict:
    base: Dict = {
        "pattern": text,
        "distilled": f"distilled: {text}",
        "importance": 0.6,
        "category": "uncategorized",
        "embedding": [float(x) for x in emb],
        "gated": False,
        "trust_score": 0.8,
        "valid_until": None,
        "valid_from": "2026-04-10T00:00",
        "provenance": {"source_type": "self_reflection"},
    }
    base.update(over)
    return base


class TestFindNeighbors:
    def test_picks_only_patterns_in_evolution_band(self):
        new_emb = _emb(1.0, 0.0)
        # Below band: orthogonal → sim 0
        # In band: ~0.75
        # Above band: 0.92
        live = [
            _make_pattern("orthogonal", _emb(0.0, 1.0)),
            _make_pattern("related", _emb(0.75, 0.66)),  # sim ~0.75
            _make_pattern("near-dup", _emb(0.95, 0.31)),  # sim ~0.95
        ]
        pairs = find_neighbors("new observation text", new_emb, live)
        assert len(pairs) == 1
        assert pairs[0].neighbor["pattern"] == "related"
        assert EVOLUTION_MIN <= pairs[0].similarity < EVOLUTION_MAX_EXCL

    def test_honours_k_cap(self):
        new_emb = _emb(1.0, 0.0)
        live = [
            _make_pattern(f"n{i}", _emb(0.70 + i * 0.01, (1 - (0.70 + i * 0.01) ** 2) ** 0.5))
            for i in range(5)
        ]
        pairs = find_neighbors("x", new_emb, live, k=2)
        assert len(pairs) == 2
        assert pairs[0].similarity >= pairs[1].similarity

    def test_skips_patterns_without_embedding(self):
        new_emb = _emb(1.0, 0.0)
        live = [
            _make_pattern("no emb", _emb(0.75, 0.66), embedding=None),
            {"pattern": "no emb key", "distilled": "x"},
        ]
        assert find_neighbors("x", new_emb, live) == []


class TestParseRevision:
    def test_no_change_marker_returns_none(self):
        assert _parse_revision("NO_CHANGE") is None
        assert _parse_revision("  NO_CHANGE  ") is None
        assert _parse_revision('"NO_CHANGE"') is None
        assert _parse_revision("NO_CHANGE.") is None

    def test_empty_returns_none(self):
        assert _parse_revision("") is None
        assert _parse_revision(None) is None
        assert _parse_revision("   \n\n  ") is None

    def test_too_short_returns_none(self):
        assert _parse_revision("yep") is None

    def test_valid_revision_returned_stripped(self):
        text = "  The original observation is sharper when viewed alongside the new one.  "
        assert _parse_revision(text) == text.strip()


class TestReviseNeighbor:
    def test_calls_generate_with_formatted_prompt(self):
        captured = {}

        def fake_generate(prompt: str, **kw) -> str:
            captured["prompt"] = prompt
            captured["kw"] = kw
            return "A revised reading of the original observation, now contextualised."

        neighbor = _make_pattern("old", _emb(0.75, 0.66))
        pair = EvolutionPair(
            new_text="new arrival",
            new_emb=_emb(1.0, 0.0),
            neighbor=neighbor,
            similarity=0.75,
        )
        template = "Past: {neighbor}\nNew: {new_pattern}\nRevised:"
        result = revise_neighbor(pair, template, generate_fn=fake_generate)
        assert "Past: distilled: old" in captured["prompt"]
        assert "New: new arrival" in captured["prompt"]
        assert result.revised_distilled is not None
        assert result.neighbor is neighbor

    def test_no_change_marker_produces_none(self):
        def fake_generate(prompt, **kw) -> str:
            return "NO_CHANGE"

        pair = EvolutionPair(
            new_text="x",
            new_emb=_emb(1.0, 0.0),
            neighbor=_make_pattern("old", _emb(0.75, 0.66)),
            similarity=0.75,
        )
        result = revise_neighbor(pair, "{neighbor}{new_pattern}", generate_fn=fake_generate)
        assert result.revised_distilled is None


class TestApplyRevision:
    def test_invalidates_old_and_builds_new_row(self):
        neighbor = _make_pattern("old", _emb(0.75, 0.66), importance=0.7)
        result = EvolutionResult(
            neighbor=neighbor,
            revised_distilled="Revised interpretation in light of new evidence.",
            similarity=0.75,
        )
        now = datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc)
        outcome = apply_revision(result, now=now)
        assert outcome is not None
        invalidated, new_row = outcome
        # Original neighbor is untouched (immutability)
        assert neighbor["valid_until"] is None
        # Invalidated copy carries the new timestamp
        assert invalidated["valid_until"] == "2026-04-16T12:00+00:00"
        assert invalidated["pattern"] == neighbor["pattern"]
        # New row mirrors identity, not meta
        assert new_row["pattern"] == neighbor["pattern"]
        assert new_row["embedding"] == neighbor["embedding"]
        assert new_row["importance"] == neighbor["importance"]
        assert new_row["distilled"] == "Revised interpretation in light of new evidence."
        assert new_row["valid_until"] is None
        assert new_row["valid_from"] == "2026-04-16T12:00+00:00"
        # ADR-0028: access_count / last_accessed_at no longer written
        assert "access_count" not in new_row
        assert "last_accessed_at" not in new_row
        # Provenance bumped to mixed, preserves history
        assert new_row["provenance"]["source_type"] == "mixed"
        assert new_row["provenance"]["evolution_similarity"] == 0.75
        assert new_row["provenance"]["derived_from"] == "unknown" or new_row["provenance"]["derived_from"]

    def test_none_result_returns_none(self):
        neighbor = _make_pattern("old", _emb(1.0, 0.0))
        result = EvolutionResult(neighbor=neighbor, revised_distilled=None, similarity=0.75)
        assert apply_revision(result) is None
        # Also does not touch neighbor
        assert neighbor["valid_until"] is None


class TestEvolvePatterns:
    def test_full_path_end_to_end(self):
        def fake_generate(prompt, **kw) -> str:
            return "Revised combined interpretation, faithful to both observations."

        new_emb = _emb(1.0, 0.0)
        neighbor = _make_pattern("neighbor pattern", _emb(0.75, 0.66))
        unrelated = _make_pattern("unrelated", _emb(0.0, 1.0))
        live = [neighbor, unrelated]

        batch = evolve_patterns(
            [("new pattern text", new_emb)], live,
            prompt_template="{neighbor}|{new_pattern}",
            generate_fn=fake_generate,
        )
        assert len(batch.revised_rows) == 1
        assert len(batch.invalidations) == 1
        old_ref, invalidated = batch.invalidations[0]
        assert old_ref is neighbor
        assert invalidated["valid_until"] is not None
        # Original still untouched
        assert neighbor["valid_until"] is None
        assert unrelated["valid_until"] is None
        assert batch.revised_rows[0]["distilled"].startswith("Revised")

    def test_no_prompt_template_is_no_op(self):
        new_emb = _emb(1.0, 0.0)
        neighbor = _make_pattern("x", _emb(0.75, 0.66))
        batch = evolve_patterns(
            [("t", new_emb)], [neighbor], prompt_template="",
        )
        assert batch.invalidations == ()
        assert batch.revised_rows == ()
        assert neighbor["valid_until"] is None

    def test_neighbor_only_revised_once_per_call(self):
        """If two new patterns both target the same neighbor, only the first wins."""
        calls = []

        def fake_generate(prompt, **kw) -> str:
            calls.append(prompt)
            return "Revised text, enough length to pass parse."

        neighbor = _make_pattern("shared neighbor", _emb(0.75, 0.66))
        new_a = _emb(1.0, 0.0)
        new_b = _emb(0.98, 0.2)  # also in band w.r.t. neighbor
        batch = evolve_patterns(
            [("a", new_a), ("b", new_b)], [neighbor],
            prompt_template="{neighbor}|{new_pattern}",
            generate_fn=fake_generate,
        )
        assert len(batch.revised_rows) == 1
        assert len(calls) == 1  # neighbor only asked about once

    def test_empty_inputs_return_empty(self):
        empty_a = evolve_patterns([], [], "x")
        assert empty_a.invalidations == () and empty_a.revised_rows == ()
        empty_b = evolve_patterns([("t", _emb(1.0, 0.0))], [], "x")
        assert empty_b.invalidations == () and empty_b.revised_rows == ()

    def test_already_invalidated_neighbor_is_skipped(self):
        """ADR-0022 / memory_evolution.py:250-252 — neighbors that already
        carry ``valid_until`` must not be re-revised. Otherwise the
        bitemporal chain branches and data silently corrupts."""
        fake_gen_calls = []

        def fake_generate(prompt, **kw) -> str:
            fake_gen_calls.append(prompt)
            return "Revised interpretation that should never be produced."

        new_emb = _emb(1.0, 0.0)
        already_invalid = _make_pattern(
            "previously invalidated neighbor", _emb(0.75, 0.66),
            valid_until="2026-03-01T00:00:00+00:00",
        )
        batch = evolve_patterns(
            [("new pattern text", new_emb)], [already_invalid],
            prompt_template="{neighbor}|{new_pattern}",
            generate_fn=fake_generate,
        )
        assert batch.invalidations == ()
        assert batch.revised_rows == ()
        assert fake_gen_calls == []  # LLM never invoked

    def test_revise_none_output_is_skipped(self):
        """ADR-0022 / memory_evolution.py:254-256 — when the LLM (or parse)
        returns ``revised_distilled=None``, the neighbor is skipped without
        crashing or half-writing an invalidation row."""
        def fake_generate(prompt, **kw) -> str:
            return ""  # parse treats empty as None → result.revised_distilled = None

        new_emb = _emb(1.0, 0.0)
        neighbor = _make_pattern("neighbor pattern", _emb(0.75, 0.66))
        batch = evolve_patterns(
            [("new pattern text", new_emb)], [neighbor],
            prompt_template="{neighbor}|{new_pattern}",
            generate_fn=fake_generate,
        )
        assert batch.invalidations == ()
        assert batch.revised_rows == ()
        # Original untouched
        assert neighbor.get("valid_until") is None


class TestHybridRankBM25:
    """ADR-0022 IV-5: hybrid cosine+BM25 scoring in ViewRegistry._rank."""

    def test_bm25_raises_patterns_with_literal_term_match(self):
        from contemplative_agent.core.views import (
            ViewRegistry,
            _compute_bm25_scores,
        )

        # Both patterns equally similar to seed in embedding space, but only
        # one contains the literal word "axiom" in its text.
        candidates = [
            {
                "pattern": "pattern about the axiom of emptiness in practice",
                "distilled": "axiom observation",
                "embedding": [1.0, 0.0, 0.0, 0.0],
                "trust_score": 1.0, "importance": 0.5,
                "valid_until": None,
            },
            {
                "pattern": "pattern about a quite different topic entirely",
                "distilled": "topic observation",
                "embedding": [1.0, 0.0, 0.0, 0.0],
                "trust_score": 1.0, "importance": 0.5,
                "valid_until": None,
            },
            # Extra rows so BM25 has enough corpus to produce non-zero IDF
            {
                "pattern": "third unrelated pattern for corpus size", "distilled": "z",
                "embedding": [0.0, 1.0, 0.0, 0.0],
                "trust_score": 1.0, "importance": 0.5,
                "valid_until": None,
            },
            {
                "pattern": "fourth unrelated pattern for corpus size", "distilled": "w",
                "embedding": [0.0, 0.0, 1.0, 0.0],
                "trust_score": 1.0, "importance": 0.5,
                "valid_until": None,
            },
        ]
        seed_text = "axiom"
        seed_emb = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        scores = _compute_bm25_scores(seed_text, candidates)
        result = ViewRegistry._rank(
            seed_emb, candidates, threshold=0.0, top_k=None,
            bm25_scores=scores, alpha=0.5, beta=0.5,
        )
        # The "axiom"-bearing pattern should lead
        assert result[0]["distilled"] == "axiom observation"

    def test_no_bm25_falls_back_to_cosine_only(self):
        from contemplative_agent.core.views import ViewRegistry

        candidates = [
            {
                "pattern": "a", "distilled": "a",
                "embedding": [0.8, 0.6], "trust_score": 1.0, "access_count": 0,
                "importance": 0.5, "valid_until": None,
            },
            {
                "pattern": "b", "distilled": "b",
                "embedding": [1.0, 0.0], "trust_score": 1.0, "access_count": 0,
                "importance": 0.5, "valid_until": None,
            },
        ]
        seed = np.array([1.0, 0.0], dtype=np.float32)
        result = ViewRegistry._rank(
            seed, candidates, threshold=0.0, top_k=None,
            bm25_scores=None, alpha=1.0, beta=0.0,
        )
        assert result[0]["pattern"] == "b"  # higher cosine

    def test_bm25_weight_zero_is_cosine_only_even_with_scores(self):
        from contemplative_agent.core.views import ViewRegistry

        cand_a = {
            "pattern": "axiom axiom axiom", "distilled": "axiom",
            "embedding": [0.1, 0.99], "trust_score": 1.0, "access_count": 0,
            "importance": 0.5, "valid_until": None,
        }
        cand_b = {
            "pattern": "different topic", "distilled": "topic",
            "embedding": [1.0, 0.0], "trust_score": 1.0, "access_count": 0,
            "importance": 0.5, "valid_until": None,
        }
        candidates = [cand_a, cand_b]
        seed = np.array([1.0, 0.0], dtype=np.float32)
        # beta=0 → BM25 not applied even though scores provided
        scores = {id(cand_a): 1.0, id(cand_b): 0.0}
        result = ViewRegistry._rank(
            seed, candidates, threshold=0.0, top_k=None,
            bm25_scores=scores, alpha=1.0, beta=0.0,
        )
        assert result[0]["pattern"] == "different topic"

    def test_empty_query_returns_no_bm25_signal(self):
        from contemplative_agent.core.views import _compute_bm25_scores
        assert _compute_bm25_scores("", [{"pattern": "x", "distilled": "y"}]) == {}


class TestViewBm25Weight:
    def test_frontmatter_parses_bm25_weight(self, tmp_path):
        from contemplative_agent.core.views import _parse_seed_file

        p = tmp_path / "v.md"
        p.write_text(
            "---\nthreshold: 0.5\nbm25_weight: 0.4\n---\nseed body text",
            encoding="utf-8",
        )
        view = _parse_seed_file(p)
        assert view.bm25_weight == pytest.approx(0.4)
        assert view.threshold == pytest.approx(0.5)

    def test_invalid_bm25_weight_logs_and_keeps_default(self, tmp_path, caplog):
        from contemplative_agent.core.views import (
            HYBRID_BETA_DEFAULT,
            _parse_seed_file,
        )

        p = tmp_path / "v.md"
        p.write_text("---\nbm25_weight: nope\n---\nbody", encoding="utf-8")
        view = _parse_seed_file(p)
        assert view.bm25_weight == HYBRID_BETA_DEFAULT

    def test_default_bm25_weight_when_frontmatter_omits_it(self, tmp_path):
        from contemplative_agent.core.views import (
            HYBRID_BETA_DEFAULT,
            _parse_seed_file,
        )

        p = tmp_path / "v.md"
        p.write_text("just a seed body\n", encoding="utf-8")
        view = _parse_seed_file(p)
        assert view.bm25_weight == HYBRID_BETA_DEFAULT
