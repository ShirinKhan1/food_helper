# Food Helper

`food_helper` - API-сервис для рецептов с гибридным поиском (векторный + keyword), структурированными ограничениями по запросу и чат-эндпоинтом для deterministic-first оркестрации ответа.

Проект состоит из:
- Postgres + `pgvector` для хранения рецептов и эмбеддингов;
- сервисов поиска и оркестрации в `app/`;
- фронтенда MVP в `web/` (Next.js, чат, email/password, история чатов);
- утилит загрузки/эмбеддингов в `scripts/`;
- Docker-сборки для `db`, `loader`, `embed`, `api`, **`web`** (Next.js в контейнере).

Подробности по Compose-профилям и контейнерам: [docs/docker-compose.md](docs/docker-compose.md).  
Архитектурные заметки и контекст RAG: [docs/food_helper_rag_tz.md](docs/food_helper_rag_tz.md).

## Быстрый старт (Docker)

### 1) Поднять базу

```bash
docker compose up -d db
```

По умолчанию база доступна на `localhost:5433` (`food_helper`, user `food`, password `foodpass`).

### 2) Загрузить рецепты из `recipes.jsonl`

```bash
docker compose --profile load run --rm loader
```

### 3) Построить эмбеддинги

```bash
docker compose --profile embed run --rm embed python scripts/embedding/embed_recipes.py --from-db --only-missing --db-fetch-batch 500
```

### 4) Запустить API и веб-интерфейс

```bash
docker compose build api web
docker compose up -d db ollama api web
```

