"""RAG retrieval over knowledge/invariants.md.

Uses sentence-transformers embeddings if installed (better), else a simple bag-of-words
cosine fallback so the project still runs anywhere. Tell which one was used in your README.
"""
import math
import re
from collections import Counter
from pathlib import Path

KB = Path(__file__).resolve().parent.parent / "knowledge" / "invariants.md"


def load_invariants(path: Path = KB) -> list[str]:
    return [ln[2:].strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.startswith("- ")]


def _tok(t: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", t.lower())


class Retriever:
    def __init__(self, docs: list[str] | None = None):
        self.docs = docs or load_invariants()
        self.backend = "bow"
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
            self._np = np
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            self._emb = self._model.encode(self.docs, normalize_embeddings=True)
            self.backend = "sentence-transformers"
        except Exception:
            self._vecs = [Counter(_tok(d)) for d in self.docs]

    @staticmethod
    def _cos(a: Counter, b: Counter) -> float:
        num = sum(a[k] * b.get(k, 0) for k in a)
        den = math.sqrt(sum(x * x for x in a.values())) * math.sqrt(sum(x * x for x in b.values()))
        return num / den if den else 0.0

    def search(self, query: str, k: int = 5) -> list[str]:
        if self.backend == "sentence-transformers":
            q = self._model.encode([query], normalize_embeddings=True)[0]
            scores = self._emb @ q
            idx = self._np.argsort(-scores)[:k]
            return [self.docs[int(i)] for i in idx]
        q = Counter(_tok(query))
        ranked = sorted(range(len(self.docs)), key=lambda i: -self._cos(q, self._vecs[i]))
        return [self.docs[i] for i in ranked[:k]]
