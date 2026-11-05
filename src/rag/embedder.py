"""Embedding backends. 'hash' is a dependency-free stand-in for tests; anything else is a sentence-transformers model."""
from __future__ import annotations

import hashlib
import re

import numpy as np

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class HashEmbedder:
    """Signed feature hashing of words. Deterministic, no downloads. For unit tests only."""
    dim = 512
    query_prefix = ""

    def encode(self, texts, batch_size: int = 32) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in re.findall(r"[a-z0-9]+", t.lower()):
                h = int(hashlib.md5(w.encode()).hexdigest(), 16)
                out[i, h % self.dim] += 1.0 if (h >> 64) & 1 else -1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms


class STEmbedder:
    def __init__(self, name: str):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(name)
        self.dim = self.model.get_sentence_embedding_dimension()
        self.query_prefix = BGE_QUERY_PREFIX if "bge" in name.lower() and "m3" not in name.lower() else ""

    def encode(self, texts, batch_size: int = 32) -> np.ndarray:
        return self.model.encode(list(texts), batch_size=batch_size, normalize_embeddings=True,
                                 show_progress_bar=len(texts) > 200)


def get_embedder(name: str):
    return HashEmbedder() if name == "hash" else STEmbedder(name)