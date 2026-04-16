"""Tests for ADR-0021 pattern schema additions in KnowledgeStore."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from contemplative_agent.core.knowledge_store import (
    DEFAULT_TRUST,
    TRUST_BASE_BY_SOURCE,
    KnowledgeStore,
    effective_importance,
)
from contemplative_agent.core.forgetting import (
    STRENGTH_FLOOR,
    TRUST_FLOOR,
    compute_strength,
    is_live,
    mark_accessed,
    time_constant,
)
from contemplative_agent.core.feedback import record_outcome, record_outcome_batch


class TestLoadIdempotency:
    """Regression: load() must reset state so repeated calls do not duplicate.

    Multiple commands (insight, distill, distill-identity) call load()
    at both the CLI handler and core function layer. Without idempotency
    a subsequent save() persists the doubled list — observed in the wild
    as 285 pairs with identical valid_from on a production knowledge.json.
    """

    def test_load_twice_does_not_duplicate(self, tmp_path: Path):
        path = tmp_path / "k.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern("first observed behavior pattern in agent logs")
        store.add_learned_pattern("second observed behavior pattern in agent logs")
        store.save()

        fresh = KnowledgeStore(path=path)
        fresh.load()
        first_count = len(fresh.get_raw_patterns())
        fresh.load()
        second_count = len(fresh.get_raw_patterns())

        assert first_count == 2
        assert second_count == first_count

    def test_load_resets_preexisting_in_memory_state(self, tmp_path: Path):
        path = tmp_path / "k.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern("persisted pattern written to disk")
        store.save()

        fresh = KnowledgeStore(path=path)
        fresh.add_learned_pattern("in-memory only pattern not on disk")
        fresh.load()

        texts = [p["pattern"] for p in fresh.get_raw_patterns()]
        assert texts == ["persisted pattern written to disk"]


class TestAddLearnedPatternADR0021:
    def test_defaults_for_new_pattern(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        store.add_learned_pattern("observed something interesting in the agent logs today")
        assert len(store.get_raw_patterns()) == 1
        p = store.get_raw_patterns()[0]
        assert p["provenance"] == {"source_type": "unknown"}
        assert p["trust_score"] == DEFAULT_TRUST
        assert p["valid_until"] is None
        assert p["access_count"] == 0
        assert p["success_count"] == 0
        assert p["failure_count"] == 0
        assert p["valid_from"] == p["distilled"]

    def test_explicit_provenance_preserved(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        prov = {
            "source_type": "self_reflection",
            "source_episode_ids": ["2026-04-15#1"],
            "sanitized": True,
            "pipeline_version": "distill@0.21",
        }
        store.add_learned_pattern(
            "reflective note on boundless care", provenance=prov, trust_score=0.88
        )
        p = store.get_raw_patterns()[0]
        assert p["provenance"] == prov
        assert p["trust_score"] == pytest.approx(0.88)


class TestRoundTripADR0021:
    def test_save_then_load_preserves_new_fields(self, tmp_path: Path):
        path = tmp_path / "k.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern(
            "long enough pattern to pass the valid pattern gate easily",
            provenance={"source_type": "external_post"},
            trust_score=0.42,
        )
        store.save()

        # Re-load and verify round-trip
        store2 = KnowledgeStore(path=path)
        store2.load()
        p = store2.get_raw_patterns()[0]
        assert p["provenance"]["source_type"] == "external_post"
        assert p["trust_score"] == pytest.approx(0.42)
        assert p["valid_until"] is None
        assert "last_accessed_at" in p
        assert p["access_count"] == 0

    def test_legacy_file_loads_without_adr0021_fields(self, tmp_path: Path):
        """Files written by pre-0021 code should load cleanly, without auto-fill."""
        path = tmp_path / "k.json"
        legacy = [
            {
                "pattern": "legacy pattern without any ADR-0021 metadata present",
                "distilled": "2026-03-01T00:00",
                "importance": 0.7,
                "category": "uncategorized",
            }
        ]
        path.write_text(json.dumps(legacy), encoding="utf-8")
        store = KnowledgeStore(path=path)
        store.load()
        p = store.get_raw_patterns()[0]
        assert "provenance" not in p
        assert "trust_score" not in p
        assert "valid_until" not in p


class TestEffectiveImportanceADR0021:
    def test_legacy_path_unaffected_without_fields(self):
        """Patterns without trust/strength fields score as legacy importance × decay."""
        now = datetime.now(timezone.utc)
        p = {"importance": 1.0, "distilled": now.isoformat(timespec="minutes")}
        # Fresh pattern at importance 1.0 → very close to 1.0
        score = effective_importance(p)
        assert 0.9 <= score <= 1.0

    def test_low_trust_reduces_score(self):
        now = datetime.now(timezone.utc)
        high_trust = {
            "importance": 1.0,
            "distilled": now.isoformat(timespec="minutes"),
            "trust_score": 1.0,
            "last_accessed_at": now.isoformat(timespec="minutes"),
            "access_count": 0,
        }
        low_trust = {**high_trust, "trust_score": 0.3}
        assert effective_importance(low_trust) < effective_importance(high_trust)
        # Ratio ≈ 0.3
        ratio = effective_importance(low_trust) / effective_importance(high_trust)
        assert 0.25 <= ratio <= 0.35


class TestForgetting:
    def test_time_constant_grows_with_importance(self):
        low = time_constant(0.1, access_count=0)
        high = time_constant(0.9, access_count=0)
        assert high > low

    def test_time_constant_grows_with_access(self):
        s0 = time_constant(0.5, access_count=0)
        s1 = time_constant(0.5, access_count=10)
        s2 = time_constant(0.5, access_count=100)
        assert s0 < s1 < s2

    def test_compute_strength_fresh_pattern_is_near_one(self):
        now = datetime.now(timezone.utc)
        p = {
            "importance": 0.5,
            "last_accessed_at": now.isoformat(timespec="minutes"),
            "access_count": 0,
        }
        assert compute_strength(p, now=now) == pytest.approx(1.0, abs=1e-2)

    def test_compute_strength_decays_over_time(self):
        now = datetime.now(timezone.utc)
        old = (now - timedelta(days=100)).isoformat(timespec="minutes")
        p = {
            "importance": 0.5,
            "last_accessed_at": old,
            "access_count": 0,
        }
        strength = compute_strength(p, now=now)
        assert 0.0 <= strength < 0.2

    def test_mark_accessed_updates_count_and_timestamp(self):
        p: dict = {"access_count": 2}
        now = datetime.now(timezone.utc)
        mark_accessed(p, now=now)
        assert p["access_count"] == 3
        assert str(p["last_accessed_at"]).startswith(now.strftime("%Y-%m-%dT%H:%M"))

    def test_is_live_rejects_invalidated(self):
        p = {"valid_until": "2026-04-01T00:00", "trust_score": 1.0}
        assert not is_live(p)

    def test_is_live_rejects_low_trust(self):
        now = datetime.now(timezone.utc)
        p = {
            "valid_until": None,
            "trust_score": TRUST_FLOOR - 0.01,
            "last_accessed_at": now.isoformat(timespec="minutes"),
            "access_count": 0,
            "importance": 0.5,
        }
        assert not is_live(p)

    def test_is_live_rejects_weak_strength(self):
        now = datetime.now(timezone.utc)
        very_old = (now - timedelta(days=10_000)).isoformat(timespec="minutes")
        p = {
            "valid_until": None,
            "trust_score": 1.0,
            "last_accessed_at": very_old,
            "access_count": 0,
            "importance": 0.1,
        }
        assert compute_strength(p, now=now) < STRENGTH_FLOOR
        assert not is_live(p, now=now)


class TestFeedback:
    def test_success_increments_counter_and_nudges_trust_up(self):
        p = {"success_count": 0, "failure_count": 0, "trust_score": 0.6}
        record_outcome(p, success=True)
        assert p["success_count"] == 1
        assert p["trust_score"] > 0.6

    def test_failure_hurts_more_than_success_helps(self):
        a = {"trust_score": 0.6, "success_count": 0, "failure_count": 0}
        b = {"trust_score": 0.6, "success_count": 0, "failure_count": 0}
        record_outcome(a, success=True)
        record_outcome(b, success=False)
        delta_up = a["trust_score"] - 0.6
        delta_down = 0.6 - b["trust_score"]
        assert delta_down > delta_up

    def test_trust_clamps_to_range(self):
        p = {"trust_score": 0.99, "success_count": 0, "failure_count": 0}
        for _ in range(1000):
            record_outcome(p, success=True)
        assert p["trust_score"] <= 1.0
        for _ in range(1000):
            record_outcome(p, success=False)
        assert p["trust_score"] >= 0.0

    def test_batch_applies_to_all(self):
        patterns = [
            {"trust_score": 0.6, "success_count": 0, "failure_count": 0}
            for _ in range(5)
        ]
        count = record_outcome_batch(patterns, success=True)
        assert count == 5
        assert all(p["success_count"] == 1 for p in patterns)


class TestMigrationADR0021:
    def test_migrate_fills_defaults(self, tmp_path: Path):
        from contemplative_agent.core.migration import migrate_patterns_to_adr0021

        path = tmp_path / "k.json"
        legacy = [
            {
                "pattern": "legacy pattern one, long enough to pass the filter",
                "distilled": "2026-03-01T00:00",
                "importance": 0.7,
            },
            {
                "pattern": "legacy pattern two, also long enough to pass the filter",
                "distilled": "2026-03-02T00:00",
                "importance": 0.8,
                "last_accessed": "2026-03-15T12:00",  # legacy field
            },
        ]
        path.write_text(json.dumps(legacy), encoding="utf-8")

        stats = migrate_patterns_to_adr0021(path)
        assert stats.patterns_total == 2
        assert stats.patterns_updated == 2
        assert stats.patterns_already_migrated == 0
        assert stats.backup_path is not None and stats.backup_path.exists()

        # Reload and check fields
        store = KnowledgeStore(path=path)
        store.load()
        p1, p2 = store.get_raw_patterns()
        for p in (p1, p2):
            assert p["provenance"] == {"source_type": "unknown"}
            assert p["trust_score"] == DEFAULT_TRUST
            assert p["valid_until"] is None
            assert p["access_count"] == 0

        # Legacy last_accessed migrated to last_accessed_at
        assert p2["last_accessed_at"] == "2026-03-15T12:00"
        # valid_from uses distilled timestamp where available
        assert p1["valid_from"] == "2026-03-01T00:00"

    def test_migrate_is_idempotent(self, tmp_path: Path):
        from contemplative_agent.core.migration import migrate_patterns_to_adr0021

        path = tmp_path / "k.json"
        legacy = [{
            "pattern": "legacy pattern text that is long enough for the gate",
            "distilled": "2026-03-01T00:00",
            "importance": 0.5,
        }]
        path.write_text(json.dumps(legacy), encoding="utf-8")

        s1 = migrate_patterns_to_adr0021(path)
        s2 = migrate_patterns_to_adr0021(path)
        assert s1.patterns_updated == 1
        assert s2.patterns_updated == 0
        assert s2.patterns_already_migrated == 1

    def test_migrate_dry_run_does_not_write(self, tmp_path: Path):
        from contemplative_agent.core.migration import migrate_patterns_to_adr0021

        path = tmp_path / "k.json"
        content = json.dumps([{
            "pattern": "a long enough pattern to pass the minimum filter check",
            "distilled": "2026-03-01T00:00",
            "importance": 0.5,
        }])
        path.write_text(content, encoding="utf-8")
        pre_mtime = path.stat().st_mtime

        stats = migrate_patterns_to_adr0021(path, dry_run=True)
        assert stats.patterns_updated == 1
        assert stats.backup_path is None
        assert path.read_text(encoding="utf-8") == content
        assert path.stat().st_mtime == pre_mtime


class TestTrustBaseBySource:
    def test_self_reflection_highest(self):
        assert TRUST_BASE_BY_SOURCE["self_reflection"] > TRUST_BASE_BY_SOURCE["external_post"]
        assert TRUST_BASE_BY_SOURCE["self_reflection"] > TRUST_BASE_BY_SOURCE["external_reply"]

    def test_all_within_range(self):
        for name, value in TRUST_BASE_BY_SOURCE.items():
            assert 0.0 <= value <= 1.0, f"{name}={value} out of range"


class TestReplacePatternADR0021:
    """ADR-0021 / knowledge_store.py:155-166 — replace_pattern swaps a
    pattern by identity (``is``). If this breaks, bitemporal invalidation
    fails silently: the old pattern stays live and the chain corrupts."""

    def test_returns_true_and_swaps_in_place(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        store.add_learned_pattern(
            "long enough pattern to pass the valid pattern gate easily",
        )
        old = store._learned_patterns[0]
        new = dict(old)
        new["valid_until"] = "2026-05-01T00:00:00+00:00"

        assert store.replace_pattern(old, new) is True
        assert len(store._learned_patterns) == 1
        assert store._learned_patterns[0] is new

    def test_returns_false_when_target_not_present(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        store.add_learned_pattern(
            "long enough pattern to pass the valid pattern gate easily",
        )
        stranger = {"pattern": "not in store", "distilled": "2026-01-01"}

        assert store.replace_pattern(stranger, {"pattern": "irrelevant"}) is False
        assert len(store._learned_patterns) == 1


class TestFilterSinceBadTimestampADR0021:
    """ADR-0021 / knowledge_store.py:183-199 — bad ``since`` ISO returns the
    full pool; individual records with malformed ``distilled`` are skipped
    rather than crashing the whole filter."""

    def test_bad_since_string_falls_back_to_full_pool(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        store.add_learned_pattern(
            "pattern alpha that is long enough to pass the valid gate easily",
        )
        store.add_learned_pattern(
            "pattern beta that is long enough to pass the valid gate easily",
        )

        result = store.get_raw_patterns_since("not-an-iso-timestamp")
        assert len(result) == 2

    def test_record_with_bad_distilled_is_skipped(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        store.add_learned_pattern(
            "good pattern with a properly formatted distilled timestamp field",
        )
        store._learned_patterns.append({
            "pattern": "broken record with malformed distilled",
            "distilled": "not-a-real-iso",
            "importance": 0.5,
        })

        result = store.get_raw_patterns_since("2020-01-01T00:00:00+00:00")
        assert any("good pattern" in p["pattern"] for p in result)
        assert not any("broken record" in p["pattern"] for p in result)
