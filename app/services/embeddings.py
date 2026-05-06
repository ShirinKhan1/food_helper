from __future__ import annotations

from sentence_transformers import SentenceTransformer

from app.core.config import Settings
from scripts.search.query_encode import encode_query, load_sentence_transformer, should_use_e5_prefix


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model: SentenceTransformer | None = None

    @property
    def model_name(self) -> str:
        return self._settings.embedding_model_name

    def maybe_preload(self) -> None:
        if self._settings.eager_load_embedding_model:
            self.get_model()

    def get_model(self) -> SentenceTransformer:
        if self._model is None:
            model_source = self._settings.embedding_model_path or self._settings.embedding_model_name
            model = load_sentence_transformer(model_source)
            model.max_seq_length = self._settings.embedding_max_seq_length
            self._model = model
        return self._model

    def encode_query(self, query: str) -> list[float]:
        model = self.get_model()
        vector = encode_query(
            model,
            query,
            normalize=self._settings.embedding_normalize,
            use_e5_prefix=should_use_e5_prefix(self._settings.embedding_model_name),
        )
        return vector.tolist()

    def health_status(self) -> str:
        return "loaded" if self._model is not None else "not_loaded"
