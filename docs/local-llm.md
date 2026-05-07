# Локальная LLM (Ollama) для Food Helper

Food Helper может формулировать текст ответа в `/v1/chat` через локальную модель в [Ollama](https://ollama.com/). Поиск рецептов, фильтры и структура ответа API не меняются: LLM получает уже найденные рецепты и только перефразирует ответ.

## Ollama в Docker (рекомендуется)

В проектном `docker-compose.yaml` уже добавлен сервис `ollama`, а сервис `api` настроен на него через:

```text
LLM_BASE_URL=http://ollama:11434
```

Запуск контейнеров:

```powershell
docker compose up -d db ollama api
```

Скачивание модели в контейнер:

```powershell
docker compose exec ollama ollama pull qwen3:4b
docker compose exec ollama ollama list
```

Хранилище моделей — Docker volume `ollama_data`, поэтому после перезапуска контейнера модель останется.

## Установка Ollama и модели (на хосте, альтернативный вариант)

1. Установите Ollama с [ollama.com](https://ollama.com/).
2. Проверьте установку:

   ```bash
   ollama --version
   ```

3. Скачайте рекомендуемую для первого запуска модель:

   ```bash
   ollama pull qwen3:4b
   ```

4. Убедитесь, что модель в списке:

   ```bash
   ollama list
   ```

5. Опционально проверьте в консоли:

   ```bash
   ollama run qwen3:4b
   ```

## Проверка HTTP API Ollama

При запущенном Ollama API доступен по умолчанию на `http://localhost:11434`.

Пример запроса:

```bash
curl http://localhost:11434/api/generate -d "{
  \"model\": \"qwen3:4b\",
  \"prompt\": \"Ответь коротко по-русски: что можно приготовить на ужин без мяса?\",
  \"stream\": false,
  \"think\": false,
  \"options\": {
    \"temperature\": 0.2,
    \"num_predict\": 300,
    \"num_ctx\": 4096
  }
}"
```

В ответе должно быть поле `response` с текстом.

## Переменные окружения

| Переменная | Описание | Пример |
|------------|----------|--------|
| `LLM_ENABLED` | Включить генерацию через LLM (`true` / `false`) | `true` |
| `LLM_PROVIDER` | Провайдер; поддерживается `ollama` | `ollama` |
| `LLM_MODEL` | Имя модели в Ollama | `qwen3:4b` |
| `LLM_BASE_URL` | Базовый URL API Ollama | `http://localhost:11434` |
| `LLM_TIMEOUT_SECONDS` | Таймаут HTTP-запроса к Ollama | `90` |
| `LLM_TEMPERATURE` | Температура генерации | `0.2` |
| `LLM_MAX_TOKENS` | Ограничение длины ответа (`num_predict`) | `500` |
| `LLM_NUM_CTX` | Размер контекста (`num_ctx`) | `4096` |
| `LLM_THINK` | Режим «размышления» модели (`think`) | `false` |
| `ANSWER_MODE` | Режим генерации: `template` / `llm` / `auto` | `auto` |
| `LLM_POSTCHECK_ENABLED` | Включить post-check защиту от галлюцинаций | `true` |
| `LLM_STRICT_CONTEXT` | Запрет на новые факты вне context | `true` |
| `LLM_MAX_ANSWER_CHARS` | Максимальная длина ответа LLM | `2500` |
| `LLM_STRIP_THINK_TAGS` | Удалять `<think>...</think>` из ответа | `true` |

Рекомендуемый набор для локального режима:

```bash
LLM_ENABLED=true
LLM_PROVIDER=ollama
LLM_MODEL=qwen3:4b
LLM_BASE_URL=http://localhost:11434
LLM_TIMEOUT_SECONDS=90
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=500
LLM_NUM_CTX=4096
LLM_THINK=false
ANSWER_MODE=auto
LLM_POSTCHECK_ENABLED=true
LLM_STRICT_CONTEXT=true
LLM_MAX_ANSWER_CHARS=2500
LLM_STRIP_THINK_TAGS=true
```

Если `LLM_ENABLED=false` или провайдер не `ollama`, API работает как раньше: поле `answer` собирается rule-based списком рецептов.

## Проверка `/v1/chat`

Запустите backend и отправьте запрос (порт подставьте свой):

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"Подбери рецепты на ужин без мяса и без сахара\", \"options\": {\"top_k\": 5, \"include_debug\": true}}"
```

Ожидается прежний формат ответа: `answer`, `recipes`, `sources`, `warnings`, при включённом debug — отладочные поля.

Если Ollama не запущена, модель не скачана или запрос к LLM завершился ошибкой, `answer` будет сформирован старым способом (без падения API с 500).

При `include_debug=true` в ответе присутствует блок `debug.llm` с `used_llm` и `fallback_reason`.

## Быстрые ручные проверки fallback

1. Установите `ANSWER_MODE=template`, перезапустите API и отправьте `POST /v1/chat`.
2. Проверьте, что API отвечает `200`, `answer` не пустой, а `debug.llm.fallback_reason=answer_mode_template`.
3. Верните `ANSWER_MODE=auto`, выключите Ollama или укажите недоступный `LLM_BASE_URL`.
4. Повторите запрос и убедитесь, что endpoint не падает, а `answer` пришел из fallback.

## Docker и доступ к Ollama на хосте

Этот вариант нужен, только если вы не хотите запускать сервис `ollama` из `docker-compose`. Если API запущен в контейнере, а Ollama — на той же машине вне Docker, `localhost` внутри контейнера указывает на сам контейнер. На Windows для доступа к сервисам на хосте часто используют:

```text
http://host.docker.internal:11434
```

Установите `LLM_BASE_URL` соответственно.

## Если модель медленная или не хватает RAM

Целевой режим — CPU и около 10–12 GB RAM. Рекомендации:

- Уменьшите `LLM_MAX_TOKENS` и при необходимости `LLM_NUM_CTX`.
- Попробуйте более лёгкую модель, например `qwen3:1.7b`.
- Альтернатива по качеству/скорости: `phi4-mini` (задайте в `LLM_MODEL` после `ollama pull`).

Тяжёлые модели (`qwen3:8b` и выше) на слабом ноутбуке без GPU могут быть непрактичны.
