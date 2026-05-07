# Техническое задание: локальная LLM для Food Helper

Версия: 1.0  
Дата: 2026-05-06  
Проект: `ShirinKhan1/food_helper`  
Цель: добавить локальную LLM, скачанную на ноутбук пользователя, чтобы API Food Helper мог использовать её для генерации человеческих ответов на основе найденных рецептов.

---

## 1. Цель задачи

Нужно внедрить в Food Helper локальную LLM, которая запускается на ноутбуке через CPU и использует не больше примерно 10–12 GB RAM.

LLM должна использоваться не как самостоятельный источник фактов, а как слой генерации ответа поверх текущего поиска рецептов.

Текущая логика проекта должна сохраниться:

- поиск рецептов через существующие сервисы;
- фильтрация по ограничениям пользователя;
- работа с `pgvector` / hybrid search;
- сохранение текущего API-контракта `/v1/chat`;
- сохранение fallback-ответов без LLM.

После внедрения пользователь должен иметь возможность:

1. Скачать локальную модель на ноутбук.
2. Запустить Ollama локально.
3. Включить LLM в настройках проекта.
4. Отправлять обычные запросы в `/v1/chat`.
5. Получать ответы, сформулированные локальной LLM на основе найденных рецептов.

---

## 2. Главный принцип архитектуры

LLM не должна сама искать рецепты, ходить в БД или придумывать данные.

Правильный поток:

```text
Пользовательский запрос
→ /v1/chat
→ IntentRouter
→ constraints extraction
→ SearchService / RecipeRepository / VectorSearchService
→ найденные рецепты и структурированный контекст
→ LLMAnswerGenerator
→ финальный человекочитаемый ответ
```

LLM получает только уже найденные данные и формулирует ответ на их основе.

---

## 3. Выбор модели для ноутбука

Основная модель для первой версии:

```bash
qwen3:4b
```

Причины выбора:

- модель достаточно маленькая для локального запуска;
- в Ollama версия `qwen3:4b` указана примерно как 2.5 GB;
- должна влезть в целевой лимит 10–12 GB RAM с учётом процесса Ollama и контекста;
- лучше начать с 4B, а не с 8B/14B, потому что запуск будет на CPU;
- для Food Helper модель нужна в первую очередь для аккуратной формулировки ответа, а не для тяжёлого reasoning.

Резервные варианты:

```bash
qwen3:1.7b
```

Использовать, если `qwen3:4b` работает слишком медленно.

```bash
phi4-mini
```

Использовать как альтернативную compact instruct-модель, если Qwen плохо отвечает на русском или слишком медленная.

На первом этапе не использовать:

- `qwen3:8b`, если ноутбук слабый или CPU-only;
- `qwen3:14b` и выше;
- внешние API;
- Hugging Face Inference;
- fine-tuning.

---

## 4. Установка и скачивание модели

### 4.1. Установить Ollama

Установить Ollama с официального сайта:

```text
https://ollama.com/
```

После установки проверить, что Ollama работает:

```bash
ollama --version
```

### 4.2. Скачать модель

```bash
ollama pull qwen3:4b
```

Проверить, что модель скачана:

```bash
ollama list
```

В списке должна быть модель:

```text
qwen3:4b
```

### 4.3. Проверить модель вручную

```bash
ollama run qwen3:4b
```

Тестовый запрос:

```text
Ответь коротко по-русски: что можно приготовить на ужин без мяса?
```

### 4.4. Проверить HTTP API Ollama

Если Ollama запущен, локальный API должен быть доступен по адресу:

```text
http://localhost:11434
```

