"""Local embedding interface via Ollama REST API.

Thin wrapper over Ollama's /api/embed endpoint, mirroring llm.py's URL
resolution and trust model. Used by stocktake to compute semantic
similarity between skill/rule bodies that SequenceMatcher cannot detect
(structural similarity hidden by vocabulary variation).
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

import numpy as np
import requests

from .llm import _get_ollama_url

logger = logging.getLogger(__name__)

_DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_TIMEOUT_SECONDS = 60


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


def cosine_similarity_matrix(vectors: np.ndarray) -> np.ndarray:
    """Compute pairwise cosine similarity for an (N, D) array. Returns (N, N)."""
    if vectors.size == 0:
        return np.zeros((0, 0), dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # avoid divide-by-zero
    normalized = vectors / norms
    return normalized @ normalized.T
