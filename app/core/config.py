from __future__ import annotations

import os
from dataclasses import dataclass

from scripts.embedding.embed_recipes import EmbedConfig
from scripts.embedding.pg_dsn import resolve_pg_dsn


@dataclass(frozen=True)
class Settings:
    app_name: str
    db_dsn: str | None
    embedding_model_name: str
    embedding_model_path: str | None
    embedding_normalize: bool
    embedding_max_seq_length: int
    default_top_k: int
    max_message_chars: int
    eager_load_embedding_model: bool

    @classmethod
    def from_env(cls) -> "Settings":
        explicit_dsn = os.getenv("APP_PG_DSN")
        db_dsn = resolve_pg_dsn(explicit_dsn)
        return cls(
            app_name=os.getenv("APP_NAME", "Food Helper API"),
            db_dsn=db_dsn,
            embedding_model_name=os.getenv("EMBED_MODEL_NAME", EmbedConfig.model_name),
            embedding_model_path=os.getenv("EMBED_MODEL_PATH") or None,
            embedding_normalize=os.getenv("EMBED_NORMALIZE", "true").lower() != "false",
            embedding_max_seq_length=int(
                os.getenv("EMBED_MAX_SEQ_LENGTH", str(EmbedConfig.max_seq_length))
            ),
            default_top_k=int(os.getenv("DEFAULT_TOP_K", "5")),
            max_message_chars=int(os.getenv("MAX_MESSAGE_CHARS", "1000")),
            eager_load_embedding_model=os.getenv("EAGER_LOAD_EMBEDDING_MODEL", "false").lower()
            == "true",
        )