Проверка через curl:

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "qwen3:4b",
  "prompt": "Ответь коротко по-русски: что можно приготовить на ужин без мяса?",
  "stream": false,
  "think": false,
  "options": {
    "temperature": 0.2,
    "num_predict": 300,
    "num_ctx": 4096
  }
}'
```

Ожидаемый результат: JSON-ответ с полем `response`.

---

## 5. Ограничения по RAM и CPU

Так как запуск планируется на ноутбуке и CPU, для первой версии нужно ограничить генерацию:

```text
num_ctx: 4096
num_predict: 300–600
temperature: 0.1–0.3
think: false
stream: false
```

Причина: большой context window сильно увеличивает расход памяти и снижает скорость на CPU. Несмотря на то что некоторые модели поддерживают большой контекст, для MVP Food Helper лучше держать контекст компактным.

Рекомендуемые значения для первой версии:

```text
LLM_NUM_CTX=4096
LLM_MAX_TOKENS=500
LLM_TEMPERATURE=0.2
LLM_TIMEOUT_SECONDS=90
```

---

## 6. Переменные окружения проекта

Добавить поддержку следующих переменных окружения:

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
```

Поведение:

- если `LLM_ENABLED=false`, проект работает как раньше;
- если `LLM_ENABLED=true`, проект пытается использовать локальную LLM;
- если Ollama недоступен, модель не скачана или запрос к LLM завершился ошибкой, API должен вернуть обычный rule-based ответ;
- ошибка LLM не должна ломать `/v1/chat`.

---

## 7. Изменения в коде

### 7.1. Добавить пакет `app/services/llm`

Создать файлы:

```text
app/services/llm/__init__.py
app/services/llm/base.py
app/services/llm/ollama.py
app/services/llm/null.py
```

### 7.2. `app/services/llm/base.py`

Назначение: общий интерфейс LLM-клиента.

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMGenerateRequest:
    system_prompt: str
    user_prompt: str
    temperature: float = 0.2
    max_tokens: int = 500
    num_ctx: int = 4096
    think: bool = False


class LLMClient(Protocol):
    def generate(self, request: LLMGenerateRequest) -> str:
        ...
```

### 7.3. `app/services/llm/ollama.py`

Назначение: HTTP-клиент для локальной Ollama.

```python
from __future__ import annotations

import httpx

from app.services.llm.base import LLMClient, LLMGenerateRequest


class OllamaLLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 90.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    def generate(self, request: LLMGenerateRequest) -> str:
        payload = {
            "model": self._model,
            "system": request.system_prompt,
            "prompt": request.user_prompt,
            "stream": False,
            "think": request.think,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
                "num_ctx": request.num_ctx,
            },
        }

        with httpx.Client(timeout=self._timeout_seconds) as client:
            response = client.post(f"{self._base_url}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()

        answer = str(data.get("response") or "").strip()
        if not answer:
            raise RuntimeError("Ollama returned empty response.")

        return answer
```

### 7.4. `app/services/llm/null.py`

Назначение: безопасная заглушка, когда LLM выключена.

```python
from __future__ import annotations

from app.services.llm.base import LLMGenerateRequest


class NullLLMClient:
    def generate(self, request: LLMGenerateRequest) -> str:
        raise RuntimeError("LLM is disabled.")
```

### 7.5. Добавить `app/services/answer_generator.py`

Назначение: слой, который превращает структурированный результат поиска в prompt для LLM и возвращает финальный ответ.

```python
from __future__ import annotations

import json

from app.schemas.recipe import RecipeCard
from app.services.llm.base import LLMClient, LLMGenerateRequest


SYSTEM_PROMPT = """
Ты помощник по рецептам внутри Food Helper.

Правила:
- Отвечай по-русски.
- Используй только переданный контекст.
- Не придумывай рецепты, ингредиенты, калории и факты, которых нет в контексте.
- Если данных мало, честно скажи, что можно уточнить.
- Ответ должен быть коротким, полезным и дружелюбным.
- Не давай медицинских гарантий по аллергиям.
""".strip()


class AnswerGenerator:
    def __init__(
        self,
        *,
        llm_client: LLMClient,
        temperature: float,
        max_tokens: int,
        num_ctx: int,
        think: bool,
    ) -> None:
        self._llm_client = llm_client
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._num_ctx = num_ctx
        self._think = think

    def generate_recipe_list_answer(
        self,
        *,
        user_message: str,
        fallback_answer: str,
        recipes: list[RecipeCard],
        warnings: list[str],
    ) -> str:
        if not recipes:
            return fallback_answer

        context = {
            "recipes": [recipe.model_dump(mode="json") for recipe in recipes],
            "warnings": warnings,
        }

        prompt = f"""
Запрос пользователя:
{user_message}

Найденные рецепты и ограничения:
{json.dumps(context, ensure_ascii=False, indent=2)}

Сформулируй ответ:
- сначала коротко скажи, что нашёл;
- перечисли только рецепты из списка;
- для каждого варианта дай 1 короткую причину, почему он может подойти;
- если есть предупреждения, аккуратно добавь их в конце;
- не добавляй новые рецепты, ингредиенты или значения КБЖУ.
""".strip()

        try:
            return self._llm_client.generate(
                LLMGenerateRequest(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=prompt,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    num_ctx=self._num_ctx,
                    think=self._think,
                )
            )
        except Exception:
            return fallback_answer
```

---

## 8. Изменения в `app/core/config.py`

Добавить поля в `Settings`:

```python
llm_enabled: bool
llm_provider: str
llm_model: str
llm_base_url: str
llm_timeout_seconds: float
llm_temperature: float
llm_max_tokens: int
llm_num_ctx: int
llm_think: bool
```

Добавить чтение из окружения в `Settings.from_env()`:

```python
llm_enabled=os.getenv("LLM_ENABLED", "false").lower() == "true",
llm_provider=os.getenv("LLM_PROVIDER", "none"),
llm_model=os.getenv("LLM_MODEL", "qwen3:4b"),
llm_base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434"),
llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "90")),
llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "500")),
llm_num_ctx=int(os.getenv("LLM_NUM_CTX", "4096")),
llm_think=os.getenv("LLM_THINK", "false").lower() == "true",
```

---

## 9. Изменения в `app/services/container.py`

Добавить в `AppServices`:

```python
answer_generator: AnswerGenerator
```

В `build_services()` создать LLM-клиент:

```python
if resolved_settings.llm_enabled and resolved_settings.llm_provider == "ollama":
    llm_client = OllamaLLMClient(
        base_url=resolved_settings.llm_base_url,
        model=resolved_settings.llm_model,
        timeout_seconds=resolved_settings.llm_timeout_seconds,
    )
else:
    llm_client = NullLLMClient()

answer_generator = AnswerGenerator(
    llm_client=llm_client,
    temperature=resolved_settings.llm_temperature,
    max_tokens=resolved_settings.llm_max_tokens,
    num_ctx=resolved_settings.llm_num_ctx,
    think=resolved_settings.llm_think,
)
```

Передать `answer_generator` в `ChatPipeline`.

---

## 10. Изменения в `app/orchestrator/pipeline.py`

В `ChatPipeline.__init__()` добавить зависимость:

```python
answer_generator: AnswerGenerator,
```

Сохранить:

```python
self._answer_generator = answer_generator
```

В ветках:

```python
search_recipes
recommend_recipes
allergy_or_exclusion
similar_recipes
```

заменить прямое использование rule-based answer на схему:

```python
fallback_answer = self._render_recipe_list_answer(decision.intent, recipes)
answer = self._answer_generator.generate_recipe_list_answer(
    user_message=message,
    fallback_answer=fallback_answer,
    recipes=recipes,
    warnings=warnings,
)
```

Для `similar_recipes` можно на первом этапе оставить старый `_render_similar_answer`, либо добавить отдельный метод `generate_similar_recipes_answer()` позже.

На первом этапе не менять:

- `nutrition_question`;
- `recipe_details`;
- `ingredient_substitution`;
- `general_substitution`.

Причина: эти ответы более чувствительны к точности. Лучше сначала подключить LLM к спискам рецептов.

---

## 11. API-контракт

Эндпоинт остаётся прежним:

```text
POST /v1/chat
```

Пример запроса:

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Подбери рецепты на ужин без мяса и без сахара",
    "options": {
      "top_k": 5,
      "include_debug": true
    }
  }'
```

