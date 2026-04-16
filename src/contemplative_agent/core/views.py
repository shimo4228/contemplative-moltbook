"""Views: seed-text driven semantic queries over knowledge.json (ADR-0009).

A view is a named seed text plus retrieval parameters. Queries embed the
seed and rank patterns by cosine similarity. This replaces the discrete
``subcategory`` field — the categorisation axis is no longer baked into
state, it lives as data in ``config/views/`` (templates) or
``~/.config/moltbook/views/`` (user-customised).

Seed file format (Markdown with optional YAML frontmatter):

    ---
    threshold: 0.65                    # optional, default 0.0 (no filter)
    top_k: 50                          # optional, default None
    seed_from: ${CONSTITUTION_DIR}/*.md # optional, inject seed from external files
    ---

    # Optional title (ignored)

    Seed text body (used when seed_from is absent or resolves to nothing).

When ``seed_from`` is present, the referenced files' contents replace the
body as the embedded seed. ``${VAR}`` placeholders are substituted from
``path_vars`` passed to ``ViewRegistry``. The value may contain glob
wildcards (``*``, ``?``). Relative paths resolve against the view file's
directory. If resolution yields zero readable files, the body is used as
fallback.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import numpy as np

from .embeddings import cosine, embed_one
from .forgetting import compute_strength, is_live, mark_accessed

# ADR-0022 (IV-5) Hybrid Retrieval defaults
HYBRID_ALPHA_DEFAULT = 0.7   # cosine weight
HYBRID_BETA_DEFAULT = 0.3    # BM25 weight (normalized)
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    """Simple tokenizer for BM25: lowercase + unicode-word split."""
    return _TOKEN_RE.findall((text or "").lower())

logger = logging.getLogger(__name__)

# Cache embedded seeds per ViewRegistry instance to avoid re-embedding on
# every query. Cleared when load_views() is called again.
_DEFAULT_THRESHOLD = 0.0
_DEFAULT_TOP_K: Optional[int] = None


@dataclass(frozen=True)
class View:
    """A named semantic query over knowledge patterns.

    ``bm25_weight`` enables ADR-0022 hybrid retrieval. 0.0 disables the
    lexical channel for this view (pure cosine). Defaults to
    ``HYBRID_BETA_DEFAULT``; set explicitly in the view's YAML
    frontmatter to override.
    """

    name: str
    seed_text: str
    threshold: float = _DEFAULT_THRESHOLD
    top_k: Optional[int] = _DEFAULT_TOP_K
    bm25_weight: float = HYBRID_BETA_DEFAULT


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _substitute_vars(value: str, path_vars: Mapping[str, Path]) -> str:
    """Replace ``${VAR}`` placeholders using path_vars. Unknown vars stay literal."""
    def repl(m: "re.Match[str]") -> str:
        key = m.group(1)
        replacement = path_vars.get(key)
        return str(replacement) if replacement is not None else m.group(0)
    return _VAR_RE.sub(repl, value)


def _resolve_seed_from(
    pattern: str,
    view_path: Path,
    path_vars: Mapping[str, Path],
) -> Optional[str]:
    """Resolve a ``seed_from`` pattern to concatenated file contents.

    Returns ``None`` when no files match or all reads fail. Supports glob
    wildcards in the filename portion. Relative paths resolve against the
    view file's parent directory. ``${VAR}`` placeholders are substituted
    from ``path_vars``; unresolved placeholders cause fallback.
    """
    if "${" in pattern and _VAR_RE.search(pattern) is not None:
        substituted = _substitute_vars(pattern, path_vars)
        if "${" in substituted:
            logger.warning(
                "View %s: seed_from %r has unresolved placeholder — using body",
                view_path.name, pattern,
            )
            return None
    else:
        substituted = pattern

    p = Path(substituted)
    if not p.is_absolute():
        p = view_path.parent / p
    base = p.parent
    name = p.name
    try:
        matches = sorted(base.glob(name))
    except OSError as exc:
        logger.warning("View %s: seed_from glob failed: %s", view_path.name, exc)
        return None

    texts: List[str] = []
    for match in matches:
        try:
            body = match.read_text(encoding="utf-8").strip()
        except OSError as exc:
            logger.warning("View %s: seed_from read failed for %s: %s",
                           view_path.name, match, exc)
            continue
        if body:
            texts.append(body)

    if not texts:
        logger.warning(
            "View %s: seed_from %r resolved to no readable content — using body",
            view_path.name, pattern,
        )
        return None
    return "\n\n".join(texts)


def _parse_seed_file(
    path: Path,
    path_vars: Optional[Mapping[str, Path]] = None,
) -> View:
    """Parse a seed file into a View. Frontmatter is optional."""
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    threshold = _DEFAULT_THRESHOLD
    top_k: Optional[int] = _DEFAULT_TOP_K
    bm25_weight = HYBRID_BETA_DEFAULT
    seed_from: Optional[str] = None
    if match:
        front, body = match.group(1), match.group(2)
        for line in front.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key == "threshold":
                try:
                    threshold = float(value)
                except ValueError:
                    logger.warning("View %s: invalid threshold %r", path.name, value)
            elif key == "top_k":
                try:
                    top_k = int(value)
                except ValueError:
                    logger.warning("View %s: invalid top_k %r", path.name, value)
            elif key == "bm25_weight":
                try:
                    bm25_weight = max(0.0, min(1.0, float(value)))
                except ValueError:
                    logger.warning("View %s: invalid bm25_weight %r", path.name, value)
            elif key == "seed_from":
                seed_from = value
    else:
        body = raw

    seed_text = body.strip()
    if seed_from:
        injected = _resolve_seed_from(seed_from, path, path_vars or {})
        if injected is not None:
            seed_text = injected

    return View(
        name=path.stem,
        seed_text=seed_text,
        threshold=threshold,
        top_k=top_k,
        bm25_weight=bm25_weight,
    )


class ViewRegistry:
    """Loads view definitions from a directory and caches their embeddings."""

    def __init__(
        self,
        views_dir: Optional[Path] = None,
        path_vars: Optional[Mapping[str, Path]] = None,
    ) -> None:
        self._views_dir = views_dir
        self._path_vars: Mapping[str, Path] = path_vars or {}
        self._views: Dict[str, View] = {}
        self._centroids: Dict[str, np.ndarray] = {}
        self._loaded = False

    def load_views(self) -> Dict[str, View]:
        """Read all *.md files in views_dir into View instances.

        Returns the loaded views dict. Embedding of seed texts is
        deferred to first query (lazy) to avoid hitting Ollama during
        cold imports.
        """
        self._views = {}
        self._centroids = {}
        self._loaded = True
        if self._views_dir is None or not self._views_dir.exists():
            return {}
        for path in sorted(self._views_dir.glob("*.md")):
            try:
                view = _parse_seed_file(path, self._path_vars)
            except OSError as exc:
                logger.warning("Failed to read view %s: %s", path, exc)
                continue
            self._views[view.name] = view
        return dict(self._views)

    def names(self) -> List[str]:
        if not self._loaded:
            self.load_views()
        return sorted(self._views.keys())

    def get(self, name: str) -> Optional[View]:
        if not self._loaded:
            self.load_views()
        return self._views.get(name)

    def get_centroid(self, name: str) -> Optional[np.ndarray]:
        """Return the embedding of the view's seed text, embedding on first call."""
        if not self._loaded:
            self.load_views()
        cached = self._centroids.get(name)
        if cached is not None:
            return cached
        view = self._views.get(name)
        if view is None:
            return None
        emb = embed_one(view.seed_text)
        if emb is None:
            logger.warning("Failed to embed seed text for view %s", name)
            return None
        self._centroids[name] = emb
        return emb

    def find_by_view(
        self,
        view_name: str,
        candidates: List[Dict],
    ) -> List[Dict]:
        """Return patterns from ``candidates`` ranked by hybrid score.

        ADR-0022: score is ``α × cosine + β × bm25_norm`` where α, β come
        from the view (α implicit as ``1 - bm25_weight``). ``candidates``
        is a list of pattern dicts each containing an ``embedding`` field
        (List[float]). Patterns without embeddings are skipped silently.
        Applies the view's threshold (on raw cosine) and top_k.
        """
        view = self.get(view_name)
        if view is None:
            logger.warning("Unknown view: %s", view_name)
            return []
        seed_emb = self.get_centroid(view_name)
        if seed_emb is None:
            return []
        bm25_scores = _compute_bm25_scores(view.seed_text, candidates) if view.bm25_weight > 0 else None
        alpha = 1.0 - view.bm25_weight
        return self._rank(
            seed_emb, candidates, view.threshold, view.top_k,
            bm25_scores=bm25_scores, alpha=alpha, beta=view.bm25_weight,
        )

    def find_by_seed_text(
        self,
        seed: str,
        candidates: List[Dict],
        top_k: Optional[int] = None,
        threshold: float = _DEFAULT_THRESHOLD,
        bm25_weight: float = HYBRID_BETA_DEFAULT,
    ) -> List[Dict]:
        """Ad-hoc seed query without registering a view file."""
        seed_emb = embed_one(seed)
        if seed_emb is None:
            return []
        bm25_scores = _compute_bm25_scores(seed, candidates) if bm25_weight > 0 else None
        alpha = 1.0 - bm25_weight
        return self._rank(
            seed_emb, candidates, threshold, top_k,
            bm25_scores=bm25_scores, alpha=alpha, beta=bm25_weight,
        )

    @staticmethod
    def _rank(
        seed_emb: np.ndarray,
        candidates: List[Dict],
        threshold: float,
        top_k: Optional[int],
        *,
        mark_access: bool = True,
        bm25_scores: Optional[Mapping[int, float]] = None,
        alpha: float = 1.0,
        beta: float = 0.0,
    ) -> List[Dict]:
        """Rank candidates by ``(α·cosine + β·bm25_norm) × trust × strength``.

        ADR-0021 introduced the trust × strength multipliers on top of
        cosine. ADR-0022 adds an optional BM25 lexical channel blended
        linearly with cosine via (alpha, beta). Raw cosine is still used
        for the ``threshold`` gate so tuning stays semantic, not
        keyword-driven.

        ``bm25_scores`` maps ``id(pattern_dict) -> normalized BM25 score``
        (pre-computed by the caller via ``_compute_bm25_scores``). When
        ``bm25_scores`` is None or ``beta == 0``, falls back to the pure
        cosine behavior.
        """
        use_bm25 = bm25_scores is not None and beta > 0
        scored: List[tuple] = []
        for pat in candidates:
            emb = pat.get("embedding")
            if not emb:
                continue
            if not is_live(pat):
                continue
            vec = np.asarray(emb, dtype=np.float32)
            sim = cosine(seed_emb, vec)
            if sim < threshold:
                continue
            if use_bm25:
                bm = float((bm25_scores or {}).get(id(pat), 0.0))
                base = alpha * sim + beta * bm
            else:
                base = sim
            trust = float(pat.get("trust_score", 1.0))
            strength = compute_strength(pat)
            scored.append((base * trust * strength, sim, pat))
        scored.sort(key=lambda t: t[0], reverse=True)
        if top_k is not None:
            scored = scored[:top_k]
        result = [pat for _, _, pat in scored]
        if mark_access:
            for pat in result:
                mark_accessed(pat)
        return result


