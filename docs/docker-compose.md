# Docker Compose: как запускать сейчас

Корень проекта — там же лежит `docker-compose.yaml`. Команды ниже выполняй из этого каталога.

## Сервисы и профили

| Сервис | Профиль | Контейнер | Назначение |
|--------|---------|-----------|------------|
| `db` | *(нет)* | `food_helper_db` | Postgres 16 + pgvector, порт **5433→5432** |
| `ollama` | *(нет)* | `food_helper_ollama` | Локальный LLM runtime, порт **11434→11434**, модели в томе `ollama_data` |
| `loader` | `load` | `food_helper_loader` | Однократная загрузка `recipes.jsonl` в БД |
| `embed` | `embed` | **`food_helper`** | Образ с Python, зависимостями из `requirements-embed.txt`; по умолчанию **`sleep infinity`** (удобно для `exec`, тестов и поиска) |
| `api` | *(нет)* | `food_helper_api` | FastAPI на порту **8000→8000**; LLM-запросы идут в `http://ollama:11434` |
| `web` | *(нет)* | `food_helper_web` | Next.js UI на **3000→3000**; прокси `/v1/*` и `/health` → `api` (в браузере достаточно **http://localhost:3000**) |

Тома: `pgdata` (данные Postgres), `ollama_data` (скачанные модели Ollama). Модель эмбеддингов сохраняется внутрь Docker-образов при сборке и используется из `/opt/models/intfloat-multilingual-e5-small`.

## Локальная LLM в Docker (Ollama в контейнере)

По умолчанию `api` уже настроен на контейнерный Ollama:

- `LLM_ENABLED=true`
- `LLM_PROVIDER=ollama`
- `LLM_MODEL=qwen3:4b`
- `LLM_BASE_URL=http://ollama:11434`

Запуск:

```powershell
docker compose up -d db ollama api
```

Скачать модель внутрь контейнера Ollama:

```powershell
docker compose exec ollama ollama pull qwen3:4b
docker compose exec ollama ollama list
```

Быстрые проверки:

```powershell
docker compose exec ollama ollama ps
curl http://localhost:8000/v1/chat -H "Content-Type: application/json" -d "{\"message\":\"Подбери рецепты на ужин без мяса\",\"options\":{\"top_k\":5}}"
```

## Секреты и токен Hugging Face

1. Скопируй [`.env.example`](../.env.example) в **`.env`** в корне репозитория (файл `.env` в git не коммитится).
2. Укажи `HF_TOKEN=...` (read-токен с [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)), если нужно скачивать модели с HF при сборке или вручную.

В обычном запуске `api` и `embed` работают с локальной моделью в offline-режиме и не ходят в HF.

Дополнительно: пример без корневого `.env` — [secrets/huggingface.env.example](../secrets/huggingface.env.example) и [secrets/README.txt](../secrets/README.txt).

## Сборка образов

После изменения `requirements-embed.txt` или `Dockerfile.embed`:

```powershell
docker compose build embed
```

После изменения `requirements-api.txt`, `Dockerfile.api` или модели эмбеддингов:

```powershell
docker compose build api
```

Loader (другой Dockerfile):

```powershell
docker compose build loader
```

## Как перезапускать после изменений

Код проекта монтируется в контейнеры как **`.:/app`**, поэтому правки `.py`, `.json`, тестов и большинства файлов приложения сразу видны внутри контейнеров. Но процесс Python сам себя не перезапускает.

Если менял код API:

```powershell
docker compose restart api
```

Если менял код, которым пользуешься через долгоживущий `embed`-контейнер, чаще всего ничего пересобирать не надо. Для команд через `docker compose exec embed ...` новый запуск Python увидит свежий код. Если внутри `embed` был запущен долгий процесс, перезапусти контейнер:

```powershell
docker compose --profile embed restart embed
```

Если менял `docker-compose.yaml`, переменные окружения, порты или список volume, пересоздай контейнеры:

```powershell
docker compose up -d --force-recreate api
docker compose --profile embed up -d --force-recreate embed
```

Если менял зависимости, Dockerfile или локально запечённую модель, сначала пересобери образ, потом пересоздай контейнер:

```powershell
docker compose build api
docker compose up -d --force-recreate api
```

Для `embed` аналогично:

```powershell
docker compose build embed
docker compose --profile embed up -d --force-recreate embed
```

Если менял SQL init-файлы в `db/init`, они применяются только при создании пустого Postgres-тома. Для полной пересборки БД с потерей данных:

```powershell
docker compose --profile embed down -v
docker compose up -d db
```

Короткое правило: код — `restart`, зависимости/Dockerfile — `build` + `up --force-recreate`, схема БД из init-файлов — пересоздание тома `pgdata`.

## Поднять только БД

```powershell
docker compose up -d db
```

Строка подключения с хоста (Windows/macOS/Linux):

`postgresql://food:foodpass@127.0.0.1:5433/food_helper`

Переменные для скриптов без DSN-строки: `DB_HOST=127.0.0.1`, `DB_PORT=5433`, `DB_NAME=food_helper`, `DB_USER=food`, `DB_PASSWORD=foodpass`.

## Поднять только Ollama

```powershell
docker compose up -d ollama
docker compose exec ollama ollama list
```

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

Интеграционный сценарий «запрос → нормализация → эмбеддинг → топ-10» ([tests/test_search_user_pipeline.py](../tests/test_search_user_pipeline.py)): нужны **БД с `recipe_embeddings`** и доступная модель эмбеддингов. Задай DSN, например:

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

Первый build образов может долго качать PyTorch и модель. При запуске контейнеров используется локальная модель из `/opt/models/intfloat-multilingual-e5-small`.

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

1. `.env` с `HF_TOKEN` (по желанию; полезно при скачивании модели во время build).
2. `docker compose build api embed`
3. `docker compose up -d db ollama api web`
4. `docker compose exec ollama ollama pull qwen3:4b`
5. При необходимости: `docker compose --profile load run --rm loader`
6. При необходимости: `docker compose --profile embed run --rm embed python scripts/embedding/embed_recipes.py --from-db --only-missing`
7. `docker compose --profile embed up -d embed` — дальше работа через `docker compose exec embed ...` (в т.ч. pytest — см. раздел «Тесты (pytest)» ниже).
8. Остановка: `docker compose --profile embed down` (и при необходимости `docker compose down` для `db/ollama/api`, если `embed` уже снят).

## Frontend и авторизация (MVP)

В `docker-compose.yaml` у сервиса `api` заданы `FRONTEND_ORIGIN` и `AUTH_SECRET_KEY` для локальной разработки с Next.js на `http://localhost:3000`. Для продакшена замените `AUTH_SECRET_KEY` на случайную длинную строку и выставьте `AUTH_COOKIE_SECURE=true` при HTTPS.

Если база уже существовала до появления таблицы `users` и колонок в `chat_sessions`, примените миграцию:

```powershell
Get-Content db/migrations/manual_users_and_chat_sessions.sql | docker compose exec -T db psql -U food -d food_helper
```

Фронтенд: каталог `web/`, образ `docker/Dockerfile.web`, сервис `web` в Compose. После `docker compose up -d web` откройте **http://localhost:3000/** (см. корневой [README.md](../README.md)).