Ожидаемое поведение:

- API возвращает тот же `ChatResponse`;
- поле `answer` формулируется LLM;
- поля `recipes`, `sources`, `warnings`, `debug` сохраняются;
- если LLM недоступна, поле `answer` формируется старым способом.

---

## 12. Поведение fallback

Fallback обязателен.

Сценарии fallback:

- `LLM_ENABLED=false`;
- Ollama не запущен;
- модель не скачана;
- HTTP timeout;
- Ollama вернула пустой ответ;
- ошибка JSON/HTTP;
- LLM слишком долго отвечает.

Во всех этих случаях `/v1/chat` должен вернуть ответ без ошибки 500, используя текущий rule-based renderer.

---

## 13. Тесты

Добавить тесты:

```text
tests/test_llm_answer_generator.py
tests/test_ollama_llm_client.py
tests/test_chat_pipeline_llm_fallback.py
```

### 13.1. Unit test: LLM успешно генерирует ответ

Проверить:

- передан список рецептов;
- fake LLM возвращает строку;
- `AnswerGenerator` возвращает эту строку.

### 13.2. Unit test: fallback при ошибке LLM

Проверить:

- fake LLM бросает exception;
- `AnswerGenerator` возвращает `fallback_answer`;
- исключение не пробрасывается наружу.

### 13.3. Unit test: пустой список рецептов

Проверить:

- если `recipes=[]`, LLM не вызывается;
- возвращается `fallback_answer`.

### 13.4. Integration-style test: LLM выключена

Проверить:

- `LLM_ENABLED=false`;
- `/v1/chat` работает как раньше;
- API-контракт не меняется.

### 13.5. Integration-style test: Ollama недоступна

Проверить:

- `LLM_ENABLED=true`;
- `LLM_BASE_URL` указывает на несуществующий порт;
- `/v1/chat` не падает;
- возвращается fallback-ответ.

---

## 14. Критерии готовности

Задача считается выполненной, если:

1. Команда `ollama pull qwen3:4b` успешно скачивает модель.
2. Команда `ollama list` показывает `qwen3:4b`.
3. Команда `curl http://localhost:11434/api/generate ...` возвращает JSON с `response`.
4. В проекте появились настройки `LLM_ENABLED`, `LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL`.
5. При `LLM_ENABLED=false` API работает как раньше.
6. При `LLM_ENABLED=true` и запущенной Ollama поле `answer` в `/v1/chat` генерируется локальной LLM.
7. LLM не придумывает рецепты вне списка, переданного из retrieval.
8. Поля `recipes`, `sources`, `warnings` сохраняются в ответе API.
9. Если Ollama выключена, API не падает и возвращает fallback-ответ.
10. Есть тесты на успешную генерацию и fallback.

---

## 15. Что не входит в первую версию

В первую версию не входит:

- fine-tuning модели;
- загрузка модели на Hugging Face;
- использование Hugging Face Inference API;
- OpenAI / Claude / Gemini / внешние LLM API;
- streaming ответов;
- agent tools;
- function calling;
- генерация новых рецептов с нуля;
- медицинские рекомендации;
- автоматическое определение аллергической безопасности блюда;
- обучение модели на пользовательских данных.

---

## 16. План внедрения

### Этап 0. Локальная модель

- Установить Ollama.
- Скачать `qwen3:4b`.
- Проверить ручной запуск.
- Проверить HTTP API Ollama.

### Этап 1. Настройки проекта

- Добавить LLM-поля в `Settings`.
- Добавить переменные окружения.
- Убедиться, что при отсутствии переменных проект работает как раньше.

