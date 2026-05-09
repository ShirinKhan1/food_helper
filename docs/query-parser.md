# LLM Query Parser

Структурированный разбор пользовательского сообщения поверх эвристик: класс [`LLMQueryParser`](../app/services/llm/query_parser.py). Итог согласуется с rule-based ограничениями и интентом из [`IntentRouter`](../app/orchestrator/intent_router.py).

## Режим работы: `QUERY_PARSER_MODE`

Значения задаются в [`Settings`](../app/core/config.py):

| Значение | Поведение |
|----------|-----------|
| `rules` | Только правила, без вызова LLM (по умолчанию). |
| `llm` | Всегда пытаться вызвать LLM для парсинга (с откатом на rules при ошибке). |
| `auto` | LLM для «сложных» запросов по эвристикам внутри парсера; иначе rules. |

Чтобы LLM реально вызывался, нужно **`LLM_QUERY_PARSER_ENABLED=true`** и доступный провайдер (например Ollama в Docker, см. [local-llm.md](local-llm.md)).

## Основные переменные окружения

| Переменная | Назначение |
|------------|------------|
| `QUERY_PARSER_MODE` | `rules` / `llm` / `auto` |
| `LLM_QUERY_PARSER_ENABLED` | Включить LLM-слой парсера |
| `LLM_QUERY_PARSER_PROVIDER` | Например `ollama` |
| `LLM_QUERY_PARSER_MODEL` | Имя модели |
| `LLM_QUERY_PARSER_TIMEOUT_SECONDS` | Таймаут HTTP к LLM |
| `LLM_QUERY_PARSER_CONFIDENCE_THRESHOLD` | Порог уверенности; ниже — усиление fallback |
| `LLM_QUERY_PARSER_POSTCHECK_ENABLED` | Пост-проверка результата парсера |
| `LLM_QUERY_PARSER_LOG_PROMPTS` / `LLM_QUERY_PARSER_LOG_RESPONSES` | Логирование для отладки |
| `QUERY_PARSER_RECENT_MESSAGES_LIMIT` | Сколько последних сообщений учитывать в промпте |
| `CLARIFICATION_ENABLED` | Запрос уточнений при неоднозначности |
| `CLARIFICATION_MAX_QUESTION_CHARS` | Ограничение длины вопроса пользователю |

Температура, `max_tokens`, `num_ctx` для парсера — отдельные переменные `LLM_QUERY_PARSER_*` (см. `Settings.from_env` в [`config.py`](../app/core/config.py)).

## Связь с ответом чата

Парсер влияет на нормализацию запроса и ограничения до поиска; финальный текст ответа пользователю задаётся [`AnswerGenerator`](../app/services/answer_generator.py) и режимом `ANSWER_MODE` (см. [llm-answer-generator-mvp.md](llm-answer-generator-mvp.md)).
