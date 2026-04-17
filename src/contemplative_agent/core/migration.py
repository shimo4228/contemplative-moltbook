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

from ._io import now_iso
from .distill import NOISE_THRESHOLD as DEFAULT_NOISE_THRESHOLD
from .embeddings import cosine, embed_texts
from .episode_embeddings import EpisodeEmbeddingStore, episode_id_for
from .episode_log import EpisodeLog
from .knowledge_store import KnowledgeStore
from .views import ViewRegistry

logger = logging.getLogger(__name__)

# Bulk embed batch size — Ollama /api/embed accepts arrays. Keeps memory
# bounded and gives tqdm-style progress.
EMBED_BATCH_SIZE = 32


@dataclass(frozen=True)
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
    errors: Tuple[str, ...] = ()


@dataclass
class _BackfillBuilder:
    """Internal mutable accumulator for BackfillStats.

    Not exported — callers receive an immutable ``BackfillStats`` via
    ``.build()``.
    """

    patterns_total: int = 0
    patterns_embedded: int = 0
    patterns_gated: int = 0
    patterns_skipped: int = 0
    episodes_total: int = 0
    episodes_embedded: int = 0
    episodes_skipped: int = 0
    episodes_failed: int = 0
    backup_path: Optional[Path] = None
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)

    def build(self) -> BackfillStats:
        return BackfillStats(
            patterns_total=self.patterns_total,
            patterns_embedded=self.patterns_embedded,
            patterns_gated=self.patterns_gated,
            patterns_skipped=self.patterns_skipped,
            episodes_total=self.episodes_total,
            episodes_embedded=self.episodes_embedded,
            episodes_skipped=self.episodes_skipped,
            episodes_failed=self.episodes_failed,
            backup_path=self.backup_path,
            duration_seconds=self.duration_seconds,
            errors=tuple(self.errors),
        )


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
    """Text representation of an episode for embedding.

    Delegates to distill.summarize_record; falls back to a JSON dump for
    record types distill doesn't know about so migration never drops an
    episode silently.
    """
    from .distill import summarize_record

    record_type = record.get("type", "unknown")
    data = record.get("data", {}) or {}
    summary = summarize_record(record_type, data)
    if summary:
        return summary
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
    builder = _BackfillBuilder()
    patterns = knowledge.get_raw_patterns()
    builder.patterns_total = len(patterns)

    # Build queues of patterns needing work
    needing_embedding: List[int] = []
    for i, p in enumerate(patterns):
        if not isinstance(p.get("embedding"), list):
            needing_embedding.append(i)

    if not needing_embedding:
        # Even if all have embeddings, gated may be missing
        _backfill_gated(patterns, view_registry, builder, noise_threshold)
        builder.patterns_skipped = builder.patterns_total
        return builder.build()

    # Embed in batches
    for batch_start in range(0, len(needing_embedding), EMBED_BATCH_SIZE):
        batch_idx = needing_embedding[batch_start : batch_start + EMBED_BATCH_SIZE]
        texts = [patterns[i]["pattern"] for i in batch_idx]
        if dry_run:
            builder.patterns_embedded += len(batch_idx)
            continue
        result = _bulk_embed(texts)
        if result is None or result.shape[0] != len(batch_idx):
            builder.errors.append(
                f"embed batch starting at index {batch_idx[0]} failed; skipping"
            )
            continue
        for i, vec in zip(batch_idx, result):
            patterns[i]["embedding"] = [float(x) for x in vec]
            builder.patterns_embedded += 1

    # Now compute gated for everything
    _backfill_gated(patterns, view_registry, builder, noise_threshold, dry_run=dry_run)

    return builder.build()


