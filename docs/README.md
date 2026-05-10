# Документация Food Helper

Справочные материалы по проекту (не ТЗ). Короткий обзор сервиса и запуск — в [README.md](../README.md) в корне репозитория.

| Файл | Содержание |
|------|------------|
| [architecture.md](architecture.md) | Пайплайн чата, интенты, связь модулей `app/`. |
| [query-parser.md](query-parser.md) | Режимы LLM-парсера запроса и переменные окружения. |
| [event-menu.md](event-menu.md) | Событийное меню: профиль события, поиск, меню. |
| [docker-compose.md](docker-compose.md) | Сервисы Compose, профили, пересборка, типичные команды. |
| [local-llm.md](local-llm.md) | Ollama в Docker и на хосте для ответов и парсера. |
| [model-integration.md](model-integration.md) | Сервис `model` (Transformers + PEFT), `peft_http`, переменные и откат. |
| [model-artifacts.md](model-artifacts.md) | Контрольные суммы адаптера и расположение файлов. |
| [llm-answer-generator-mvp.md](llm-answer-generator-mvp.md) | Режимы `ANSWER_MODE`, post-check, debug-поля. |
| [api-test-requests.md](api-test-requests.md) | Ручные проверки API (Postman/curl). |
