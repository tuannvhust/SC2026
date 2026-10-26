"""
src/services/bm25s_embedder.py
Sparse vector embedding service using bm25s on the local CPU.
Converts text into lexical indices and values for Qdrant sparse vectors.
Supports saving and loading the vocabulary to keep token IDs consistent.
"""

import os
from typing import List, Dict, Any, Optional
import bm25s


class BM25SparseEmbedder:
    def __init__(self, index_dir: Optional[str] = None):
        self.retriever = None
        self.vocab = {}
        self.index_dir = index_dir

        if self.index_dir and os.path.exists(self.index_dir):
            self.load(self.index_dir)

    def fit_corpus(self, corpus: List[str], save_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fit BM25 to a corpus and create a sparse vector for each document.

        Save the index and vocabulary when save_dir is provided.
        """
        corpus_tokens = bm25s.tokenize(corpus, show_progress=False)
        self.retriever = bm25s.BM25()
        self.retriever.index(corpus_tokens, show_progress=False)
        self.vocab = self.retriever.vocab_dict

        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
            self.retriever.save(save_dir)
            self.index_dir = save_dir

        num_docs = len(corpus)
        doc_vectors = [{"indices": [], "values": []} for _ in range(num_docs)]

        indptr = self.retriever.scores["indptr"]
        data = self.retriever.scores["data"]
        indices = self.retriever.scores["indices"]

        for term, token_id in self.vocab.items():
            if token_id >= len(indptr):
                continue
            start = indptr[token_id]
            end = indptr[token_id + 1] if token_id + 1 < len(indptr) else len(data)

            doc_ids = indices[start:end]
            scores = data[start:end]

            for doc_id, score in zip(doc_ids, scores):
                if score > 0:
                    doc_vectors[doc_id]["indices"].append(int(token_id))
                    doc_vectors[doc_id]["values"].append(float(score))

        return doc_vectors

    def load(self, index_dir: str):
        """Load a trained BM25 index and vocabulary from disk."""
        try:
            self.retriever = bm25s.BM25.load(index_dir, load_corpus=False)
            self.vocab = self.retriever.vocab_dict
            self.index_dir = index_dir
        except Exception as e:
            print(f"[BM25SparseEmbedder] Failed to load index from {index_dir}: {e}")

    def encode_query(self, query: str) -> Dict[str, Any]:
        """Encode a query using token IDs from the fitted vocabulary."""
        if not self.vocab:
            return {"indices": [], "values": []}

        tokenized = bm25s.tokenize([query], return_ids=False, show_progress=False)
        tokens = tokenized[0] if len(tokenized) > 0 else []

        indices = []
        values = []
        seen = set()

        for tok in tokens:
            if tok in self.vocab and tok not in seen:
                seen.add(tok)
                token_id = self.vocab[tok]
                indices.append(int(token_id))
                values.append(1.0)

        return {"indices": indices, "values": values}
