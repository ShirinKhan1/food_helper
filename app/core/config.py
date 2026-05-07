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
    llm_enabled: bool
    llm_provider: str
    llm_model: str
    llm_base_url: str
    llm_timeout_seconds: float
    llm_temperature: float
    llm_max_tokens: int
    llm_num_ctx: int
    llm_think: bool
    answer_mode: str
    llm_postcheck_enabled: bool
    llm_strict_context: bool
    llm_log_prompts: bool
    llm_log_responses: bool
    llm_min_recipes_for_list_answer: int
    llm_max_context_recipes: int
    llm_max_context_ingredients: int
    llm_max_context_steps: int
    llm_max_answer_chars: int
    llm_strip_think_tags: bool
    query_parser_mode: str
    llm_query_parser_enabled: bool
    llm_query_parser_provider: str
    llm_query_parser_model: str
    llm_query_parser_temperature: float
    llm_query_parser_max_tokens: int
    llm_query_parser_num_ctx: int
    llm_query_parser_timeout_seconds: float
    llm_query_parser_confidence_threshold: float
    llm_query_parser_postcheck_enabled: bool
    llm_query_parser_log_prompts: bool
    llm_query_parser_log_responses: bool
    query_parser_recent_messages_limit: int
    clarification_enabled: bool
    clarification_max_question_chars: int

    @classmethod
    def from_env(cls) -> "Settings":
        explicit_dsn = os.getenv("APP_PG_DSN")
        db_dsn = resolve_pg_dsn(explicit_dsn)
        answer_mode = os.getenv("ANSWER_MODE", "auto")
        if answer_mode not in {"template", "llm", "auto"}:
            raise ValueError("ANSWER_MODE must be one of: template, llm, auto")
        query_parser_mode = os.getenv("QUERY_PARSER_MODE", "rules")
        if query_parser_mode not in {"rules", "llm", "auto"}:
            raise ValueError("QUERY_PARSER_MODE must be one of: rules, llm, auto")
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
            llm_enabled=os.getenv("LLM_ENABLED", "false").lower() == "true",
            llm_provider=os.getenv("LLM_PROVIDER", "none"),
            llm_model=os.getenv("LLM_MODEL", "qwen3:4b"),
            llm_base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434"),
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "90")),
            llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "500")),
            llm_num_ctx=int(os.getenv("LLM_NUM_CTX", "4096")),
            llm_think=os.getenv("LLM_THINK", "false").lower() == "true",
            answer_mode=answer_mode,
            llm_postcheck_enabled=os.getenv("LLM_POSTCHECK_ENABLED", "true").lower() == "true",
            llm_strict_context=os.getenv("LLM_STRICT_CONTEXT", "true").lower() == "true",
            llm_log_prompts=os.getenv("LLM_LOG_PROMPTS", "false").lower() == "true",
            llm_log_responses=os.getenv("LLM_LOG_RESPONSES", "false").lower() == "true",
            llm_min_recipes_for_list_answer=int(
                os.getenv("LLM_MIN_RECIPES_FOR_LIST_ANSWER", "1")
            ),
            llm_max_context_recipes=int(os.getenv("LLM_MAX_CONTEXT_RECIPES", "5")),
            llm_max_context_ingredients=int(
                os.getenv("LLM_MAX_CONTEXT_INGREDIENTS", "30")
            ),
            llm_max_context_steps=int(os.getenv("LLM_MAX_CONTEXT_STEPS", "20")),
            llm_max_answer_chars=int(os.getenv("LLM_MAX_ANSWER_CHARS", "2500")),
            llm_strip_think_tags=os.getenv("LLM_STRIP_THINK_TAGS", "true").lower() == "true",
            query_parser_mode=query_parser_mode,
            llm_query_parser_enabled=os.getenv("LLM_QUERY_PARSER_ENABLED", "false").lower() == "true",
            llm_query_parser_provider=os.getenv("LLM_QUERY_PARSER_PROVIDER", "ollama"),
            llm_query_parser_model=os.getenv("LLM_QUERY_PARSER_MODEL", "qwen3:4b"),
            llm_query_parser_temperature=float(os.getenv("LLM_QUERY_PARSER_TEMPERATURE", "0")),
            llm_query_parser_max_tokens=int(os.getenv("LLM_QUERY_PARSER_MAX_TOKENS", "700")),
            llm_query_parser_num_ctx=int(os.getenv("LLM_QUERY_PARSER_NUM_CTX", "4096")),
            llm_query_parser_timeout_seconds=float(os.getenv("LLM_QUERY_PARSER_TIMEOUT_SECONDS", "15")),
            llm_query_parser_confidence_threshold=float(
                os.getenv("LLM_QUERY_PARSER_CONFIDENCE_THRESHOLD", "0.65")
            ),
            llm_query_parser_postcheck_enabled=os.getenv(
                "LLM_QUERY_PARSER_POSTCHECK_ENABLED", "true"
            ).lower()
            == "true",
            llm_query_parser_log_prompts=os.getenv("LLM_QUERY_PARSER_LOG_PROMPTS", "false").lower()
            == "true",
            llm_query_parser_log_responses=os.getenv("LLM_QUERY_PARSER_LOG_RESPONSES", "false").lower()
            == "true",
            query_parser_recent_messages_limit=int(
                os.getenv("QUERY_PARSER_RECENT_MESSAGES_LIMIT", "6")
            ),
            clarification_enabled=os.getenv("CLARIFICATION_ENABLED", "true").lower() == "true",
            clarification_max_question_chars=int(
                os.getenv("CLARIFICATION_MAX_QUESTION_CHARS", "250")
            ),
        )