def _backfill_gated(
    patterns: List[Dict],
    view_registry: ViewRegistry,
    builder: _BackfillBuilder,
    noise_threshold: float,
    dry_run: bool = False,
) -> None:
    """Fill `gated` field by comparing each pattern embedding to the noise centroid."""
    noise_centroid = view_registry.get_centroid("noise")
    if noise_centroid is None:
        builder.errors.append(
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
            builder.patterns_gated += 1
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
            builder.patterns_gated += 1


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
    builder = _BackfillBuilder()
    files = _iter_episode_files(log_dir, episodes_days)

    pending: List[Tuple[str, str, str]] = []  # (id, ts, text)
    for path in files:
        try:
            records = EpisodeLog.read_file(path)
        except OSError as exc:
            builder.errors.append(f"read failed for {path.name}: {exc}")
            continue
        for record in records:
            builder.episodes_total += 1
            eid = episode_id_for(record)
            if store.has(eid):
                builder.episodes_skipped += 1
                continue
            text = _summarize_for_embedding(record)
            if not text:
                continue
            pending.append((eid, record.get("ts", ""), text))

    if not pending:
        return builder.build()

    if dry_run:
        builder.episodes_embedded = len(pending)
        return builder.build()

    for batch_start in range(0, len(pending), EMBED_BATCH_SIZE):
        batch = pending[batch_start : batch_start + EMBED_BATCH_SIZE]
        texts = [t for _, _, t in batch]
        result = _bulk_embed(texts)
        if result is None or result.shape[0] != len(batch):
            builder.episodes_failed += len(batch)
            builder.errors.append(
                f"episode embed batch failed at item {batch_start}"
            )
            continue
        rows = [
            (eid, ts, vec)
            for (eid, ts, _), vec in zip(batch, result)
        ]
        store.upsert_many(rows)
        builder.episodes_embedded += len(rows)
        if progress is not None:
            progress(builder.episodes_embedded, len(pending))

    return builder.build()


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
    builder = _BackfillBuilder()

    # 1. Backup knowledge.json
    if not dry_run and knowledge_path.exists():
        builder.backup_path = backup_knowledge(knowledge_path)
        if builder.backup_path is not None:
            logger.info("Backed up knowledge.json → %s", builder.backup_path.name)

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
    _merge_pattern_stats(builder, pattern_stats)
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
        _merge_episode_stats(builder, episode_stats)
        logger.info(
            "episodes: %d total, %d newly embedded, %d skipped (already present), %d failed",
            episode_stats.episodes_total,
            episode_stats.episodes_embedded,
            episode_stats.episodes_skipped,
            episode_stats.episodes_failed,
        )

    builder.duration_seconds = time.time() - started
    return builder.build()


def _merge_pattern_stats(dst: _BackfillBuilder, src: BackfillStats) -> None:
    dst.patterns_total = src.patterns_total
    dst.patterns_embedded = src.patterns_embedded
    dst.patterns_gated = src.patterns_gated
    dst.patterns_skipped = src.patterns_skipped
    dst.errors.extend(src.errors)


def _merge_episode_stats(dst: _BackfillBuilder, src: BackfillStats) -> None:
    dst.episodes_total = src.episodes_total
    dst.episodes_embedded = src.episodes_embedded
    dst.episodes_skipped = src.episodes_skipped
    dst.episodes_failed = src.episodes_failed
    dst.errors.extend(src.errors)


# ============================================================
# ADR-0021: Pattern schema migration (provenance / bitemporal /
# forgetting / feedback). Additive and idempotent.
# ============================================================


@dataclass(frozen=True)
class Adr0021MigrationStats:
    patterns_total: int = 0
    patterns_updated: int = 0  # received at least one new field
    patterns_already_migrated: int = 0  # had all fields already
    backup_path: Optional[Path] = None
    errors: Tuple[str, ...] = ()


@dataclass
class _Adr0021MigrationBuilder:
    """Internal mutable accumulator for Adr0021MigrationStats."""

    patterns_total: int = 0
    patterns_updated: int = 0
    patterns_already_migrated: int = 0
    backup_path: Optional[Path] = None
    errors: List[str] = field(default_factory=list)

    def build(self) -> Adr0021MigrationStats:
        return Adr0021MigrationStats(
            patterns_total=self.patterns_total,
            patterns_updated=self.patterns_updated,
            patterns_already_migrated=self.patterns_already_migrated,
            backup_path=self.backup_path,
            errors=tuple(self.errors),
        )


def _ensure_adr0021_defaults(pattern: Dict) -> bool:
    """Add missing ADR-0021 fields with defaults. Returns True if mutated."""
    from .knowledge_store import DEFAULT_TRUST

    ts = now_iso()
    changed = False

    if "provenance" not in pattern:
        pattern["provenance"] = {"source_type": "unknown"}
        changed = True
    if "trust_score" not in pattern:
        pattern["trust_score"] = DEFAULT_TRUST
        changed = True
    if "trust_updated_at" not in pattern:
        pattern["trust_updated_at"] = ts
        changed = True
    if "valid_from" not in pattern:
        # Use distilled timestamp if it's a real ISO, else now
        distilled = pattern.get("distilled", "")
        pattern["valid_from"] = distilled if (
            isinstance(distilled, str) and distilled != "unknown" and distilled
        ) else ts
        changed = True
    if "valid_until" not in pattern:
        pattern["valid_until"] = None
        changed = True

    # ADR-0028: last_accessed_at / access_count / success_count /
    # failure_count retired. Strip them from legacy patterns if present
    # so the migration is net-reductive rather than just additive.
    for retired_field in (
        "last_accessed_at",
        "access_count",
        "success_count",
        "failure_count",
        "last_accessed",  # pre-ADR-0021 legacy spelling
    ):
        if retired_field in pattern:
            pattern.pop(retired_field)
            changed = True

    return changed


# ============================================================
# ADR-0026: Drop the ``category`` pattern field.
#
# Legacy rows may carry ``category: "noise"`` from pre-0019 LLM
# classification. Preserve that signal as ``gated = True`` before
# removing the field; other category values are semantically redundant
# with the view registry and are dropped outright.
# ============================================================


@dataclass(frozen=True)
class Adr0026MigrationStats:
    patterns_total: int = 0
    patterns_updated: int = 0  # had ``category`` removed
    patterns_gated_from_noise: int = 0  # legacy ``category == "noise"`` preserved as gated
    patterns_already_migrated: int = 0  # no ``category`` field in the first place
    backup_path: Optional[Path] = None
    errors: Tuple[str, ...] = ()


@dataclass
class _Adr0026MigrationBuilder:
    patterns_total: int = 0
    patterns_updated: int = 0
    patterns_gated_from_noise: int = 0
    patterns_already_migrated: int = 0
    backup_path: Optional[Path] = None
    errors: List[str] = field(default_factory=list)

    def build(self) -> Adr0026MigrationStats:
        return Adr0026MigrationStats(
            patterns_total=self.patterns_total,
            patterns_updated=self.patterns_updated,
            patterns_gated_from_noise=self.patterns_gated_from_noise,
            patterns_already_migrated=self.patterns_already_migrated,
            backup_path=self.backup_path,
            errors=tuple(self.errors),
        )


def drop_category_field(
    knowledge_path: Path,
    *,
    dry_run: bool = False,
) -> Adr0026MigrationStats:
    """Remove the ``category`` field from every pattern.

    Idempotent: running twice is a no-op. A pre-migration backup is
    created before any mutation. Patterns with ``category == "noise"``
    are preserved as ``gated = True`` (binary gate decision separate
    from the retired ternary label).

    Operates on the raw JSON to bypass ``KnowledgeStore.load``, which
    silently drops ``category`` on read since ADR-0026 — the migration
    needs to see the pre-migration state.
    """
    builder = _Adr0026MigrationBuilder()
    if not knowledge_path.exists():
        builder.errors.append(f"knowledge file not found: {knowledge_path}")
        return builder.build()

    try:
        raw_text = knowledge_path.read_text(encoding="utf-8")
    except OSError as exc:
        builder.errors.append(f"read failed: {exc}")
        return builder.build()

    try:
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        builder.errors.append(f"json parse failed: {exc}")
        return builder.build()

    if not isinstance(raw_data, list):
        builder.errors.append("knowledge.json is not a JSON array")
        return builder.build()

    builder.patterns_total = len(raw_data)

    for pattern in raw_data:
        if not isinstance(pattern, dict):
            continue
        if "category" not in pattern:
            builder.patterns_already_migrated += 1
            continue
        if pattern.get("category") == "noise" and not isinstance(pattern.get("gated"), bool):
            pattern["gated"] = True
            builder.patterns_gated_from_noise += 1
        del pattern["category"]
        builder.patterns_updated += 1

    if dry_run:
        return builder.build()

    if builder.patterns_updated == 0:
        return builder.build()

    builder.backup_path = backup_knowledge(knowledge_path)
    if builder.backup_path is not None:
        logger.info("Backed up knowledge.json → %s", builder.backup_path.name)

    knowledge_path.write_text(
        json.dumps(raw_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info(
        "ADR-0026 migration: %d/%d patterns updated (%d legacy noise → gated)",
        builder.patterns_updated,
        builder.patterns_total,
        builder.patterns_gated_from_noise,
    )

    return builder.build()


def migrate_patterns_to_adr0021(
    knowledge_path: Path,
    *,
    dry_run: bool = False,
) -> Adr0021MigrationStats:
    """Fill ADR-0021 fields on every pattern; strip ADR-0028-retired fields.

    Idempotent: running twice is a no-op. Backup is created before any
    mutation. ADR-0028 retired ``last_accessed_at`` / ``access_count`` /
    ``success_count`` / ``failure_count``; this migration now also
    removes those fields (and the pre-ADR-0021 ``last_accessed`` spelling)
    from legacy patterns.
    """
    from .knowledge_store import KnowledgeStore

    builder = _Adr0021MigrationBuilder()
    if not knowledge_path.exists():
        builder.errors.append(f"knowledge file not found: {knowledge_path}")
        return builder.build()

    if not dry_run:
        builder.backup_path = backup_knowledge(knowledge_path)
        if builder.backup_path is not None:
            logger.info("Backed up knowledge.json → %s", builder.backup_path.name)

    # Detect ADR-0028 strip-drift before KnowledgeStore.load drops the
    # retired fields from the in-memory representation. Counting at this
    # layer lets the migration report how many patterns actually change
    # on disk (additive fill + reductive strip), even though the strip
    # happens silently at load time.
    retired_fields = (
        "last_accessed_at",
        "access_count",
        "success_count",
        "failure_count",
        "last_accessed",
    )
    strip_drift = 0
    try:
        raw_text = knowledge_path.read_text(encoding="utf-8")
        raw_data = json.loads(raw_text) if raw_text.strip().startswith("[") else []
    except (OSError, json.JSONDecodeError):
        raw_data = []
    for raw_entry in raw_data:
        if isinstance(raw_entry, dict) and any(f in raw_entry for f in retired_fields):
            strip_drift += 1

    store = KnowledgeStore(path=knowledge_path)
    store.load()
    patterns = store.get_raw_patterns()
    builder.patterns_total = len(patterns)

    for pattern in patterns:
        if _ensure_adr0021_defaults(pattern):
            builder.patterns_updated += 1
        else:
            builder.patterns_already_migrated += 1

    # ADR-0028: if the on-disk file contained retired fields but every
    # pattern was otherwise fully migrated, the load-path strip is the
    # only change. Save unconditionally in that case so the file is
    # rewritten without the retired fields.
    needs_save = builder.patterns_updated > 0 or strip_drift > 0
    if not dry_run and needs_save:
        store.save()
        logger.info(
            "ADR-0021/0028 migration: %d/%d patterns updated (%d stripped of retired fields)",
            builder.patterns_updated, builder.patterns_total, strip_drift,
        )

    return builder.build()
