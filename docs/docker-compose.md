# Docker Compose: как запускать сейчас

Корень проекта — там же лежит `docker-compose.yaml`. Команды ниже выполняй из этого каталога.

## Сервисы и профили

| Сервис | Профиль | Контейнер | Назначение |
|--------|---------|-----------|------------|
| `db` | *(нет)* | `food_helper_db` | Postgres 16 + pgvector, порт **5433→5432** |
| `loader` | `load` | `food_helper_loader` | Однократная загрузка `recipes.jsonl` в БД |
| `embed` | `embed` | **`food_helper`** | Образ с Python, зависимостями из `requirements-embed.txt`; по умолчанию **`sleep infinity`** (удобно для `exec`, тестов и поиска) |

Тома: `pgdata` (данные Postgres), `huggingface_cache` (кэш моделей HF).

## Секреты и токен Hugging Face

1. Скопируй [`.env.example`](../.env.example) в **`.env`** в корне репозитория (файл `.env` в git не коммитится).
2. Укажи `HF_TOKEN=...` (read-токен с [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)), чтобы не упираться в лимиты анонимных запросов при скачивании моделей.

Compose подставляет `HF_TOKEN` в сервис `embed` через `HF_TOKEN: ${HF_TOKEN:-}`.

Дополнительно: пример без корневого `.env` — [secrets/huggingface.env.example](../secrets/huggingface.env.example) и [secrets/README.txt](../secrets/README.txt).

## Сборка образов

После изменения `requirements-embed.txt` или `Dockerfile.embed`:

```powershell
docker compose build embed
```

Loader (другой Dockerfile):

```powershell
docker compose build loader
```

## Поднять только БД

```powershell
docker compose up -d db
```

Строка подключения с хоста (Windows/macOS/Linux):

`postgresql://food:foodpass@127.0.0.1:5433/food_helper`

Переменные для скриптов без DSN-строки: `DB_HOST=127.0.0.1`, `DB_PORT=5433`, `DB_NAME=food_helper`, `DB_USER=food`, `DB_PASSWORD=foodpass`.

## Долгоживущий контейнер приложения (`food_helper`)

Код монтируется в контейнер как **`.:/app`** — правки в репозитории видны сразу, пересборка образа нужна в основном при смене зависимостей.

```powershell
docker compose up -d db
docker compose --profile embed up -d embed
```

Проверка:

```powershell
docker ps --filter name=food_helper
```

### Зайти в контейнер

```powershell
docker compose exec embed bash
```

Дальше из каталога `/app` (это корень репозитория):

- поиск: `python scripts/search/search_recipes.py --from-db --query "борщ с говядиной" --json`
- эмбеддинги (разовый прогон): см. раздел ниже
- тесты: см. раздел «Тесты (pytest)» ниже на этой странице.

## Тесты (pytest)

Маркер **`integration`** описан в [pytest.ini](../pytest.ini): такие тесты ходят в Postgres, качают/грузят модель HF и выполняются дольше. Остальные тесты не требуют живой БД.

### На хосте (из корня репозитория)

Нужен Python с зависимостями (как минимум `pip install -r requirements-embed.txt` — там есть `pytest`).

Быстрый набор **без** интеграции (без БД и без тяжёлой модели для части тестов):

```powershell
python -m pytest tests/ -q -m "not integration"
```

Все тесты, для которых хватает окружения (интеграция пропустится с `skipped`, если нет DSN):

```powershell
python -m pytest tests/ -v
```

Интеграционный сценарий «запрос → нормализация → эмбеддинг → топ-10» ([tests/test_search_user_pipeline.py](../tests/test_search_user_pipeline.py)): нужны **БД с `recipe_embeddings`** и доступ к HF. Задай DSN, например:

```powershell
$env:EMBED_PG_DSN = "postgresql://food:foodpass@127.0.0.1:5433/food_helper"
python -m pytest tests/test_search_user_pipeline.py -v -m integration --log-cli-level=INFO --log-cli-format="%(asctime)s %(levelname)s %(message)s" --log-date-format="%H:%M:%S"
```

Текст запроса по умолчанию в тесте можно переопределить: `SEARCH_E2E_QUERY="..."`.

### В контейнере `embed`

Подними `db` и **`embed`** (в контейнере уже выставлены `DB_HOST=db` и остальные `DB_*`, отдельно DSN для интеграции часто не нужен):

```powershell
docker compose up -d db
docker compose --profile embed up -d embed
```

Все тесты без лишнего вывода:

```powershell
docker compose exec embed python -m pytest tests/ -q
```

Только быстрые (без маркера `integration`):

```powershell
docker compose exec embed python -m pytest tests/ -q -m "not integration"
```

Интеграционный тест поиска **с логами шагов** в консоль:

```powershell
docker compose exec embed python -m pytest tests/test_search_user_pipeline.py -v -m integration --log-cli-level=INFO --log-cli-format="%(asctime)s %(levelname)s %(message)s" --log-date-format="%H:%M:%S"
```

При желании добавь **`-s`**, чтобы не буферизовать stdout.

## Загрузка JSONL в Postgres (loader)

Нужен файл **`recipes.jsonl`** в корне (путь зашит в `docker-compose.yaml` как `./recipes.jsonl`).

```powershell
docker compose up -d db
docker compose --profile load run --rm loader
```

Контейнер после выполнения скрипта завершится (`restart: "no"`).

## Эмбеддинги в БД

Образ `embed` по умолчанию **не** запускает `embed_recipes.py` при `up` — только держит процесс `sleep infinity`. Чтобы один раз прогнать эмбеддинги, переопредели команду:

```powershell
docker compose up -d db
docker compose --profile embed run --rm embed python scripts/embedding/embed_recipes.py --from-db --only-missing --db-fetch-batch 500
```

Первый прогон может долго качать PyTorch и модель; кэш лежит в томе `huggingface_cache`.

## Остановка и тома

Обычное выключение БД:

```powershell
docker compose down
```

Сервис **`embed` относится к профилю `embed`**. Если поднимал `embed` через `--profile embed`, при остановке укажи тот же профиль — иначе контейнер **`food_helper`** может остаться работать, и сеть `food_helper_default` не удалится (`Resource is still in use`):

```powershell
docker compose --profile embed down
```

Удалить ещё и тома (в т.ч. **`pgdata`** — полная потеря данных БД):

```powershell
docker compose --profile embed down -v
```

## Ручная зачистка «залипшего» контейнера

Если сеть занята, посмотри, кто подключён:

```powershell
docker network inspect food_helper_default
```

Останови и удали контейнер `food_helper`, затем снова `docker compose down` или `docker network rm food_helper_default`, если сеть осталась без контейнеров.

## Краткая последовательность «с нуля»

1. `.env` с `HF_TOKEN` (по желанию, но рекомендуется).
2. `docker compose build embed`
3. `docker compose up -d db`
4. При необходимости: `docker compose --profile load run --rm loader`
5. `docker compose --profile embed run --rm embed python scripts/embedding/embed_recipes.py --from-db --only-missing`
6. `docker compose --profile embed up -d embed` — дальше работа через `docker compose exec embed ...` (в т.ч. pytest — см. раздел «Тесты (pytest)» ниже).
7. Остановка: `docker compose --profile embed down` (и при необходимости `docker compose down` для `db`, если `embed` уже снят).
