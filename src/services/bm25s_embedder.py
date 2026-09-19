"""
src/services/bm25s_embedder.py
NhÃ¡nh 2 (Sparse Vector): DÃ¹ng thÆ° viá»‡n bm25s (cháº¡y cá»±c nháº¹ trÃªn CPU local)
-> Chuyá»ƒn vÄƒn báº£n thÃ nh chá»‰ má»¥c cÃ¡c tá»« khÃ³a chÃ­nh xÃ¡c (indices vÃ  values) cho Qdrant Sparse Vector.
-> Há»— trá»£ lÆ°u vÃ  náº¡p tá»« Ä‘iá»ƒn tá»« disk Ä‘á»ƒ Ä‘áº£m báº£o token_id Ä‘á»“ng bá»™ giá»¯a Indexing vÃ  Querying.
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
        """
        Huáº¥n luyá»‡n mÃ´ hÃ¬nh BM25 trÃªn táº­p vÄƒn báº£n vÃ  trÃ­ch xuáº¥t Sparse Vector cho tá»«ng tÃ i liá»‡u.
        LÆ°u index vÃ  vocab náº¿u cÃ³ save_dir.
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
        """
        Náº¡p index vÃ  tá»« Ä‘iá»ƒn BM25 Ä‘Ã£ huáº¥n luyá»‡n tá»« disk.
        """
        try:
            self.retriever = bm25s.BM25.load(index_dir, load_corpus=False)
            self.vocab = self.retriever.vocab_dict
            self.index_dir = index_dir
        except Exception as e:
            print(f"[BM25SparseEmbedder] Lá»—i khi náº¡p index tá»« {index_dir}: {e}")

    def encode_query(self, query: str) -> Dict[str, Any]:
        """
        MÃ£ hÃ³a cÃ¢u truy váº¥n thÃ nh Sparse Vector theo Ä‘Ãºng token_id cá»§a tá»« Ä‘iá»ƒn.
        """
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