Сайт в браузере: **[http://localhost:3000/](http://localhost:3000/)** — один адрес; запросы к API идут через прокси внутри Docker (порт **8000** снаружи можно не открывать, но он проброшен для отладки).

Проверка API (опционально):

```bash
curl http://localhost:8000/health
```

## Локальный запуск API (без Docker для приложения)

Если БД уже поднята, API можно запустить локально:

```bash
pip install -r requirements-api.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Важно: при первом запуске модель эмбеддингов может загружаться дольше обычного.

### Миграция БД (пользователи и привязка чатов)

Если том Postgres уже создан со старой схемой, примените SQL вручную:

```bash
docker compose exec -T db psql -U food -d food_helper -f - < db/migrations/manual_users_and_chat_sessions.sql
```

Для новых томов актуальная схема уже в [`db/init/01_schema.sql`](db/init/01_schema.sql).

Переменные окружения для JWT и CORS (локально можно оставить значения по умолчанию из `Settings.from_env`, кроме секрета в продакшене):

- `AUTH_SECRET_KEY` — секрет подписи JWT (в продакшене задайте длинную случайную строку);
- `AUTH_COOKIE_SECURE` — `true` за HTTPS;
- `FRONTEND_ORIGIN` — origin фронта, например `http://localhost:3000` (CORS + cookie).

## Веб-сайт (интерфейс Food Helper)

Код фронта в каталоге [`web/`](web/).

### Вариант A — всё в Docker (одна ссылка)

После `docker compose up -d ...` с сервисом **`web`** откройте в браузере:

| Страница | URL |
|----------|-----|
| **Главная — чат** | [http://localhost:3000/](http://localhost:3000/) |
| Вход | [http://localhost:3000/login](http://localhost:3000/login) |
| Регистрация | [http://localhost:3000/register](http://localhost:3000/register) |
| Чат по id | `http://localhost:3000/chat/<conversation_id>` |

В контейнере `web` фронт обращается к API **по относительным путям** `/v1/...`: Next.js проксирует их на сервис `api` (`API_PROXY_TARGET` при сборке образа). Cookie авторизации остаются на том же origin (`localhost:3000`), CORS для браузера не нужен.

Пересборка только фронта после правок в `web/`:

```bash
docker compose build web && docker compose up -d web
```

### Вариант B — фронт локально (`npm run dev`), API в Docker

Тогда в `web/.env.local` задайте прямой URL API:

```bash
cd web
copy .env.example .env.local
npm install
npm run dev
```

В [`web/.env.example`](web/.env.example) по умолчанию **`NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`**. Для `npm run dev` **не** задавайте `API_PROXY_TARGET` (он только для сборки Docker-образа).

Если подняли Next на другом порту, выставьте у API **`FRONTEND_ORIGIN`** на этот origin (например `http://localhost:3001`).

Проверка типов фронта: `npm run test` (`tsc --noEmit`).

### Поведение

**Без входа** — чат на главной, без истории. **После регистрации/входа** — сайдбар с чатами, «Новый чат», открытие старых диалогов.

## API эндпоинты

- `GET /health` - статус сервиса, БД и embedding-модели.
- `POST /v1/chat` - основной чатовый запрос (оркестратор + поиск).
- `POST /v1/search/debug` - отладочный ответ поиска (нормализованный запрос, constraints, кандидаты).
- `GET /v1/recipes/{recipe_id}` - получить подробности рецепта по ID.
- `POST /v1/auth/register`, `POST /v1/auth/login`, `POST /v1/auth/logout`, `GET /v1/auth/me` — регистрация, вход, cookie JWT;
- `GET /v1/chats`, `GET /v1/chats/{id}`, `PATCH /v1/chats/{id}`, `DELETE /v1/chats/{id}` — история чатов (только для авторизованного пользователя).

Примеры запросов: [docs/api-test-requests.md](docs/api-test-requests.md).

## Ключевые chat-сценарии

- `search_recipes` / `recommend_recipes`: подбор рецептов с учетом `include/exclude` ограничений, калорийности, времени и сложности.
- `nutrition_question`:  
  - по выбранному рецепту — вернуть КБЖУ по конкретному блюду;  
  - по запросу вида `... в рецепте с курицей` — вернуть список рецептов и числовые значения КБЖУ по каждому найденному.
- `ingredient_substitution`: замена ингредиента в выбранном/найденном рецепте.
- `general_substitution`: общая замена ингредиента без привязки к рецепту (`substitution_catalog`).
- Hard filters: исключения и аллергены применяются к `final_results`, включая аллергенные характеристики рецепта (например, `Аллергены -> Злаки`).

## Тесты

```bash
python -m pytest -q
```

Офлайн-прогон набора для парсера запросов (правила + согласованность с `LLMQueryParser` в режиме без вызова LLM):

```bash
python scripts/eval/run_query_parser_eval.py
```

## LLM Query Parser (v1)

Поверх rule-based разбора опционально вызывается LLM как структурный парсер запроса (см. [docs/food_helper_llm_query_parser_v1_tz.md](docs/food_helper_llm_query_parser_v1_tz.md)).

По умолчанию парсер **выключен** (поведение как до v1). Чтобы включить локально при работающем Ollama:

| Переменная | Пример для разработки |
|------------|------------------------|
| `QUERY_PARSER_MODE` | `auto` или `llm` |
| `LLM_QUERY_PARSER_ENABLED` | `true` |
| `LLM_QUERY_PARSER_MODEL` | `qwen3:4b` |
| `LLM_QUERY_PARSER_TIMEOUT_SECONDS` | `15` |
| `LLM_QUERY_PARSER_CONFIDENCE_THRESHOLD` | `0.65` |
| `CLARIFICATION_ENABLED` | `true` |

Режимы `QUERY_PARSER_MODE`: `rules` (без LLM), `llm` (всегда вызывать LLM с fallback на rules), `auto` (эвристики «сложного» запроса).

## Структура репозитория

| Путь | Назначение |
|------|------------|
| [app/](app/) | FastAPI-приложение, роуты, схемы, оркестратор, сервисы |
| [db/](db/) | Инициализация схемы БД и SQL-миграции |
| [docker/](docker/) | Dockerfile'ы для API, embedding-контейнера и **веб-UI** (`Dockerfile.web`) |
| [scripts/](scripts/) | Загрузка данных, эмбеддинги, утилиты поиска |
| [pipeline/](pipeline/) | Сбор/парсинг исходных рецептов |
| [data/](data/) | Справочные JSON (алиасы, группы ингредиентов, substitutions) |
| [docs/](docs/) | Документация по запуску, API и архитектуре |
| [web/](web/) | Веб-интерфейс (Next.js): чат, вход, история чатов |
| [tests/](tests/) | Unit/API тесты |

## Полезные заметки

- Если база была создана до добавления новой схемы, может потребоваться ручная миграция из `db/migrations/`.
- Если API недоступен из-за БД, проверьте `docker compose ps` и `docker compose logs db`.
