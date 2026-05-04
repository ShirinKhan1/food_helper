"""Кодирование текстового запроса в вектор (SentenceTransformers, префикс E5)."""
from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer


def reset_hf_http_session() -> None:
    try:
        from huggingface_hub import close_session

        close_session()
        return
    except Exception:
        pass

    try:
        from huggingface_hub.utils._http import reset_sessions  # type: ignore

        reset_sessions()
    except Exception:
        pass


def _is_closed_client_error(e: Exception) -> bool:
    return "client has been closed" in str(e).lower()


def retry_once_on_closed_client(fn):
    try:
        return fn()
    except RuntimeError as e:
        if _is_closed_client_error(e):
            reset_hf_http_session()
            return fn()
        raise


def should_use_e5_prefix(model_name: str) -> bool:
    m = model_name.lower()
    return "e5" in m and ("intfloat/" in m or "e5-" in m)


def encode_query(
    model: SentenceTransformer,
    query: str,
    *,
    normalize: bool,
    use_e5_prefix: bool,
) -> np.ndarray:
    text = f"query: {query}" if use_e5_prefix else query
    vec = model.encode([text], normalize_embeddings=normalize, show_progress_bar=False)[0]
    return np.asarray(vec, dtype=np.float32)


def load_sentence_transformer(model_name: str) -> SentenceTransformer:
    reset_hf_http_session()
    return retry_once_on_closed_client(
        lambda: SentenceTransformer(model_name, device="cpu")
    )
