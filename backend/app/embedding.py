"""Mô hình embedding bge-m3: nạp một lần, dùng lại cho mọi câu hỏi."""

import os
from functools import lru_cache

from app.config import get_settings


@lru_cache
def get_model():
    s = get_settings()
    # Biến môi trường phải đặt trước khi import sentence_transformers / transformers.
    if s.hf_home:
        os.environ.setdefault("HF_HOME", s.hf_home)
    if s.disable_safetensors_conversion:
        os.environ.setdefault("DISABLE_SAFETENSORS_CONVERSION", "true")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(s.embedding_model, device="cpu")
    model.max_seq_length = s.embedding_max_seq_length
    return model


def embed_query(text: str) -> list[float]:
    """Câu hỏi → vector đã chuẩn hoá (cùng cách chuẩn hoá với lúc lập chỉ mục)."""
    return get_model().encode([text], normalize_embeddings=True)[0].tolist()
