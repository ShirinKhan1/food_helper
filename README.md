# Food Helper

`food_helper` - API-сервис для рецептов с гибридным поиском (векторный + keyword), базовыми ограничениями по запросу и чат-эндпоинтом для оркестрации ответа.

Проект состоит из:
- Postgres + `pgvector` для хранения рецептов и эмбеддингов;
- сервисов поиска и оркестрации в `app/`;
- утилит загрузки/эмбеддингов в `scripts/`;
- Docker-сборки для `db`, `loader`, `embed`, `api`.

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

### 4) Запустить API

```bash
docker compose up -d api
```

Проверка здоровья:

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

## API эндпоинты

- `GET /health` - статус сервиса, БД и embedding-модели.
- `POST /v1/chat` - основной чатовый запрос (оркестратор + поиск).
- `POST /v1/search/debug` - отладочный ответ поиска (нормализованный запрос, constraints, кандидаты).
- `GET /v1/recipes/{recipe_id}` - получить подробности рецепта по ID.

Примеры запросов: [docs/api-test-requests.md](docs/api-test-requests.md).

## Тесты

```bash
pytest -q
```

Минимальный smoke-набор API находится в `tests/test_api.py`.

## Структура репозитория

| Путь | Назначение |
|------|------------|
| [app/](app/) | FastAPI-приложение, роуты, схемы, оркестратор, сервисы |
| [db/](db/) | Инициализация схемы БД и SQL-миграции |
| [docker/](docker/) | Dockerfile'ы для API и embedding-контейнера |
| [scripts/](scripts/) | Загрузка данных, эмбеддинги, утилиты поиска |
| [pipeline/](pipeline/) | Сбор/парсинг исходных рецептов |
| [data/](data/) | Справочные JSON (алиасы, группы ингредиентов, substitutions) |
| [docs/](docs/) | Документация по запуску, API и архитектуре |
| [tests/](tests/) | Unit/API тесты |

## Полезные заметки

- Если база была создана до добавления новой схемы, может потребоваться ручная миграция из `db/migrations/`.
- Если API недоступен из-за БД, проверьте `docker compose ps` и `docker compose logs db`.
