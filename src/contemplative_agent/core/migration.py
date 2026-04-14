"""Migration logic for ADR-0009 (embedding-based memory architecture).

Backfills knowledge.json patterns with `embedding` and `gated` fields,
and bulk-embeds the episode log into a SQLite sidecar. Used by the
``embed-backfill`` CLI subcommand.

The migration is additive on the pattern dict: it adds new fields but
does not remove ``category`` / ``subcategory``. Removal happens in the
distill code path that no longer writes them; old records keep their
legacy fields until natural rewrite.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from .embeddings import cosine, embed_texts
from .episode_embeddings import EpisodeEmbeddingStore, episode_id_for
from .episode_log import EpisodeLog
from .knowledge_store import KnowledgeStore
from .views import ViewRegistry

logger = logging.getLogger(__name__)

# Patterns whose noise similarity is at or above this are gated (skipped at
# distillation). Calibrated against the noise.md seed; tune via dry runs.
DEFAULT_NOISE_THRESHOLD = 0.55

# Bulk embed batch size — Ollama /api/embed accepts arrays. Keeps memory
# bounded and gives tqdm-style progress.
EMBED_BATCH_SIZE = 32


@dataclass
class BackfillStats:
    patterns_total: int = 0
    patterns_embedded: int = 0
    patterns_gated: int = 0
    patterns_skipped: int = 0  # already had embedding+gated
    episodes_total: int = 0
    episodes_embedded: int = 0
    episodes_skipped: int = 0  # already in sidecar
    episodes_failed: int = 0
    backup_path: Optional[Path] = None
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)


def backup_knowledge(knowledge_path: Path) -> Optional[Path]:
    """Copy knowledge.json to knowledge.json.bak.{timestamp}.

    Returns the backup path, or None if source file does not exist.
    Uses copy2 to preserve mtime.
    """
    if not knowledge_path.exists():
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    backup_path = knowledge_path.with_name(f"{knowledge_path.name}.bak.{ts}")
    shutil.copy2(knowledge_path, backup_path)
    return backup_path


def _summarize_for_embedding(record: Dict) -> str:
    """One-line text representation of an episode for embedding.

    Mirrors distill.summarize_record but inlined to avoid a circular
    import once distill is rewritten in commit 5.
    """
    record_type = record.get("type", "unknown")
    data = record.get("data", {}) or {}
    if record_type == "interaction":
        direction = data.get("direction", "?")
        agent = data.get("agent_name", "unknown")
        content = str(data.get("content_summary", ""))[:200]
        return f"{direction} with {agent}: {content}"
    if record_type == "post":
        title = data.get("title", data.get("topic_summary", "untitled"))
        body = str(data.get("body", ""))[:200]
        return f"posted: {title}. {body}".strip()
    if record_type == "insight":
        return str(data.get("observation", ""))[:300]
    if record_type == "activity":
        action = data.get("action", "unknown")
        target = data.get("target_agent", data.get("post_id", ""))
        return f"{action} {target}".strip()
    return f"{record_type}: {json.dumps(data, ensure_ascii=False)[:200]}"


def _bulk_embed(texts: List[str]) -> Optional[np.ndarray]:
    """Wrapper that returns None on any failure for caller convenience."""
    if not texts:
        return None
    return embed_texts(texts)


def backfill_pattern_embeddings(
    knowledge: KnowledgeStore,
    view_registry: ViewRegistry,
    *,
    noise_threshold: float = DEFAULT_NOISE_THRESHOLD,
    dry_run: bool = False,
) -> BackfillStats:
    """Add `embedding` and `gated` to every pattern that lacks them.

    Patterns are batched through Ollama for efficiency. ``gated`` is
    derived from cosine similarity to the ``noise`` view's centroid.
    Patterns that were classified as ``noise`` under the legacy schema
    are pre-gated.
    """
    stats = BackfillStats()
    patterns = knowledge.get_raw_patterns()
    stats.patterns_total = len(patterns)

    # Build queues of patterns needing work
    needing_embedding: List[int] = []
    for i, p in enumerate(patterns):
        if not isinstance(p.get("embedding"), list):
            needing_embedding.append(i)

    if not needing_embedding:
        # Even if all have embeddings, gated may be missing
        _backfill_gated(patterns, view_registry, stats, noise_threshold)
        stats.patterns_skipped = stats.patterns_total
        return stats

    # Embed in batches
    for batch_start in range(0, len(needing_embedding), EMBED_BATCH_SIZE):
        batch_idx = needing_embedding[batch_start : batch_start + EMBED_BATCH_SIZE]
        texts = [patterns[i]["pattern"] for i in batch_idx]
        if dry_run:
            stats.patterns_embedded += len(batch_idx)
            continue
        result = _bulk_embed(texts)
        if result is None or result.shape[0] != len(batch_idx):
            stats.errors.append(
                f"embed batch starting at index {batch_idx[0]} failed; skipping"
            )
            continue
        for i, vec in zip(batch_idx, result):
            patterns[i]["embedding"] = [float(x) for x in vec]
            stats.patterns_embedded += 1

    # Now compute gated for everything
    _backfill_gated(patterns, view_registry, stats, noise_threshold, dry_run=dry_run)

    return stats


def _backfill_gated(
    patterns: List[Dict],
    view_registry: ViewRegistry,
    stats: BackfillStats,
    noise_threshold: float,
    dry_run: bool = False,
) -> None:
    """Fill `gated` field by comparing each pattern embedding to the noise centroid."""
    noise_centroid = view_registry.get_centroid("noise")
    if noise_centroid is None:
        stats.errors.append(
            "noise view centroid unavailable — cannot compute gated. "
            "Verify config/views/noise.md and Ollama embedding model."
        )
        return
    for p in patterns:
        if isinstance(p.get("gated"), bool):
            continue
        # Pre-existing legacy noise label takes precedence as a safety net
        if p.get("category") == "noise":
            if not dry_run:
                p["gated"] = True
            stats.patterns_gated += 1
            continue
        emb = p.get("embedding")
        if not isinstance(emb, list):
            continue  # cannot judge without embedding
        vec = np.asarray(emb, dtype=np.float32)
        sim = cosine(vec, noise_centroid)
        gated = sim >= noise_threshold
        if not dry_run:
            p["gated"] = gated
        if gated:
            stats.patterns_gated += 1


def _iter_episode_files(log_dir: Path, episodes_days: Optional[int]) -> List[Path]:
    """List jsonl files in log_dir, optionally limited to the most recent N days."""
    if not log_dir.exists():
        return []
    files = sorted(log_dir.glob("*.jsonl"))
    if episodes_days is None:
        return files
    cutoff = (datetime.now(timezone.utc).date()).toordinal() - episodes_days
    out = []
    for path in files:
        stem = path.stem  # e.g. "2026-04-15"
        try:
            d = datetime.strptime(stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d.toordinal() >= cutoff:
            out.append(path)
    return out


def backfill_episode_embeddings(
    log_dir: Path,
    store: EpisodeEmbeddingStore,
    *,
    episodes_days: Optional[int] = None,
    dry_run: bool = False,
    progress: Optional[Callable[[int, int], None]] = None,
) -> BackfillStats:
    """Bulk embed all episodes (in jsonl files) into the SQLite sidecar.

    Skips episodes whose id is already present in the sidecar. Bulk
    embeds in batches of EMBED_BATCH_SIZE for throughput.
    """
    stats = BackfillStats()
    files = _iter_episode_files(log_dir, episodes_days)

    pending: List[Tuple[str, str, str]] = []  # (id, ts, text)
    for path in files:
        try:
            records = EpisodeLog.read_file(path)
        except OSError as exc:
            stats.errors.append(f"read failed for {path.name}: {exc}")
            continue
        for record in records:
            stats.episodes_total += 1
            eid = episode_id_for(record)
            if store.has(eid):
                stats.episodes_skipped += 1
                continue
            text = _summarize_for_embedding(record)
            if not text:
                continue
            pending.append((eid, record.get("ts", ""), text))

    if not pending:
        return stats

    if dry_run:
        stats.episodes_embedded = len(pending)
        return stats

    for batch_start in range(0, len(pending), EMBED_BATCH_SIZE):
        batch = pending[batch_start : batch_start + EMBED_BATCH_SIZE]
        texts = [t for _, _, t in batch]
        result = _bulk_embed(texts)
        if result is None or result.shape[0] != len(batch):
            stats.episodes_failed += len(batch)
            stats.errors.append(
                f"episode embed batch failed at item {batch_start}"
            )
            continue
        rows = [
            (eid, ts, vec)
            for (eid, ts, _), vec in zip(batch, result)
        ]
        store.upsert_many(rows)
        stats.episodes_embedded += len(rows)
        if progress is not None:
            progress(stats.episodes_embedded, len(pending))

    return stats


def run_embed_backfill(
    *,
    knowledge_path: Path,
    log_dir: Path,
    sqlite_path: Path,
    views_dir: Path,
    episodes_days: Optional[int] = None,
    patterns_only: bool = False,
    noise_threshold: float = DEFAULT_NOISE_THRESHOLD,
    dry_run: bool = False,
) -> BackfillStats:
    """Run the full backfill pipeline.

    Returns merged stats. On dry_run, no files are written but the
    pipeline runs end-to-end (embedding calls included for accurate
    counts) so users can spot config/threshold issues before committing.
    """
    started = time.time()
    stats = BackfillStats()

    # 1. Backup knowledge.json
    if not dry_run and knowledge_path.exists():
        stats.backup_path = backup_knowledge(knowledge_path)
        if stats.backup_path is not None:
            logger.info("Backed up knowledge.json → %s", stats.backup_path.name)

    # 2. Load knowledge + views
    knowledge = KnowledgeStore(path=knowledge_path)
    knowledge.load()
    view_registry = ViewRegistry(views_dir=views_dir)
    view_registry.load_views()

    # 3. Pattern embeddings + gated
    pattern_stats = backfill_pattern_embeddings(
        knowledge, view_registry,
        noise_threshold=noise_threshold,
        dry_run=dry_run,
    )
    _merge_pattern_stats(stats, pattern_stats)
    if not dry_run and pattern_stats.patterns_embedded > 0:
        knowledge.save()
        logger.info(
            "knowledge.json: %d patterns embedded, %d gated",
            pattern_stats.patterns_embedded,
            pattern_stats.patterns_gated,
        )

    # 4. Episode embeddings (skipped if --patterns-only)
    if not patterns_only:
        store = EpisodeEmbeddingStore(db_path=sqlite_path)
        episode_stats = backfill_episode_embeddings(
            log_dir, store,
            episodes_days=episodes_days,
            dry_run=dry_run,
        )
        _merge_episode_stats(stats, episode_stats)
        logger.info(
            "episodes: %d total, %d newly embedded, %d skipped (already present), %d failed",
            episode_stats.episodes_total,
            episode_stats.episodes_embedded,
            episode_stats.episodes_skipped,
            episode_stats.episodes_failed,
        )

    stats.duration_seconds = time.time() - started
    return stats


def _merge_pattern_stats(dst: BackfillStats, src: BackfillStats) -> None:
    dst.patterns_total = src.patterns_total
    dst.patterns_embedded = src.patterns_embedded
    dst.patterns_gated = src.patterns_gated
    dst.patterns_skipped = src.patterns_skipped
    dst.errors.extend(src.errors)


def _merge_episode_stats(dst: BackfillStats, src: BackfillStats) -> None:
    dst.episodes_total = src.episodes_total
    dst.episodes_embedded = src.episodes_embedded
    dst.episodes_skipped = src.episodes_skipped
    dst.episodes_failed = src.episodes_failed
    dst.errors.extend(src.errors)