def _compute_bm25_scores(
    seed_text: str,
    candidates: List[Dict],
) -> Dict[int, float]:
    """Build a one-off BM25 index over candidates and score against ``seed_text``.

    Returns ``{id(pattern_dict): normalized_score}`` where normalization
    is min-max over the batch so the blended score sums stay in [0, 1].
    Patterns with empty text contribute a zero corpus entry (BM25 needs a
    position even if the row isn't meaningful); they never receive a
    non-zero BM25 score. Empty query returns all zeros.
    """
    from rank_bm25 import BM25Okapi  # local import: cheap, only on hybrid queries

    query_tokens = _tokenize(seed_text)
    if not query_tokens or not candidates:
        return {}

    corpus: List[List[str]] = []
    for pat in candidates:
        text = (pat.get("pattern", "") + " " + pat.get("distilled", "")).strip()
        tokens = _tokenize(text) or ["__empty__"]
        corpus.append(tokens)

    try:
        bm25 = BM25Okapi(corpus)
        raw_scores = bm25.get_scores(query_tokens)
    except Exception as exc:  # pragma: no cover — defensive; rank_bm25 is well-tested
        logger.warning("BM25 scoring failed: %s — disabling lexical channel", exc)
        return {}

    max_score = float(np.max(raw_scores)) if len(raw_scores) > 0 else 0.0
    if max_score <= 0.0:
        return {id(pat): 0.0 for pat in candidates}
    return {id(pat): float(raw_scores[i]) / max_score for i, pat in enumerate(candidates)}
