В планах сделать RAG-систему по рецептам. Где модельку спрашиваем, что да как а он из базы понимает надо ли подтягивать инфу или нет. Отвечает на то, что спросил пользователь.

Пошаговый план и БФТ: [docs/plan.md](docs/plan.md). Docker Compose (профили, `food_helper`, секреты): [docs/docker-compose.md](docs/docker-compose.md).

## Структура репозитория

| Путь | Назначение |
|------|------------|
| [db/](db/) | Схема Postgres + pgvector, миграции (фаза 0) |
| [docker/](docker/) | `Dockerfile` (loader) и `Dockerfile.embed` |
| [pipeline/](pipeline/) | Парсинг food.ru → `recipes.jsonl` (до БД) |
| [data/](data/) | Справочные JSON (категории и подкатегории) |
| [scripts/ingest/](scripts/ingest/) | Загрузка JSONL в Postgres |
| [scripts/embedding/](scripts/embedding/) | Эмбеддинги в БД, проверка `recipe_embeddings` |
| [scripts/search/](scripts/search/) | Офлайн поиск по JSON с векторами (часто `archive/embeddings.json`) |
| [archive/](archive/) | Неактивные артефакты: старый дамп векторов, кэш парсера, логи — см. [archive/README.md](archive/README.md) |
| [docs/](docs/) | План, [docker-compose.md](docs/docker-compose.md), прочее |
| [tests/](tests/) | Тесты |

Корень: `docker-compose.yaml`, `requirements.txt`, `requirements-embed.txt`, рабочий **`recipes.jsonl`** для loader. Для `search_recipes.py` без пересчёта эмбеддингов можно указать `--embeddings archive/embeddings.json`.

## Данные и векторы (фаза 0)

1. Поднять БД: `docker compose up -d db` (порт с хоста по умолчанию **5433**).
2. Загрузить JSONL: `docker compose --profile load run --rm loader` (путь к файлу в `docker-compose.yaml`).
3. Заполнить **`recipe_embeddings`** (после шага 2), варианты:

   **Через Docker** (модель скачается в том `huggingface_cache`, первый прогон долгий) — явная команда, см. [docs/docker-compose.md](docs/docker-compose.md):

   `docker compose --profile embed run --rm embed python scripts/embedding/embed_recipes.py --from-db --only-missing --db-fetch-batch 500`

   **Локально:** `pip install -r requirements-embed.txt`, затем:

   `python scripts/embedding/embed_recipes.py --from-db --only-missing --pg-dsn "postgresql://food:foodpass@127.0.0.1:5433/food_helper"`

   Либо из файла в JSON и в БД: `python scripts/embedding/embed_recipes.py --input recipes.jsonl --output embeddings.json --pg-dsn "..."`.

Если том `pgdata` уже был создан до появления pgvector-таблицы, примените вручную [db/migrations/manual_pgvector_embeddings.sql](db/migrations/manual_pgvector_embeddings.sql). Проверка счётчиков: `python scripts/embedding/check_embedding_integrity.py --pg-dsn "..."`.

## Пайплайн парсинга (каталог food.ru)

Из корня репозитория:

- `python pipeline/parse_category.py` — обновить `data/categories_and_subcategories.json`
- `python pipeline/foodru_pipeline.py ...` — сбор `recipes.jsonl` (см. аргументы в файле)
