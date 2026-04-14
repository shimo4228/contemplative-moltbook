"""Local embedding interface via Ollama REST API.

Thin wrapper over Ollama's /api/embed endpoint plus utilities for
similarity, centroid, and argmax-based view assignment. Used by
stocktake, distill (dedup), and the views mechanism (ADR-0009) to
resolve semantic similarity that SequenceMatcher cannot detect
(structural similarity hidden by vocabulary variation).
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import requests

from .llm import _get_ollama_url

logger = logging.getLogger(__name__)

_DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_TIMEOUT_SECONDS = 60
EMBEDDING_DIM = 768  # nomic-embed-text dimension


def _get_embedding_model() -> str:
    return os.environ.get("OLLAMA_EMBEDDING_MODEL", _DEFAULT_EMBEDDING_MODEL)


def embed_texts(texts: List[str]) -> Optional[np.ndarray]:
    """Embed a list of texts using Ollama. Returns (N, D) float array or None.

    On any failure (network, model missing, malformed response), returns
    None — caller is expected to handle gracefully (skip similarity-based
    work).
    """
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)

    try:
        base_url = _get_ollama_url()
    except ValueError as exc:
        logger.error("Invalid Ollama URL for embedding: %s", exc)
        return None

    url = f"{base_url}/api/embed"
    payload = {
        "model": _get_embedding_model(),
        "input": texts,
    }
    try:
        response = requests.post(url, json=payload, timeout=EMBEDDING_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Embedding request failed: %s", exc)
        return None

    embeddings = data.get("embeddings")
    if not isinstance(embeddings, list) or not embeddings:
        logger.warning("Embedding response missing 'embeddings' field")
        return None

    try:
        return np.asarray(embeddings, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        logger.warning("Could not parse embeddings array: %s", exc)
        return None


def embed_one(text: str) -> Optional[np.ndarray]:
    """Embed a single text. Returns (D,) float vector or None."""
    result = embed_texts([text])
    if result is None or result.shape[0] == 0:
        return None
    return result[0]


def cosine(v1: np.ndarray, v2: np.ndarray) -> float:
    """Cosine similarity between two 1D vectors. Zero vectors → 0.0."""
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


def cosine_similarity_matrix(vectors: np.ndarray) -> np.ndarray:
    """Compute pairwise cosine similarity for an (N, D) array. Returns (N, N)."""
    if vectors.size == 0:
        return np.zeros((0, 0), dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # avoid divide-by-zero
    normalized = vectors / norms
    return normalized @ normalized.T


def find_similar(
    target: np.ndarray,
    candidates: List[np.ndarray],
    top_k: Optional[int] = None,
    threshold: Optional[float] = None,
) -> List[Tuple[int, float]]:
    """Return [(index, similarity), ...] sorted by similarity desc.

    Filters by threshold if given, then truncates to top_k if given.
    """
    if not candidates:
        return []
    sims = [(i, cosine(target, c)) for i, c in enumerate(candidates)]
    if threshold is not None:
        sims = [(i, s) for i, s in sims if s >= threshold]
    sims.sort(key=lambda t: t[1], reverse=True)
    if top_k is not None:
        sims = sims[:top_k]
    return sims


def centroid(vectors: List[np.ndarray]) -> Optional[np.ndarray]:
    """Mean vector. Returns None for empty input."""
    if not vectors:
        return None
    return np.mean(np.asarray(vectors, dtype=np.float32), axis=0)


def argmax_centroid(
    target: np.ndarray, centroids: Dict[str, np.ndarray]
) -> Optional[Tuple[str, float]]:
    """Return (best_key, similarity) for the centroid most similar to target.

    Returns None if centroids is empty.
    """
    if not centroids:
        return None
    best_key = ""
    best_sim = -float("inf")
    for key, c in centroids.items():
        s = cosine(target, c)
        if s > best_sim:
            best_sim = s
            best_key = key
    return best_key, best_sim
