# LLM Answer Generator MVP

## Принцип

- Deterministic pipeline остается источником истины.
- LLM влияет только на `ChatResponse.answer`.
- Любая ошибка LLM приводит к безопасному fallback.

## Режимы

- `ANSWER_MODE=template`: LLM не вызывается.
- `ANSWER_MODE=llm`: LLM вызывается всегда при наличии контекста.
- `ANSWER_MODE=auto`: LLM вызывается только для allowlist-сценариев и валидного контекста.

## Debug-поля

При `include_debug=true` добавляется `debug.llm`:

- `used_llm`
- `fallback_reason`
- `latency_ms`
- `postcheck_passed`
- `postcheck_errors`

## Post-check MVP

- пустой/слишком длинный ответ отклоняется;
- удаляются `<think>...</think>` при включенном `LLM_STRIP_THINK_TAGS`;
- блокируются медицинские гарантии;
- блокируются неизвестные recipe titles в list-сценариях;
- в nutrition strict-mode блокируются неизвестные числовые значения.
