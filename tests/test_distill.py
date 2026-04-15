"""Tests for sleep-time memory distillation (ADR-0009 embedding-based)."""

import json
import logging
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from contemplative_agent.core.distill import (
    summarize_record,
    distill,
    distill_identity,
    enrich,
    IdentityResult,
    _is_valid_pattern,
    _parse_importance_scores,
    _classify_episodes,
    _ClassifiedRecords,
    _dedup_patterns,
    SIM_DUPLICATE,
    SIM_UPDATE,
)
from contemplative_agent.core.knowledge_store import effective_importance
from contemplative_agent.core.memory import EpisodeLog, KnowledgeStore


def _make_log(tmp_path):
    """Helper: create EpisodeLog with one interaction."""
    log = EpisodeLog(log_dir=tmp_path / "logs")
    log.append("interaction", {
        "direction": "sent", "agent_name": "Alice",
        "content_summary": "Hello", "agent_id": "a1",
    })
    return log


def _embedding(*values):
    """Helper: build a 1D float32 array."""
    return np.array(values, dtype=np.float32)


@pytest.fixture
def mock_embed_distinct():
    """Patch embed_texts to return (n, 4) distinct one-hot-ish vectors."""
    def _mk(texts):
        # Distinct, low-similarity vectors so dedup doesn't trigger
        n = len(texts)
        return np.array(
            [[1.0 if i == j else 0.0 for j in range(max(n, 4))] for i in range(n)],
            dtype=np.float32,
        )

    with patch("contemplative_agent.core.distill.embed_texts", side_effect=_mk) as m:
        yield m


