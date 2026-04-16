"""Tests for ADR-0023 skill router + usage log."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import numpy as np

from contemplative_agent.core.skill_frontmatter import SkillMeta, render
from contemplative_agent.core.skill_router import (
    DEFAULT_THRESHOLD,
    FAILURE_RATE_FOR_REFLECT,
    MIN_FAILURES_FOR_REFLECT,
    SkillMatch,
    SkillRouter,
    SkillUsageStats,
    aggregate_usage,
    context_hash,
    needs_reflection,
)


def _emb(*xs: float) -> np.ndarray:
    v = np.asarray(xs, dtype=np.float32)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def _write_skill(
    skills_dir: Path,
    name: str,
    body: str,
    meta: Optional[SkillMeta] = None,
) -> Path:
    skills_dir.mkdir(parents=True, exist_ok=True)
    path = skills_dir / name
    text = render(meta, body) if meta is not None else body
    path.write_text(text, encoding="utf-8")
    return path


class _EmbedFake:
    """Deterministic embedder that maps substring → fixed vector."""

    def __init__(self, mapping: dict[str, np.ndarray], default: np.ndarray) -> None:
        self._mapping = mapping
        self._default = default
        self.calls: List[List[str]] = []

    def __call__(self, texts: List[str]) -> Optional[np.ndarray]:
        self.calls.append(list(texts))
        rows = []
        for t in texts:
            matched = None
            for key, vec in self._mapping.items():
                if key in t:
                    matched = vec
                    break
            rows.append(matched if matched is not None else self._default)
        return np.stack(rows).astype(np.float32)


class TestSelect:
    def test_empty_skills_dir_returns_empty(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        log_dir = tmp_path / "logs"
        embed = _EmbedFake({}, default=_emb(1.0, 0.0))
        router = SkillRouter(skills_dir, embed_fn=embed, log_dir=log_dir)
        matches = router.select("test context")
        assert matches == []

    def test_returns_top_k_sorted_by_cosine(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        log_dir = tmp_path / "logs"
        _write_skill(skills_dir, "alpha.md", "# Alpha\n\nalpha body")
        _write_skill(skills_dir, "beta.md", "# Beta\n\nbeta body")
        _write_skill(skills_dir, "gamma.md", "# Gamma\n\ngamma body")

        vec_q = _emb(1.0, 0.0, 0.0)
        embed = _EmbedFake(
            mapping={
                "alpha": _emb(0.95, 0.3, 0.0),  # high
                "beta": _emb(0.70, 0.7, 0.0),   # medium
                "gamma": _emb(0.0, 0.0, 1.0),   # low
                "query": vec_q,
            },
            default=vec_q,
        )
        router = SkillRouter(skills_dir, embed_fn=embed, log_dir=log_dir)
        matches = router.select("query here", top_k=2)
        assert [m.name for m in matches] == ["alpha.md", "beta.md"]
        assert matches[0].score > matches[1].score

    def test_below_threshold_returns_empty(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        log_dir = tmp_path / "logs"
        _write_skill(skills_dir, "alpha.md", "# Alpha\n\nalpha body")

        vec_q = _emb(1.0, 0.0)
        embed = _EmbedFake(
            mapping={
                "alpha": _emb(0.1, 0.99),  # very orthogonal
                "query": vec_q,
            },
            default=vec_q,
        )
        router = SkillRouter(
            skills_dir, embed_fn=embed, log_dir=log_dir, threshold=DEFAULT_THRESHOLD,
        )
        matches = router.select("query here")
        assert matches == []

    def test_empty_context_returns_empty_without_logging(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        log_dir = tmp_path / "logs"
        _write_skill(skills_dir, "alpha.md", "# Alpha\n\nalpha body")

        embed = _EmbedFake({}, default=_emb(1.0, 0.0))
        router = SkillRouter(skills_dir, embed_fn=embed, log_dir=log_dir)
        assert router.select("") == []
        assert router.select("   \n") == []
        assert not log_dir.exists() or not any(log_dir.glob("*.jsonl"))

    def test_tie_break_prefers_higher_net_success(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        log_dir = tmp_path / "logs"
        _write_skill(
            skills_dir, "alpha.md", "# Alpha\n\nalpha body",
            meta=SkillMeta(success_count=5, failure_count=0),
        )
        _write_skill(
            skills_dir, "beta.md", "# Beta\n\nbeta body",
            meta=SkillMeta(success_count=0, failure_count=3),
        )

        same = _emb(1.0, 0.0, 0.0)
        embed = _EmbedFake(
            mapping={
                "alpha body": same,
                "beta body": same,
                "query": same,
            },
            default=same,
        )
        router = SkillRouter(skills_dir, embed_fn=embed, log_dir=log_dir)
        matches = router.select("query here", top_k=2)
        assert matches[0].name == "alpha.md"
        assert matches[1].name == "beta.md"

    def test_selection_log_written(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        log_dir = tmp_path / "logs"
        _write_skill(skills_dir, "alpha.md", "# Alpha\n\nalpha body")

        vec_q = _emb(1.0, 0.0)
        embed = _EmbedFake(
            mapping={"alpha": _emb(0.9, 0.4), "query": vec_q},
            default=vec_q,
        )
        router = SkillRouter(skills_dir, embed_fn=embed, log_dir=log_dir)
        router.select("query here about alpha", action_id="abc123")

        log_files = list(log_dir.glob("skill-usage-*.jsonl"))
        assert len(log_files) == 1
        record = json.loads(log_files[0].read_text().strip())
        assert record["type"] == "selection"
        assert record["action_id"] == "abc123"
        assert record["selected"] == ["alpha.md"]
        assert "alpha" in record["context_excerpt"]

    def test_auto_generates_action_id_when_missing(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        log_dir = tmp_path / "logs"
        _write_skill(skills_dir, "alpha.md", "# Alpha\n\nalpha body")

        vec_q = _emb(1.0, 0.0)
        embed = _EmbedFake(
            mapping={"alpha": _emb(0.9, 0.4), "query": vec_q},
            default=vec_q,
        )
        router = SkillRouter(skills_dir, embed_fn=embed, log_dir=log_dir)
        router.select("query text")
        log_files = list(log_dir.glob("skill-usage-*.jsonl"))
        record = json.loads(log_files[0].read_text().strip())
        assert isinstance(record["action_id"], str) and len(record["action_id"]) == 16

    def test_no_match_still_logs_selection(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        log_dir = tmp_path / "logs"
        _write_skill(skills_dir, "alpha.md", "# Alpha\n\nalpha body")

        vec_q = _emb(1.0, 0.0)
        embed = _EmbedFake(
            mapping={"alpha": _emb(0.1, 0.99), "query": vec_q},  # low sim
            default=vec_q,
        )
        router = SkillRouter(skills_dir, embed_fn=embed, log_dir=log_dir)
        router.select("query here", action_id="no_match")

        log_files = list(log_dir.glob("skill-usage-*.jsonl"))
        record = json.loads(log_files[0].read_text().strip())
        assert record["selected"] == []
        assert record["action_id"] == "no_match"

    def test_embed_failure_returns_empty(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        log_dir = tmp_path / "logs"
        _write_skill(skills_dir, "alpha.md", "# Alpha\n\nalpha body")

        def embed_none(_: List[str]) -> Optional[np.ndarray]:
            return None

        router = SkillRouter(skills_dir, embed_fn=embed_none, log_dir=log_dir)
        matches = router.select("query here")
        assert matches == []

    def test_cache_invalidated_on_mtime_change(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        log_dir = tmp_path / "logs"
        path = _write_skill(skills_dir, "alpha.md", "# Alpha\n\nversion 1")

        vec_q = _emb(1.0, 0.0)
        embed = _EmbedFake(
            mapping={"version 1": _emb(0.9, 0.4), "version 2": _emb(0.1, 0.99), "query": vec_q},
            default=vec_q,
        )
        router = SkillRouter(skills_dir, embed_fn=embed, log_dir=log_dir)
        matches = router.select("query here")
        assert len(matches) == 1  # version 1 passes threshold

        # Overwrite with "version 2" — should miss threshold. Bump mtime.
        import os, time
        time.sleep(0.01)
        path.write_text("# Alpha\n\nversion 2\n", encoding="utf-8")
        os.utime(path, None)  # ensure mtime advance on some FS

        matches2 = router.select("query here")
        assert matches2 == []


class TestOutcome:
    def test_record_success(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        router = SkillRouter(tmp_path / "skills", embed_fn=lambda x: None, log_dir=log_dir)
        router.record_outcome("abc", "success")
        log_files = list(log_dir.glob("skill-usage-*.jsonl"))
        assert len(log_files) == 1
        record = json.loads(log_files[0].read_text().strip())
        assert record["type"] == "outcome"
        assert record["action_id"] == "abc"
        assert record["outcome"] == "success"

    def test_record_failure_with_note(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        router = SkillRouter(tmp_path / "skills", embed_fn=lambda x: None, log_dir=log_dir)
        router.record_outcome("abc", "failure", note="timed out")
        record = json.loads(
            next(log_dir.glob("skill-usage-*.jsonl")).read_text().strip()
        )
        assert record["outcome"] == "failure"
        assert record["note"] == "timed out"

    def test_rejects_unknown_outcome(self, tmp_path: Path) -> None:
        router = SkillRouter(tmp_path / "skills", embed_fn=lambda x: None, log_dir=None)
        import pytest
        with pytest.raises(ValueError):
            router.record_outcome("abc", "wibble")  # type: ignore[arg-type]


class TestLoadUsage:
    def test_reads_back_records(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        log_dir = tmp_path / "logs"
        _write_skill(skills_dir, "alpha.md", "# Alpha\n\nalpha body")

        vec_q = _emb(1.0, 0.0)
        embed = _EmbedFake(
            mapping={"alpha": _emb(0.9, 0.4), "query": vec_q},
            default=vec_q,
        )
        router = SkillRouter(skills_dir, embed_fn=embed, log_dir=log_dir)
        router.select("query here about alpha", action_id="abc")
        router.record_outcome("abc", "success")

        records = router.load_usage(days=1)
        assert len(records) == 2
        assert records[0]["type"] == "selection"
        assert records[1]["type"] == "outcome"

    def test_ignores_corrupt_lines(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = log_dir / f"skill-usage-{today}.jsonl"
        path.write_text(
            '{"type": "outcome", "action_id": "x", "outcome": "success"}\n'
            "not valid json\n"
            '{"type": "outcome", "action_id": "y", "outcome": "failure"}\n',
            encoding="utf-8",
        )
        router = SkillRouter(tmp_path / "skills", embed_fn=lambda x: None, log_dir=log_dir)
        records = router.load_usage(days=1)
        assert len(records) == 2

    def test_empty_when_no_log_dir(self, tmp_path: Path) -> None:
        router = SkillRouter(tmp_path / "skills", embed_fn=lambda x: None, log_dir=None)
        assert router.load_usage() == []


class TestAggregateUsage:
    def test_joins_selection_to_outcome(self) -> None:
        records = [
            {"type": "selection", "action_id": "a1", "selected": ["alpha.md"],
             "context_excerpt": "ctx a"},
            {"type": "outcome", "action_id": "a1", "outcome": "success"},
            {"type": "selection", "action_id": "a2", "selected": ["alpha.md", "beta.md"],
             "context_excerpt": "ctx b"},
            {"type": "outcome", "action_id": "a2", "outcome": "failure"},
        ]
        stats = aggregate_usage(records)
        assert stats["alpha.md"].selections == 2
        assert stats["alpha.md"].successes == 1
        assert stats["alpha.md"].failures == 1
        assert "ctx b" in stats["alpha.md"].failure_contexts
        assert stats["beta.md"].failures == 1

    def test_selection_without_outcome_counts_as_pending(self) -> None:
        records = [
            {"type": "selection", "action_id": "a1", "selected": ["alpha.md"]},
        ]
        stats = aggregate_usage(records)
        assert stats["alpha.md"].selections == 1
        assert stats["alpha.md"].outcomes == 0

    def test_failure_rate(self) -> None:
        stats = SkillUsageStats(name="x", selections=5, successes=1, failures=3, partials=0)
        assert stats.outcomes == 4
        assert abs(stats.failure_rate - 0.75) < 1e-6

    def test_needs_reflection(self) -> None:
        ok = SkillUsageStats(name="x", selections=10, successes=2, failures=3, partials=0)
        not_enough = SkillUsageStats(name="y", selections=5, successes=0, failures=1, partials=0)
        low_rate = SkillUsageStats(name="z", selections=20, successes=18, failures=2, partials=0)
        assert needs_reflection(ok)
        assert not needs_reflection(not_enough)  # < MIN_FAILURES
        assert not needs_reflection(low_rate)    # < FAILURE_RATE


class TestContextHash:
    def test_short_hex(self) -> None:
        h = context_hash("some text")
        assert isinstance(h, str) and len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)


def test_constants_sanity() -> None:
    """Lock down the thresholds so accidental re-tuning shows in diffs."""
    assert MIN_FAILURES_FOR_REFLECT == 2
    assert abs(FAILURE_RATE_FOR_REFLECT - 0.3) < 1e-6
    assert abs(DEFAULT_THRESHOLD - 0.45) < 1e-6


def test_skill_match_shape() -> None:
    match = SkillMatch(
        name="x.md",
        path=Path("x.md"),
        body="# Title\n",
        score=0.9,
        meta=SkillMeta(),
    )
    assert match.name == "x.md" and match.score == 0.9


class TestEmbedFailureADR0023:
    """ADR-0023 / skill_router.py:192-194 — when the embedder returns None
    or a wrong-sized vector, ``_embed_missing`` logs and bails without
    writing to the cache. Prevents index errors on the next select() call
    that would otherwise index into a partially-populated cache."""

    def test_embed_returning_none_bails_without_cache_write(
        self, tmp_path: Path, caplog,
    ) -> None:
        skills_dir = tmp_path / "skills"
        log_dir = tmp_path / "logs"
        _write_skill(skills_dir, "alpha.md", "# Alpha\n\nalpha body")

        def none_embed(texts: List[str]) -> Optional[np.ndarray]:
            return None

        router = SkillRouter(skills_dir, embed_fn=none_embed, log_dir=log_dir)
        with caplog.at_level("WARNING", logger="contemplative_agent.core.skill_router"):
            matches = router.select("query")
        assert matches == []
        assert "skill embedding failed" in caplog.text.lower()

    def test_embed_wrong_length_bails_without_cache_write(
        self, tmp_path: Path, caplog,
    ) -> None:
        skills_dir = tmp_path / "skills"
        log_dir = tmp_path / "logs"
        _write_skill(skills_dir, "alpha.md", "# Alpha\n\nalpha body")
        _write_skill(skills_dir, "beta.md", "# Beta\n\nbeta body")

        def short_embed(texts: List[str]) -> np.ndarray:
            # expected 2 rows, returns 1
            return np.array([[1.0, 0.0]], dtype=np.float32)

        router = SkillRouter(skills_dir, embed_fn=short_embed, log_dir=log_dir)
        with caplog.at_level("WARNING", logger="contemplative_agent.core.skill_router"):
            matches = router.select("query")
        assert matches == []
        assert "skill embedding failed" in caplog.text.lower()