### Этап 2. LLM-клиент

- Добавить `LLMGenerateRequest`.
- Добавить `LLMClient` protocol.
- Добавить `OllamaLLMClient`.
- Добавить `NullLLMClient`.

### Этап 3. Генератор ответов

- Добавить `AnswerGenerator`.
- Реализовать prompt для списка рецептов.
- Реализовать fallback.

### Этап 4. Интеграция в pipeline

- Передать `AnswerGenerator` в `ChatPipeline`.
- Подключить LLM для `search_recipes`, `recommend_recipes`, `allergy_or_exclusion`.
- Оставить остальные intent-ветки rule-based.

### Этап 5. Тесты

- Проверить успешный LLM-ответ.
- Проверить fallback.
- Проверить выключенный LLM-режим.
- Проверить недоступную Ollama.

### Этап 6. Документация

Добавить файл:

```text
docs/local-llm.md
```

В нём описать:

- как установить Ollama;
- как скачать модель;
- какие env-переменные выставить;
- как проверить `/v1/chat`;
- что делать, если модель работает медленно.

---

## 17. Рекомендованный `.env` для локального LLM-режима

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
```

---

## 18. Рекомендованный prompt-контракт

System prompt:

```text
Ты помощник по рецептам внутри Food Helper.
Отвечай по-русски.
Используй только переданный контекст.
Не придумывай рецепты, ингредиенты, калории и факты, которых нет в контексте.
Если данных мало, честно скажи, что можно уточнить.
Ответ должен быть коротким, полезным и дружелюбным.
Не давай медицинских гарантий по аллергиям.
```

User prompt должен содержать:

- исходный запрос пользователя;
- список найденных рецептов;
- ограничения пользователя;
- warnings;
- явный запрет добавлять новые рецепты.

---

## 19. Пример ожидаемого ответа LLM

Запрос:

```text
Подбери рецепты на ужин без мяса и без сахара
```

Ожидаемый стиль ответа:

```text
Я нашёл несколько вариантов, которые могут подойти под ваши ограничения:

1. Овощное рагу — лёгкий вариант на ужин без мясных ингредиентов.
2. Гречка с грибами — сытное блюдо, где основной акцент на крупе и грибах.
3. Салат с фасолью — подойдёт, если нужен быстрый вариант с растительным белком.

Проверьте состав конкретных продуктов, особенно если ограничения связаны с аллергией.
```

Важно: названия рецептов в ответе должны быть только из результата поиска.

---

## 20. Дальнейшие улучшения после MVP

После первой версии можно улучшать:

- подключить LLM к `recipe_details`;
- подключить LLM к объяснению замен ингредиентов;
- добавить streaming ответов;
- добавить поле `llm_used` в debug;
- добавить поле `llm_model` в debug;
- добавить замер latency;
- подобрать модель быстрее или качественнее;
- попробовать `qwen3:8b`, если ноутбук справится;
- сделать benchmark моделей;
- подготовить датасет для будущего LoRA fine-tuning;
- добавить provider interface для внешних API, но не включать их по умолчанию.

---

## 21. Источники и справочные ссылки

Ollama:

```text
https://ollama.com/
https://ollama.com/library/qwen3
https://docs.ollama.com/api/generate
https://docs.ollama.com/api/streaming
```

Проект:

```text
https://github.com/ShirinKhan1/food_helper
```

---

## 22. Итоговое решение

Для первой версии Food Helper нужно внедрить локальную LLM через Ollama и модель `qwen3:4b`.

LLM должна использоваться только для генерации финального текста ответа на основе уже найденных рецептов. Поиск, фильтрация, ограничения, источники и текущий API-контракт остаются за существующей логикой проекта.

Такой подход даст возможность пользоваться скачанной локальной моделью уже сейчас, не тратить деньги на inference API и не рисковать стабильностью текущего backend.