class TestDistill:
    """Pipeline: classify → extract → refine → importance → embed → dedup → save."""

    @patch("contemplative_agent.core.distill.generate")
    def test_basic_distillation(self, mock_generate, mock_embed_distinct, tmp_path):
        # classify is now embedding-based (no generate call); only extract / refine / importance.
        mock_generate.side_effect = [
            "Some free-form analysis of patterns from the episode logs.",
            json.dumps({"patterns": [
                "Pattern one shows that quoting specific details improves engagement",
                "Pattern two reveals that generic replies stall conversations quickly",
            ]}),
            json.dumps({"scores": [8, 6]}),
        ]

        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {
            "direction": "sent", "agent_name": "Alice",
            "content_summary": "Hello", "agent_id": "a1",
        })
        log.append("activity", {"action": "comment", "post_id": "p1"})

        ks = KnowledgeStore(path=tmp_path / "knowledge.json")

        result = distill(days=1, episode_log=log, knowledge_store=ks)
        assert "Pattern one" in result
        assert "Pattern two" in result

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        patterns = ks2.get_learned_patterns()
        assert any("Pattern one" in p for p in patterns)
        assert any("Pattern two" in p for p in patterns)
        # Importance from Step 3
        p1 = [p for p in ks2._learned_patterns if "Pattern one" in p["pattern"]][0]
        assert p1["importance"] == 0.8  # 8/10
        # Embedding stored
        assert isinstance(p1["embedding"], list)

    @patch("contemplative_agent.core.distill.generate")
    def test_dry_run_does_not_write(self, mock_generate, mock_embed_distinct, tmp_path):
        mock_generate.side_effect = [
            "Some analysis.",
            json.dumps({"patterns": [
                "Dry pattern that explains how quoting specific details works better",
            ]}),
            json.dumps({"scores": [5]}),
        ]
        log = _make_log(tmp_path)
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")

        result = distill(days=1, dry_run=True, episode_log=log, knowledge_store=ks)
        assert "Dry pattern" in result
        assert not (tmp_path / "knowledge.json").exists()

    def test_empty_episodes(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        result = distill(days=1, episode_log=log, knowledge_store=ks)
        assert "No episodes" in result

    @patch("contemplative_agent.core.distill.generate", return_value=None)
    def test_llm_failure(self, mock_generate, tmp_path):
        log = _make_log(tmp_path)
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        result = distill(days=1, episode_log=log, knowledge_store=ks)
        assert result == ""
        assert not (tmp_path / "knowledge.json").exists()


class TestEnrichNoOp:
    def test_enrich_returns_zero(self):
        ks = KnowledgeStore()
        assert enrich(ks) == 0


class TestParseImportanceScores:
    def test_json_format(self):
        assert _parse_importance_scores('{"scores": [8, 5]}', 2) == [0.8, 0.5]

    def test_count_mismatch_returns_defaults(self):
        assert _parse_importance_scores('{"scores": [8]}', 2) == [0.5, 0.5]

    def test_invalid_json_falls_back_to_csv(self):
        assert _parse_importance_scores("8, 5, 9", 3) == [0.8, 0.5, 0.9]

    def test_clamps_out_of_range(self):
        assert _parse_importance_scores('{"scores": [15, -2]}', 2) == [1.0, 0.1]


class TestDedupPatternsEmbedding:
    """ADR-0009: cosine-based dedup."""

    def test_distinct_patterns_all_added(self):
        new_patterns = ["A new pattern", "Another distinct pattern"]
        new_imps = [0.7, 0.5]
        new_embs = [_embedding(1, 0, 0), _embedding(0, 1, 0)]
        existing = []
        add, add_imp, add_emb, skip, upd = _dedup_patterns(
            new_patterns, new_imps, new_embs, existing,
        )
        assert len(add) == 2
        assert skip == 0
        assert upd == 0

    def test_near_duplicate_skipped(self):
        existing = [{"pattern": "Existing", "importance": 0.6, "embedding": [1.0, 0.0, 0.0]}]
        new_patterns = ["Almost same"]
        new_imps = [0.5]
        # Same direction, slight scale → cosine ≈ 1.0
        new_embs = [_embedding(0.99, 0.01, 0.0)]
        add, add_imp, add_emb, skip, upd = _dedup_patterns(
            new_patterns, new_imps, new_embs, existing,
        )
        assert len(add) == 0
        assert skip == 1

    def test_similar_triggers_update(self):
        """ADR-0021: UPDATE path soft-invalidates old pattern and ADDs a new
        boosted one; the old pattern keeps its original importance but gains
        a ``valid_until`` timestamp for audit / replay."""
        existing = [{"pattern": "Existing", "importance": 0.5, "embedding": [1.0, 0.0]}]
        # cosine ≈ 0.85 (between SIM_UPDATE=0.80 and SIM_DUPLICATE=0.92)
        new_embs = [_embedding(0.85, 0.527)]
        add, add_imp, add_emb, skip, upd = _dedup_patterns(
            ["new"], [0.7], new_embs, existing,
        )
        assert upd == 1
        assert existing[0]["importance"] == 0.5  # not mutated
        assert existing[0].get("valid_until") is not None  # soft-invalidated
        assert len(add) == 1
        assert add_imp[0] == 0.7  # boosted importance on the new pattern

    def test_existing_without_embedding_ignored(self):
        existing = [{"pattern": "Old", "importance": 0.5}]  # no embedding
        new_embs = [_embedding(1.0, 0.0)]
        add, add_imp, add_emb, skip, upd = _dedup_patterns(
            ["new"], [0.5], new_embs, existing,
        )
        # Should ADD since existing has no embedding to compare against
        assert len(add) == 1

    def test_new_without_embedding_always_added(self):
        existing = [{"pattern": "Old", "importance": 0.5, "embedding": [1.0, 0.0]}]
        add, add_imp, add_emb, skip, upd = _dedup_patterns(
            ["new"], [0.5], [None], existing,
        )
        assert len(add) == 1
        assert add_emb == [None]

    def test_mutate_existing_false_does_not_modify(self):
        existing = [{"pattern": "Old", "importance": 0.5, "embedding": [1.0, 0.0]}]
        new_embs = [_embedding(0.85, 0.527)]
        _dedup_patterns(
            ["new"], [0.9], new_embs, existing,
            mutate_existing=False,
        )
        assert existing[0]["importance"] == 0.5
        assert existing[0].get("valid_until") is None  # no soft-invalidation either

    def test_thresholds_in_range(self):
        assert 0.0 < SIM_UPDATE < SIM_DUPLICATE < 1.0


class TestDeriveSourceTypeADR0021:
    """ADR-0021: map episode types to provenance.source_type."""

    def test_all_self_generated_is_self_reflection(self):
        from contemplative_agent.core.distill import _derive_source_type

        records = [
            {"type": "post", "data": {}},
            {"type": "insight", "data": {}},
            {"type": "interaction", "data": {"direction": "sent"}},
            {"type": "activity", "data": {}},
        ]
        assert _derive_source_type(records) == "self_reflection"

    def test_all_external_is_external_reply(self):
        from contemplative_agent.core.distill import _derive_source_type

        records = [{"type": "interaction", "data": {"direction": "received"}}] * 3
        assert _derive_source_type(records) == "external_reply"

    def test_mixed_self_and_external(self):
        from contemplative_agent.core.distill import _derive_source_type

        records = [
            {"type": "post", "data": {}},
            {"type": "interaction", "data": {"direction": "received"}},
        ]
        assert _derive_source_type(records) == "mixed"

    def test_only_unknown_types(self):
        from contemplative_agent.core.distill import _derive_source_type

        records = [{"type": "something_weird", "data": {}}]
        assert _derive_source_type(records) == "unknown"

    def test_trust_for_source_maps_correctly(self):
        from contemplative_agent.core.distill import _trust_for_source

        assert _trust_for_source("self_reflection") > _trust_for_source("external_reply")
        assert _trust_for_source("mixed") <= _trust_for_source("external_reply")
        assert _trust_for_source("unknown") == 0.6


class TestDedupSoftInvalidationADR0021:
    """ADR-0021: SIM_UPDATE path creates a new row + invalidates the old row."""

    def test_invalidated_patterns_ignored_as_candidates(self):
        existing = [
            {
                "pattern": "ghost",
                "importance": 0.8,
                "embedding": [1.0, 0.0],
                "valid_until": "2026-01-01T00:00",
            }
        ]
        new_embs = [_embedding(0.85, 0.527)]  # would match if ghost were live
        add, add_imp, add_emb, skip, upd = _dedup_patterns(
            ["new"], [0.7], new_embs, existing,
        )
        # ghost is invalidated → ignored → new pattern is ADD'd, not UPDATE
        assert upd == 0
        assert len(add) == 1

    def test_return_indices_aligns_with_input(self):
        existing: list = []
        new_embs = [_embedding(1.0, 0.0), _embedding(0.0, 1.0)]
        out = _dedup_patterns(
            ["a", "b"], [0.5, 0.5], new_embs, existing,
            return_indices=True,
        )
        add, _imp, _emb, idxs, _skip, _upd = out
        assert add == ["a", "b"]
        assert idxs == [0, 1]


class TestIsValidPattern:
    def test_too_short(self):
        assert not _is_valid_pattern("short")

    def test_too_few_words(self):
        assert not _is_valid_pattern("OneTwoThree FourFiveSix")

    def test_valid_pattern(self):
        assert _is_valid_pattern("This is a valid pattern with enough words and length")


class TestSummarizeRecord:
    def test_interaction(self):
        s = summarize_record("interaction", {
            "direction": "sent", "agent_name": "Bob", "content_summary": "Hi"
        })
        assert "sent with Bob" in s
        assert "Hi" in s

    def test_post(self):
        s = summarize_record("post", {"title": "My Post"})
        assert "posted: My Post" in s

    def test_insight(self):
        s = summarize_record("insight", {"observation": "Something happened"})
        assert "Something happened" in s

    def test_unknown_returns_empty(self):
        assert summarize_record("weird_type", {}) == ""


class TestDistillIdentity:
    def test_no_view_registry(self):
        ks = KnowledgeStore()
        result = distill_identity(knowledge_store=ks)
        assert "ViewRegistry" in str(result)

    def test_no_self_reflection_patterns(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Some pattern", embedding=[0.1, 0.2])
        ks.save()

        registry = MagicMock()
        registry.find_by_view.return_value = []  # no matches
        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        result = distill_identity(knowledge_store=ks2, view_registry=registry)
        assert "No self-reflection" in result

    @patch("contemplative_agent.core.distill.generate")
    def test_full_path(self, mock_generate, tmp_path):
        mock_generate.side_effect = ["raw analysis", "refined identity"]
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Self-reflection pattern about meta-cognition",
                                embedding=[0.1, 0.2])
        ks.save()

        registry = MagicMock()
        registry.find_by_view.return_value = [
            {"pattern": "Self-reflection pattern about meta-cognition",
             "importance": 0.7}
        ]
        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        result = distill_identity(knowledge_store=ks2, view_registry=registry,
                                   identity_path=tmp_path / "identity.md")
        assert isinstance(result, IdentityResult)
        assert "refined identity" in result.text


class TestClassifyEpisodes:
    @patch("contemplative_agent.core.distill.embed_texts")
    def test_classifies_via_centroid(self, mock_embed):
        mock_embed.return_value = np.array([[1.0, 0.0]], dtype=np.float32)
        registry = MagicMock()
        # noise centroid different (sim < threshold), constitutional centroid matching
        registry.get_centroid.side_effect = lambda name: (
            np.array([0.0, 1.0], dtype=np.float32) if name == "noise"
            else np.array([1.0, 0.0], dtype=np.float32)  # constitutional matches
        )
        records = [{"ts": "2026-04-15T07:00:00Z", "type": "insight",
                    "data": {"observation": "Notice empty"}}]
        result = _classify_episodes(records, view_registry=registry)
        assert isinstance(result, _ClassifiedRecords)
        assert len(result.constitutional) == 1
        assert len(result.noise) == 0

    @patch("contemplative_agent.core.distill.embed_texts")
    def test_noise_gate_takes_precedence(self, mock_embed):
        mock_embed.return_value = np.array([[1.0, 0.0]], dtype=np.float32)
        registry = MagicMock()
        # both noise and constitutional centroids match; noise wins
        registry.get_centroid.return_value = np.array([1.0, 0.0], dtype=np.float32)
        records = [{"ts": "2026-04-15T07:00:00Z", "type": "insight",
                    "data": {"observation": "x"}}]
        result = _classify_episodes(records, view_registry=registry)
        assert len(result.noise) == 1

    def test_no_view_registry_defaults_to_uncategorized(self):
        records = [{"ts": "2026-04-15T07:00:00Z", "type": "insight",
                    "data": {"observation": "x"}}]
        result = _classify_episodes(records, view_registry=None)
        assert len(result.uncategorized) == 1
        assert len(result.noise) == 0

    def test_empty_records(self):
        assert _classify_episodes([], view_registry=None).uncategorized == ()


class TestKnowledgeStore:
    def test_get_context_string_no_subcategory_param(self):
        """ADR-0009: subcategory parameter has been removed."""
        ks = KnowledgeStore()
        ks.add_learned_pattern("a")
        # Should not accept subcategory keyword
        with pytest.raises(TypeError):
            ks.get_context_string(subcategory="x")  # type: ignore[call-arg]


class TestThresholds:
    """Embedding thresholds are sane defaults."""

    def test_dedup_thresholds_in_range(self):
        from contemplative_agent.core.distill import (
            NOISE_THRESHOLD,
            CONSTITUTIONAL_THRESHOLD,
        )
        assert 0.0 < NOISE_THRESHOLD < 1.0
        assert 0.0 < CONSTITUTIONAL_THRESHOLD < 1.0


class TestEffectiveImportance:
    def test_zero_for_unknown_distilled(self):
        p = {"importance": 0.8, "distilled": "unknown"}
        assert effective_importance(p) < 0.1

    def test_recent_keeps_value(self):
        from datetime import datetime, timezone
        p = {"importance": 0.7, "distilled": datetime.now(timezone.utc).isoformat()}
        assert 0.6 < effective_importance(p) <= 0.7


