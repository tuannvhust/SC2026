"""
src/services/bge_m3_service.py
Service sinh Dense và Sparse Vector embeddings từ mô hình BAAI/bge-m3.
Sử dụng FlagEmbedding hỗ trợ đa ngôn ngữ (rất mạnh cho tiếng Việt).
"""

import os
from typing import List, Dict, Any, Optional

class BGEM3Service:
    _instance = None
    _model = None

    def __init__(self, model_name_or_path: str = "BAAI/bge-m3", device: Optional[str] = None):
        self.model_name = model_name_or_path
        self.device = device or os.getenv("BGE_M3_DEVICE", "cpu")

    def _load_model(self):
        if self._model is None:
            print(f" Đang khởi tạo mô hình BGE-M3 ({self.model_name}) trên thiết bị '{self.device}'...")
            from FlagEmbedding import BGEM3FlagModel
            # use_fp16=True nếu chạy trên CUDA, False trên CPU
            use_fp16 = self.device == "cuda"
            self._model = BGEM3FlagModel(
                self.model_name,
                use_fp16=use_fp16,
                devices=self.device
            )
            print(" Khởi tạo mô hình BGE-M3 thành công!")
        return self._model

    def encode_documents(self, texts: List[str], batch_size: int = 12) -> List[Dict[str, Any]]:
        """
        Sinh đồng thời Dense vector (1024 dim) và Sparse vector (lexical weights) cho danh sách văn bản.
        """
        model = self._load_model()
        output = model.encode(
            texts,
            batch_size=batch_size,
            max_length=8192,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False
        )

        dense_vecs = output["dense_vecs"]
        lexical_weights = output["lexical_weights"]

        results = []
        for i in range(len(texts)):
            weights_dict = lexical_weights[i]
            # Chuyển đổi token keys thành int cho Qdrant SparseVector
            indices = [int(k) for k in weights_dict.keys()]
            values = [float(v) for v in weights_dict.values()]

            results.append({
                "dense": dense_vecs[i].tolist() if hasattr(dense_vecs[i], "tolist") else list(dense_vecs[i]),
                "sparse": {
                    "indices": indices,
                    "values": values
                }
            })
        return results

    def encode_query(self, query: str) -> Dict[str, Any]:
        """
        Sinh Dense và Sparse vector cho câu truy vấn tìm kiếm của người dùng.
        """
        results = self.encode_documents([query], batch_size=1)
        return results[0]

