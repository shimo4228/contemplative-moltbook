"""Tests for ADR-0009 migration logic (embed-backfill)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from contemplative_agent.core.episode_embeddings import (
    EpisodeEmbeddingStore,
    episode_id_for,
)
from contemplative_agent.core.knowledge_store import KnowledgeStore
from contemplative_agent.core.migration import (
    DEFAULT_NOISE_THRESHOLD,
    backfill_episode_embeddings,
    backfill_pattern_embeddings,
    backup_knowledge,
    run_embed_backfill,
)
from contemplative_agent.core.views import ViewRegistry


@pytest.fixture
def views_dir(tmp_path):
    """Minimal views dir with a noise seed (centroid for gating)."""
    d = tmp_path / "views"
    d.mkdir()
    (d / "noise.md").write_text(
        "---\nthreshold: 0.55\n---\n\nTest data, errors, trivial pings.\n",
        encoding="utf-8",
    )
    return d


@pytest.fixture
def knowledge_path(tmp_path):
    return tmp_path / "knowledge.json"


@pytest.fixture
def populated_knowledge(knowledge_path):
    """Knowledge file with 3 patterns, none embedded."""
    data = [
        {"pattern": "Pattern about reasoning under uncertainty",
         "importance": 0.7, "category": "uncategorized", "distilled": "2026-04-15T07:00"},
        {"pattern": "trivial test ping", "importance": 0.3,
         "category": "noise", "distilled": "2026-04-15T07:01"},
        {"pattern": "Pattern about engagement and dialogue",
         "importance": 0.5, "category": "uncategorized", "distilled": "2026-04-15T07:02"},
    ]
    knowledge_path.write_text(json.dumps(data) + "\n", encoding="utf-8")
    return knowledge_path


class TestBackupKnowledge:
    def test_creates_backup(self, populated_knowledge):
        backup = backup_knowledge(populated_knowledge)
        assert backup is not None
        assert backup.exists()
        assert backup.name.startswith("knowledge.json.bak.")
        assert backup.read_text(encoding="utf-8") == populated_knowledge.read_text(encoding="utf-8")

    def test_returns_none_when_source_missing(self, tmp_path):
        assert backup_knowledge(tmp_path / "nonexistent.json") is None


class TestBackfillPatternEmbeddings:
    @patch("contemplative_agent.core.migration.embed_texts")
    @patch("contemplative_agent.core.views.embed_one")
    def test_adds_embedding_and_gated(self, mock_embed_one, mock_embed_texts,
                                       populated_knowledge, views_dir):
        # Noise centroid embedding
        mock_embed_one.return_value = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        # 3 patterns embedded — 1st reasoning (similar), 2nd noise (very similar), 3rd engagement (orthogonal)
        mock_embed_texts.return_value = np.array([
            [0.0, 1.0, 0.0],   # not noise
            [0.95, 0.31, 0.0], # very close to noise centroid (sim ≈ 0.95)
            [0.0, 0.0, 1.0],   # not noise
        ], dtype=np.float32)

        knowledge = KnowledgeStore(path=populated_knowledge)
        knowledge.load()
        registry = ViewRegistry(views_dir=views_dir)

        stats = backfill_pattern_embeddings(knowledge, registry)

        assert stats.patterns_total == 3
        assert stats.patterns_embedded == 3
        # gated: pattern 2 was already labeled "noise" (legacy), so pre-gated
        # plus pattern 2's embedding is similar to noise centroid
        assert stats.patterns_gated >= 1

        patterns = knowledge.get_raw_patterns()
        for p in patterns:
            assert isinstance(p["embedding"], list)
            assert len(p["embedding"]) == 3
            assert isinstance(p["gated"], bool)

    @patch("contemplative_agent.core.migration.embed_texts")
    @patch("contemplative_agent.core.views.embed_one")
    def test_skips_already_embedded(self, mock_embed_one, mock_embed_texts,
                                     knowledge_path, views_dir):
        data = [{
            "pattern": "Already embedded pattern",
            "importance": 0.6,
            "category": "uncategorized",
            "embedding": [0.1, 0.2, 0.3],
            "distilled": "2026-04-15T07:00",
        }]
        knowledge_path.write_text(json.dumps(data) + "\n", encoding="utf-8")

        mock_embed_one.return_value = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        mock_embed_texts.return_value = np.zeros((0, 3), dtype=np.float32)

        knowledge = KnowledgeStore(path=knowledge_path)
        knowledge.load()
        registry = ViewRegistry(views_dir=views_dir)

        stats = backfill_pattern_embeddings(knowledge, registry)
        assert stats.patterns_embedded == 0
        # gated still gets computed for already-embedded patterns
        assert isinstance(knowledge.get_raw_patterns()[0]["gated"], bool)

    @patch("contemplative_agent.core.migration.embed_texts")
    @patch("contemplative_agent.core.views.embed_one")
    def test_dry_run_does_not_mutate(self, mock_embed_one, mock_embed_texts,
                                      populated_knowledge, views_dir):
        mock_embed_one.return_value = np.array([1.0, 0.0], dtype=np.float32)
        mock_embed_texts.return_value = np.array([[0.0, 1.0]] * 3, dtype=np.float32)

        knowledge = KnowledgeStore(path=populated_knowledge)
        knowledge.load()
        registry = ViewRegistry(views_dir=views_dir)

        stats = backfill_pattern_embeddings(knowledge, registry, dry_run=True)
        # Counts reflect work, but patterns are not mutated
        assert stats.patterns_embedded == 3
        for p in knowledge.get_raw_patterns():
            assert p.get("embedding") is None or "embedding" not in p
            assert p.get("gated") is None or "gated" not in p

    @patch("contemplative_agent.core.views.embed_one")
    def test_missing_noise_centroid_records_error(self, mock_embed_one,
                                                   populated_knowledge, tmp_path):
        # No noise.md in this views dir
        empty_views = tmp_path / "empty_views"
        empty_views.mkdir()

        knowledge = KnowledgeStore(path=populated_knowledge)
        knowledge.load()
        registry = ViewRegistry(views_dir=empty_views)

        stats = backfill_pattern_embeddings(knowledge, registry)
        assert any("noise view centroid" in e for e in stats.errors)
        mock_embed_one.assert_not_called()


class TestBackfillEpisodeEmbeddings:
    @pytest.fixture
    def log_dir(self, tmp_path):
        d = tmp_path / "logs"
        d.mkdir()
        records = [
            {"ts": "2026-04-14T07:00:00Z", "type": "post",
             "data": {"title": "test post", "body": "hello world"}},
            {"ts": "2026-04-14T07:05:00Z", "type": "interaction",
             "data": {"direction": "received", "agent_name": "Alice",
                      "content_summary": "hello back"}},
        ]
        with (d / "2026-04-14.jsonl").open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        return d

    @patch("contemplative_agent.core.migration.embed_texts")
    def test_embeds_all_episodes(self, mock_embed, log_dir, tmp_path):
        mock_embed.return_value = np.array([
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ], dtype=np.float32)
        store = EpisodeEmbeddingStore(db_path=tmp_path / "embeddings.sqlite")

        stats = backfill_episode_embeddings(log_dir, store)
        assert stats.episodes_total == 2
        assert stats.episodes_embedded == 2
        assert store.count() == 2

    @patch("contemplative_agent.core.migration.embed_texts")
    def test_skips_already_present(self, mock_embed, log_dir, tmp_path):
        # Pre-populate sidecar with one of the records' id
        store = EpisodeEmbeddingStore(db_path=tmp_path / "embeddings.sqlite")
        first_record = {"ts": "2026-04-14T07:00:00Z", "type": "post",
                        "data": {"title": "test post", "body": "hello world"}}
        store.upsert(episode_id_for(first_record), first_record["ts"],
                     np.array([1.0], dtype=np.float32))

        mock_embed.return_value = np.array([[0.4, 0.5, 0.6]], dtype=np.float32)
        stats = backfill_episode_embeddings(log_dir, store)
        assert stats.episodes_total == 2
        assert stats.episodes_skipped == 1
        assert stats.episodes_embedded == 1

    @patch("contemplative_agent.core.migration.embed_texts")
    def test_dry_run_no_writes(self, mock_embed, log_dir, tmp_path):
        mock_embed.return_value = np.zeros((2, 3), dtype=np.float32)
        store = EpisodeEmbeddingStore(db_path=tmp_path / "embeddings.sqlite")

        stats = backfill_episode_embeddings(log_dir, store, dry_run=True)
        assert stats.episodes_embedded == 2
        assert store.count() == 0


class TestRunEmbedBackfill:
    @patch("contemplative_agent.core.migration.embed_texts")
    @patch("contemplative_agent.core.views.embed_one")
    def test_full_pipeline(self, mock_embed_one, mock_embed_texts,
                           populated_knowledge, views_dir, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        record = {"ts": "2026-04-15T07:00:00Z", "type": "insight",
                  "data": {"observation": "noticed something"}}
        (log_dir / "2026-04-15.jsonl").write_text(
            json.dumps(record) + "\n", encoding="utf-8"
        )

        mock_embed_one.return_value = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        mock_embed_texts.side_effect = [
            np.array([[0.0, 1.0, 0.0]] * 3, dtype=np.float32),  # patterns
            np.array([[0.0, 0.0, 1.0]], dtype=np.float32),       # episodes
        ]

        sqlite_path = tmp_path / "embeddings.sqlite"
        stats = run_embed_backfill(
            knowledge_path=populated_knowledge,
            log_dir=log_dir,
            sqlite_path=sqlite_path,
            views_dir=views_dir,
        )

        assert stats.backup_path is not None
        assert stats.backup_path.exists()
        assert stats.patterns_embedded == 3
        assert stats.episodes_embedded == 1
        assert sqlite_path.exists()

    @patch("contemplative_agent.core.migration.embed_texts")
    @patch("contemplative_agent.core.views.embed_one")
    def test_patterns_only_skips_episodes(self, mock_embed_one, mock_embed_texts,
                                           populated_knowledge, views_dir, tmp_path):
        log_dir = tmp_path / "logs"  # absent intentionally
        mock_embed_one.return_value = np.array([1.0, 0.0], dtype=np.float32)
        mock_embed_texts.return_value = np.array([[0.0, 1.0]] * 3, dtype=np.float32)

        sqlite_path = tmp_path / "embeddings.sqlite"
        stats = run_embed_backfill(
            knowledge_path=populated_knowledge,
            log_dir=log_dir,
            sqlite_path=sqlite_path,
            views_dir=views_dir,
            patterns_only=True,
        )
        assert stats.patterns_embedded == 3
        assert stats.episodes_embedded == 0
        assert not sqlite_path.exists()

    @patch("contemplative_agent.core.migration.embed_texts")
    @patch("contemplative_agent.core.views.embed_one")
    def test_dry_run_no_backup_no_save(self, mock_embed_one, mock_embed_texts,
                                        populated_knowledge, views_dir, tmp_path):
        mock_embed_one.return_value = np.array([1.0, 0.0], dtype=np.float32)
        mock_embed_texts.return_value = np.array([[0.0, 1.0]] * 3, dtype=np.float32)

        original = populated_knowledge.read_text(encoding="utf-8")
        stats = run_embed_backfill(
            knowledge_path=populated_knowledge,
            log_dir=tmp_path / "logs",
            sqlite_path=tmp_path / "embeddings.sqlite",
            views_dir=views_dir,
            dry_run=True,
        )
        assert stats.backup_path is None
        # Original unchanged
        assert populated_knowledge.read_text(encoding="utf-8") == original

    def test_default_threshold_in_range(self):
        assert 0.0 <= DEFAULT_NOISE_THRESHOLD <= 1.0
