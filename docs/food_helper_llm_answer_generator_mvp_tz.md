# Техническое задание: MVP LLM-слоя для `food_helper`

**Версия:** 1.0  
**Дата:** 2026-05-07  
**Проект:** `food_helper`  
**Цель этапа:** реализовать MVP-подход `LLM = красивый answer generator поверх надежного RAG`, не передавая LLM право принимать бизнес-решения, выбирать рецепты, фильтровать результаты или вычислять факты.

---

## 1. Контекст проекта

`food_helper` — API-сервис по рецептам с гибридным поиском, структурированными ограничениями пользовательского запроса и чатовым endpoint `/v1/chat`.

Текущая архитектура уже содержит ключевые элементы RAG-пайплайна:

- FastAPI-приложение;
- endpoint `POST /v1/chat`;
- endpoint `POST /v1/search/debug`;
- endpoint `GET /v1/recipes/{recipe_id}`;
- Postgres + `pgvector`;
- таблицы рецептов и эмбеддингов;
- гибридный поиск через vector + keyword + rule scoring;
- `IntentRouter`;
- `ChatPipeline`;
- `QueryConstraints`;
- conversation state;
- сервисы nutrition/substitution/search;
- начальный `AnswerGenerator`;
- абстракцию `LLMClient`;
- `NullLLMClient` для выключенной LLM;
- `OllamaLLMClient`;
- конфигурацию LLM через env-переменные;
- Docker Compose service `ollama`.

Этот документ описывает, как превратить текущий начальный LLM-слой в полноценный MVP answer generator без перехода к agent-based архитектуре.

---

## 2. Главный принцип MVP

На этом этапе LLM не является самостоятельным агентом.

LLM не должна:

- выбирать route;
- определять intent;
- выполнять SQL;
- вызывать tools;
- выбирать рецепты из БД;
- снимать hard filters;
- добавлять новые рецепты;
- добавлять ингредиенты, которых нет в контексте;
- придумывать КБЖУ;
- придумывать калории;
- придумывать шаги приготовления;
- придумывать ссылки;
- гарантировать медицинскую безопасность;
- самостоятельно пересчитывать рецепт после замены ингредиента.

LLM должна:

- формулировать понятный, дружелюбный ответ;
- объяснять, почему найденные рецепты подходят под запрос;
- красиво представлять уже найденные данные;
- добавлять предупреждения, если они уже сформированы пайплайном;
- аккуратно отвечать при пустом результате;
- не скрывать неопределенность;
- использовать только переданный structured context.

Короткая формула:

```text
RAG / SQL / services = источник истины
LLM = слой финальной формулировки ответа
```

---

## 3. Цель MVP

Реализовать LLM-ответы для основных сценариев `/v1/chat`, сохранив текущий deterministic-first pipeline.

После внедрения пользователь должен получать более естественный ответ, но JSON-структура ответа API должна оставаться надежной и пригодной для фронтенда.

Пример желаемого поведения:

```text
Пользователь:
Посоветуй легкий ужин с курицей без грибов

До LLM:
Я нашел несколько подходящих вариантов:
1. Куриная грудка с овощами
2. Салат с курицей
3. Запеканка с курицей

После LLM:
Я нашел 3 варианта легкого ужина с курицей и без грибов:

1. Куриная грудка с овощами — хороший вариант для ужина: блюдо не слишком жирное, а в составе есть курица.
2. Салат с курицей — подойдет, если хочется чего-то более свежего и простого.
3. Запеканка с курицей — более сытный вариант, но она все еще проходит по заданным ограничениям.

Я отфильтровал рецепты по данным базы, но все равно проверьте состав продуктов, если у вас есть аллергии или строгие ограничения.
```

Важно: поле `recipes` в JSON не меняется из-за LLM. Меняется только поле `answer`.

---

## 4. Область работ

В MVP нужно доработать следующие части проекта:

```text
app/services/answer_generator.py
app/services/llm/base.py
app/services/llm/null.py
app/services/llm/ollama.py
app/services/container.py
app/orchestrator/pipeline.py
app/core/config.py
app/schemas/chat.py
app/schemas/recipe.py
app/schemas/search.py
tests/
docs/
```

Новые рекомендуемые файлы:

```text
app/services/llm/prompts.py
app/services/llm/context.py
app/services/llm/postcheck.py
app/services/llm/result.py
app/services/llm/errors.py
tests/test_answer_generator.py
tests/test_llm_postcheck.py
tests/test_chat_pipeline_llm.py
tests/eval_cases/chat_llm_answer_cases.jsonl
scripts/eval/run_chat_llm_eval.py
docs/llm-answer-generator-mvp.md
```

Этот файл ТЗ можно положить в проект как:

```text
docs/llm-answer-generator-mvp-tz.md
```

---

## 5. Что считается результатом MVP

MVP считается готовым, если:

- `/v1/chat` продолжает работать без LLM;
- `/v1/chat` использует LLM только для генерации поля `answer`;
- при недоступной LLM API не падает;
- при ошибке LLM возвращается deterministic fallback;
- список `recipes` формируется только поисковым пайплайном;
- `selected_recipe`, `nutrition`, `substitutions`, `sources`, `warnings`, `debug` не зависят от фантазии LLM;
- все основные chat-сценарии имеют LLM/fallback поведение;
- добавлены тесты на выключенную LLM, ошибку LLM, пустой ответ LLM и hallucination guard;
- добавлены ручные curl/Postman проверки;
- в debug можно понять, использовалась LLM или fallback.

---

## 6. MVP-сценарии

### 6.1. Поиск рецептов

Intent:

```text
search_recipes
recommend_recipes
allergy_or_exclusion
```

Route:

```text
hybrid_search
```

LLM получает:

- исходный запрос пользователя;
- список `RecipeCard`;
- ограничения `QueryConstraints`;
- warnings;
- sources;
- краткую информацию о route/intent для формулировки, но не для принятия решений.

LLM возвращает:

- человекочитаемый текст для `ChatResponse.answer`.

LLM не возвращает:

- новые recipe_id;
- измененный список рецептов;
- измененные warnings;
- измененные sources;
- измененные constraints.

Обязательное fallback-поведение:

```text
Если recipes пустой → LLM по умолчанию не вызывается, возвращается template answer.
Если LLM недоступна → возвращается template answer.
Если LLM вернула пустую строку → возвращается template answer.
Если LLM ответила рецептом не из списка → возвращается template answer.
```

---

### 6.2. Детали рецепта

Intent:

```text
recipe_details
```

Route:

```text
conversation_recipe_fetch
```

Примеры запросов:

```text
Покажи первый рецепт
Какие ингредиенты нужны для второго?
Как готовить третий?
Расскажи подробнее про этот рецепт
```

LLM получает:

- исходный запрос пользователя;
- `RecipeDetail`;
- тип подзапроса, если он определен rule-based логикой:
  - `ingredients_only`;
  - `steps_only`;
  - `summary`;
- warnings;
- sources.

LLM должна:

- коротко и понятно показать детали;
- не добавлять ингредиенты;
- не добавлять шаги;
- не менять порядок шагов, если показывает инструкцию;
- явно сказать, если в рецепте нет каких-то данных.

Fallback:

```text
_render_recipe_detail_answer(...)
```

---

### 6.3. Калории и БЖУ

Intent:

```text
nutrition_question
```

Route:

```text
sql
hybrid_search
```

Сценарии:

```text
Сколько калорий в первом рецепте?
Сколько белка во втором?
Какие БЖУ у этого блюда?
Сколько калорий и белка в рецепте с курицей?
```

Есть два типа ответа:

1. Ответ по одному выбранному рецепту.
2. Ответ по нескольким найденным кандидатам.

LLM получает:

- исходный запрос;
- выбранный рецепт или список карточек;
- nutrition values;
- единицу измерения, например `на 100 г`;
- выбранный nutrient, если он есть;
- warnings.

LLM должна:

- не пересчитывать значения;
- не округлять агрессивно без необходимости;
- не менять единицы измерения;
- явно указать, что данные относятся к 100 г, если это указано в данных;
- если данных нет, сказать, что в базе нет данных.

Fallback:

```text
NutritionService.format_answer(...)
_render_nutrition_candidate_answer(...)
```

---

### 6.4. Замена ингредиента в конкретном рецепте

Intent:

```text
ingredient_substitution
```

Route:

```text
substitution
```

Примеры:

```text
На что в первом рецепте можно заменить сахар?
Чем заменить молоко в этом рецепте?
У меня нет банана, что можно вместо него?
Можно этот рецепт без яйца?
```

LLM получает:

- исходный запрос;
- `RecipeDetail`;
- целевой ингредиент;
- список `SubstitutionOption`, сформированный `SubstitutionService`;
- warnings;
- ограничения пользователя.

LLM должна:

- оформить варианты замены понятным языком;
- не добавлять варианты, которых нет в `SubstitutionOption`, если включен strict mode;
- указать пропорции, если они есть в `SubstitutionOption.ratio`;
- указать влияние на вкус/текстуру только на основе `SubstitutionOption.note` или явно общими словами;
- обязательно пометить ответ как адаптацию рецепта;
- предупредить, что КБЖУ после замены не пересчитаны.

Fallback:

```text
_render_substitutions_answer(...)
```

---

### 6.5. Общая замена ингредиента

Intent:

```text
general_substitution
```

Route:

```text
substitution_catalog
```

Примеры:

```text
Чем заменить молоко?
Что можно вместо сахара?
Чем заменить яйцо в выпечке?
```

LLM получает:

- исходный запрос;
- target ingredient;
- варианты из rule-based каталога;
- warnings.

LLM должна:

- объяснить, что ответ общий и не привязан к конкретному рецепту;
- не обещать, что замена подойдет в любом рецепте;
- не пересчитывать КБЖУ;
- предложить выбрать конкретный рецепт, если нужна точная адаптация.

Fallback:

```text
_render_general_substitutions_answer(...)
```

---

### 6.6. Похожие рецепты

Intent:

```text
similar_recipes
```

Route:

```text
vector_search
```

LLM получает:

- исходный запрос;
- базовый рецепт, если он известен;
- найденные похожие рецепты;
- constraints;
- warnings.

LLM должна:

- сказать, к какому рецепту ищутся похожие варианты;
- перечислить только найденные варианты;
- объяснить, почему они могут быть похожи или подходить;
- не утверждать similarity score как факт, если он не передан в контексте.

Fallback:

```text
_render_similar_answer(...)
```

---

### 6.7. Пустая выдача

Сценарий:

```text
Пользователь просит рецепт с жесткими ограничениями, но final_results пустой.
```

LLM по умолчанию не вызывается, потому что нет recipe context.

Ответ должен:

- честно сказать, что подходящих рецептов в базе не найдено;
- предложить изменить условия поиска;
- не придумывать рецепт;
- не предлагать “примерный рецепт” вне базы.

Пример fallback:

```text
Я не нашел подходящих рецептов в базе. Можно попробовать убрать часть ограничений, выбрать другой ингредиент или поискать похожие блюда.
```

---

### 6.8. Не найден контекст диалога

Сценарии:

```text
Покажи третий рецепт
Сколько калорий во втором?
На что заменить сахар в этом рецепте?
```

Но в `conversation_state` нет предыдущей выдачи или `selected_recipe_id`.

LLM по умолчанию не вызывается.

Ответ должен:

- объяснить, что система пока не знает, о каком рецепте речь;
- предложить сначала найти рецепт или назвать его;
- не выбирать рецепт случайно.

---

## 7. Архитектура решения

### 7.1. Текущий поток

```text
User message
  ↓
POST /v1/chat
  ↓
ChatPipeline.handle_chat
  ↓
extract_query_constraints
  ↓
IntentRouter.decide
  ↓
_dispatch by intent
  ↓
SearchService / RecipeRepository / NutritionService / SubstitutionService
  ↓
Template fallback answer
  ↓
AnswerGenerator.generate_...(...)
  ↓
ChatResponse
```

### 7.2. Целевой поток MVP

```text
User message
  ↓
Intent + constraints + deterministic retrieval
  ↓
Structured response data is created
  ↓
Fallback answer is generated first
  ↓
LLM context is assembled from already trusted data
  ↓
AnswerGenerator calls LLM if allowed by answer mode
  ↓
LLM answer goes through post-check
  ↓
If valid: answer = llm_answer
  ↓
If invalid/error/timeout: answer = fallback_answer
  ↓
ChatResponse returned with stable structured fields
```

Главное правило реализации:

```text
fallback_answer должен формироваться ДО вызова LLM.
```

Это гарантирует, что при любой проблеме LLM endpoint останется рабочим.

---

## 8. Режимы ответа

Нужно добавить явный режим ответа.

Новая env-переменная:

```text
ANSWER_MODE=auto
```

Допустимые значения:

```text
template
llm
auto
```

### 8.1. `template`

LLM не вызывается никогда.

Используется для:

- тестов;
- локальной разработки без Ollama;
- быстрого API;
- production fallback режима.

Поведение:

```text
answer = fallback_answer
used_llm = false
llm_fallback_reason = "answer_mode_template"
```

### 8.2. `llm`

LLM вызывается во всех сценариях, где для этого есть context.

Если LLM недоступна или ответ не прошел post-check, используется fallback.

Поведение:

```text
answer = llm_answer OR fallback_answer
used_llm = true/false
llm_fallback_reason = null OR concrete_reason
```

### 8.3. `auto`

Рекомендуемый режим для MVP.

LLM вызывается только когда:

- есть надежный structured context;
- сценарий входит в allowlist;
- ответ не является простой ошибкой/валидацией;
- LLM включена в настройках;
- provider доступен.

Allowlist MVP:

```text
search_recipes
recommend_recipes
allergy_or_exclusion
similar_recipes
recipe_details
nutrition_question
ingredient_substitution
general_substitution
```

Не вызывать LLM в `auto`:

```text
fallback intent
empty message
too long message
DB unavailable
recipe context missing
recipes empty, если нет отдельного safe prompt для empty_results
```

---

## 9. Конфигурация

### 9.1. Текущие переменные

В проекте уже используются:

```text
LLM_ENABLED
LLM_PROVIDER
LLM_MODEL
LLM_BASE_URL
LLM_TIMEOUT_SECONDS
LLM_TEMPERATURE
LLM_MAX_TOKENS
LLM_NUM_CTX
LLM_THINK
```

### 9.2. Новые переменные

Добавить:

```text
ANSWER_MODE=auto
LLM_POSTCHECK_ENABLED=true
LLM_STRICT_CONTEXT=true
LLM_LOG_PROMPTS=false
LLM_LOG_RESPONSES=false
LLM_MIN_RECIPES_FOR_LIST_ANSWER=1
LLM_MAX_CONTEXT_RECIPES=5
LLM_MAX_CONTEXT_INGREDIENTS=30
LLM_MAX_CONTEXT_STEPS=20
LLM_MAX_ANSWER_CHARS=2500
LLM_STRIP_THINK_TAGS=true
```

### 9.3. Рекомендуемые значения для Docker Compose

```yaml
api:
  environment:
    ANSWER_MODE: auto
    LLM_ENABLED: "true"
    LLM_PROVIDER: ollama
    LLM_MODEL: qwen3:4b
    LLM_BASE_URL: http://ollama:11434
    LLM_TIMEOUT_SECONDS: "30"
    LLM_TEMPERATURE: "0.2"
    LLM_MAX_TOKENS: "500"
    LLM_NUM_CTX: "4096"
    LLM_THINK: "false"
    LLM_POSTCHECK_ENABLED: "true"
    LLM_STRICT_CONTEXT: "true"
    LLM_LOG_PROMPTS: "false"
```

Текущий `LLM_TIMEOUT_SECONDS=90` можно оставить для локального Ollama, если модель отвечает медленно. Для пользовательского API лучше стремиться к 20–30 секундам или ниже.

---

## 10. Изменения в `Settings`

Файл:

```text
app/core/config.py
```

Добавить поля:

```python
answer_mode: str
llm_postcheck_enabled: bool
llm_strict_context: bool
llm_log_prompts: bool
llm_log_responses: bool
llm_min_recipes_for_list_answer: int
llm_max_context_recipes: int
llm_max_context_ingredients: int
llm_max_context_steps: int
llm_max_answer_chars: int
llm_strip_think_tags: bool
```

Добавить чтение из env:

```python
answer_mode=os.getenv("ANSWER_MODE", "auto"),
llm_postcheck_enabled=os.getenv("LLM_POSTCHECK_ENABLED", "true").lower() == "true",
llm_strict_context=os.getenv("LLM_STRICT_CONTEXT", "true").lower() == "true",
llm_log_prompts=os.getenv("LLM_LOG_PROMPTS", "false").lower() == "true",
llm_log_responses=os.getenv("LLM_LOG_RESPONSES", "false").lower() == "true",
llm_min_recipes_for_list_answer=int(os.getenv("LLM_MIN_RECIPES_FOR_LIST_ANSWER", "1")),
llm_max_context_recipes=int(os.getenv("LLM_MAX_CONTEXT_RECIPES", "5")),
llm_max_context_ingredients=int(os.getenv("LLM_MAX_CONTEXT_INGREDIENTS", "30")),
llm_max_context_steps=int(os.getenv("LLM_MAX_CONTEXT_STEPS", "20")),
llm_max_answer_chars=int(os.getenv("LLM_MAX_ANSWER_CHARS", "2500")),
llm_strip_think_tags=os.getenv("LLM_STRIP_THINK_TAGS", "true").lower() == "true",
```

Добавить валидацию:

```python
if answer_mode not in {"template", "llm", "auto"}:
    raise ValueError("ANSWER_MODE must be one of: template, llm, auto")
```

---

## 11. Изменения в debug-схеме

Файл:

```text
app/schemas/chat.py
```

В `ChatDebugInfo` добавить optional поле:

```python
class LLMDebugInfo(BaseModel):
    used_llm: bool = False
    provider: str | None = None
    model: str | None = None
    answer_mode: str | None = None
    fallback_reason: str | None = None
    prompt_chars: int | None = None
    response_chars: int | None = None
    latency_ms: int | None = None
    postcheck_passed: bool | None = None
    postcheck_errors: list[str] = Field(default_factory=list)
```

В `ChatDebugInfo`:

```python
llm: LLMDebugInfo | None = None
```

Важно: `prompt` и raw LLM response не возвращать в debug по умолчанию. Их можно логировать только при `LLM_LOG_PROMPTS=true` и только локально.

---

## 12. LLM context layer

Создать файл:

```text
app/services/llm/context.py
```

Цель: отделить контекст, который можно отдавать LLM, от внутренних Pydantic-моделей API.

### 12.1. Почему это нужно

Нельзя просто отдавать всю модель `RecipeDetail` без контроля, потому что:

- prompt может стать слишком длинным;
- в модели могут появиться служебные поля;
- нужно стабильно контролировать, какие факты разрешены LLM;
- post-check должен знать allowed facts.

### 12.2. Рекомендуемые DTO

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class LLMRecipeCardContext(BaseModel):
    rank: int
    recipe_id: int
    title: str
    description: str | None = None
    calories_kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbs_g: float | None = None
    serving_size: str | None = "100 г"
    servings: int | None = None
    cooking_time: str | None = None
    difficulty: str | None = None
    allergens: list[str] = Field(default_factory=list)
    recipe_url: str | None = None
    matched_by: list[str] = Field(default_factory=list)


class LLMIngredientContext(BaseModel):
    name: str
    quantity: str | None = None
    block: str | None = None


class LLMStepContext(BaseModel):
    position: int
    title: str | None = None
    text: str


class LLMRecipeDetailContext(BaseModel):
    recipe_id: int
    title: str
    description: str | None = None
    ingredients: list[LLMIngredientContext] = Field(default_factory=list)
    steps: list[LLMStepContext] = Field(default_factory=list)
    nutrition: dict = Field(default_factory=dict)
    properties: dict = Field(default_factory=dict)
    servings: int | None = None
    recipe_url: str | None = None


class LLMSubstitutionContext(BaseModel):
    target_ingredient: str
    options: list[dict] = Field(default_factory=list)
    found_in_recipe: bool | None = None


class LLMAnswerContext(BaseModel):
    user_message: str
    intent: str
    route: str
    constraints: dict = Field(default_factory=dict)
    recipes: list[LLMRecipeCardContext] = Field(default_factory=list)
    selected_recipe: LLMRecipeDetailContext | None = None
    nutrition: dict | None = None
    substitutions: LLMSubstitutionContext | None = None
    warnings: list[str] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
```

### 12.3. Ограничение размера контекста

Перед отправкой в LLM:

- `recipes` обрезать до `LLM_MAX_CONTEXT_RECIPES`;
- ингредиенты в detail обрезать до `LLM_MAX_CONTEXT_INGREDIENTS`;
- шаги в detail обрезать до `LLM_MAX_CONTEXT_STEPS`;
- длинные descriptions обрезать безопасно;
- raw поля из БД не передавать целиком;
- debug поля не передавать.

---

## 13. Prompt layer

Создать файл:

```text
app/services/llm/prompts.py
```

Вынести туда prompt templates, чтобы `answer_generator.py` не разрастался.

### 13.1. System prompt

```text
Ты — кулинарный ассистент Food Helper.

Твоя задача — сформулировать понятный ответ пользователю на основе переданного JSON-контекста.

Жесткие правила:
1. Используй только факты из контекста.
2. Не добавляй рецепты, которых нет в context.recipes или context.selected_recipe.
3. Не придумывай калории, белки, жиры, углеводы, порции, время, сложность, ингредиенты, шаги или ссылки.
4. Не меняй порядок рецептов и используй их rank из контекста.
5. Если данных нет, так и скажи.
6. Если есть warnings, добавь их в конце ответа спокойной формулировкой.
7. Не давай медицинских гарантий по аллергиям.
8. Если речь о замене ингредиента, явно скажи, что это адаптация рецепта, а не исходная инструкция из базы.
9. Не пересчитывай КБЖУ после замены ингредиентов.
10. Отвечай по-русски.
11. Ответ должен быть дружелюбным, но без лишней воды.

Запрещено:
- писать “я нашел” рецепт, которого нет в JSON;
- ссылаться на внешние источники;
- говорить, что блюдо безопасно при аллергии;
- скрывать, что данных недостаточно;
- давать медицинские рекомендации.
```

### 13.2. Prompt для списка рецептов

```text
Пользовательский запрос:
{user_message}

JSON-контекст:
{context_json}

Сформулируй ответ для списка рецептов.

Требования:
- Начни с короткой фразы, что найдено несколько вариантов.
- Перечисли рецепты в порядке rank.
- Для каждого рецепта укажи название точно как в контексте.
- Для каждого рецепта дай 1 короткую причину, почему он может подойти.
- Можно использовать калории, БЖУ, время, сложность и аллергены только если они есть в JSON.
- Не добавляй рецепты, которых нет в JSON.
- Если есть warnings, добавь их в конце.
- Не делай медицинских гарантий.
```

### 13.3. Prompt для деталей рецепта

```text
Пользовательский запрос:
{user_message}

JSON-контекст:
{context_json}

Сформулируй ответ по выбранному рецепту.

Требования:
- Используй только selected_recipe.
- Если пользователь спрашивает ингредиенты, покажи ингредиенты из context.selected_recipe.ingredients.
- Если пользователь спрашивает шаги, покажи шаги из context.selected_recipe.steps.
- Не добавляй ингредиенты или шаги.
- Не меняй смысл инструкции.
- Если часть данных отсутствует, скажи, что этих данных нет в базе.
```

### 13.4. Prompt для КБЖУ

```text
Пользовательский запрос:
{user_message}

JSON-контекст:
{context_json}

Сформулируй ответ про калории или БЖУ.

Требования:
- Используй только nutrition values из JSON.
- Не пересчитывай значения.
- Не меняй единицы измерения.
- Если значения относятся к 100 г, явно укажи это.
- Если пользователь спрашивает только белок, не обязательно перечислять все БЖУ.
- Если данных нет, скажи, что в базе нет этих данных.
```

### 13.5. Prompt для замены ингредиента

```text
Пользовательский запрос:
{user_message}

JSON-контекст:
{context_json}

Сформулируй ответ про замену ингредиента.

Требования:
- Используй только substitutions.options из JSON.
- Не добавляй новые варианты замены, если их нет в JSON.
- Для каждого варианта укажи ratio, если он есть.
- Для каждого варианта укажи note, если он есть.
- Обязательно скажи, что это адаптация рецепта.
- Обязательно скажи, что КБЖУ после замены не пересчитаны.
- Если есть warnings, добавь их в конце.
```

### 13.6. Prompt для пустой выдачи

Для MVP лучше не вызывать LLM при пустой выдаче. Если все-таки понадобится включить LLM для empty result, использовать отдельный безопасный prompt:

```text
Пользовательский запрос:
{user_message}

Поиск по базе не нашел подходящих рецептов.
Ограничения пользователя:
{constraints_json}

Сформулируй короткий ответ.

Требования:
- Не придумывай рецепты.
- Скажи, что подходящих рецептов в базе не найдено.
- Предложи изменить условия поиска.
- Не обещай, что рецепт существует.
```

---

## 14. Доработка `AnswerGenerator`

Файл:

```text
app/services/answer_generator.py
```

Сейчас есть только базовая генерация ответа для списка рецептов. Нужно расширить класс до набора методов по сценариям.

### 14.1. Целевой публичный интерфейс

```python
class AnswerGenerator:
    def generate_recipe_list_answer(...):
        ...

    def generate_recipe_detail_answer(...):
        ...

    def generate_nutrition_answer(...):
        ...

    def generate_nutrition_candidates_answer(...):
        ...

    def generate_substitution_answer(...):
        ...

    def generate_general_substitution_answer(...):
        ...

    def generate_similar_recipes_answer(...):
        ...

    def generate_empty_results_answer(...):
        ...

    def generate_missing_context_answer(...):
        ...
```

### 14.2. Универсальный внутренний метод

```python
def _generate_or_fallback(
    self,
    *,
    scenario: str,
    user_message: str,
    fallback_answer: str,
    context: LLMAnswerContext,
    allow_llm: bool,
    postcheck_policy: PostcheckPolicy,
) -> AnswerGenerationResult:
    ...
```

### 14.3. Результат генерации

Создать файл:

```text
app/services/llm/result.py
```

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AnswerGenerationResult:
    answer: str
    used_llm: bool
    fallback_reason: str | None = None
    latency_ms: int | None = None
    prompt_chars: int | None = None
    response_chars: int | None = None
    postcheck_passed: bool | None = None
    postcheck_errors: list[str] = field(default_factory=list)
```

На первом шаге можно не менять `ChatPipeline` на этот result полностью, а внутри `AnswerGenerator` возвращать строку. Но лучше сразу возвращать `AnswerGenerationResult`, чтобы debug и логирование были нормальными.

---

## 15. Post-check слой

Создать файл:

```text
app/services/llm/postcheck.py
```

Цель: защититься от очевидных hallucinations.

Post-check не должен быть идеальным NLP-детектором. Его задача — поймать грубые нарушения.

### 15.1. Проверки MVP

Проверять:

- ответ не пустой;
- длина ответа не больше `LLM_MAX_ANSWER_CHARS`;
- в ответе нет `<think>` или скрытых reasoning-блоков;
- если сценарий recipe list, все упомянутые номера рецептов входят в допустимый диапазон;
- если сценарий recipe list, ответ не содержит названий рецептов вне allowed titles;
- если сценарий detail, ответ не содержит чужих recipe titles;
- если сценарий nutrition, ответ не содержит чисел КБЖУ, которых нет в context;
- если warnings содержат allergy warning, ответ не говорит “безопасно при аллергии”;
- если сценарий substitution, ответ содержит маркер адаптации или предупреждение;
- если `LLM_STRICT_CONTEXT=true`, запрещать новые варианты замен.

### 15.2. Пример интерфейса

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PostcheckResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    sanitized_answer: str | None = None


@dataclass(frozen=True)
class PostcheckPolicy:
    scenario: str
    strict_context: bool = True
    max_answer_chars: int = 2500
    strip_think_tags: bool = True
```

```python
def validate_llm_answer(
    *,
    answer: str,
    context: LLMAnswerContext,
    policy: PostcheckPolicy,
) -> PostcheckResult:
    ...
```

### 15.3. Sanitization

Если `LLM_STRIP_THINK_TAGS=true`, удалять:

```text
<think>...</think>
```

и похожие блоки, если локальная модель случайно их вернула.

Если после удаления ответ пустой — fallback.

### 15.4. Простая проверка title hallucination

Для recipe list:

```python
allowed_titles = {recipe.title.lower() for recipe in context.recipes}
```

Проверять можно мягко:

- не требовать, чтобы все titles были упомянуты;
- но если в ответе есть форматированный список с неизвестным названием, fallback;
- если ответ содержит URL, которого нет в sources, fallback.

### 15.5. Проверка медицинских гарантий

Запрещенные фразы:

```text
точно безопасно
полностью безопасно
можно при любой аллергии
гарантированно без аллергена
медицински безопасно
```

Если такие фразы есть — fallback или заменить ответ на fallback.

---

## 16. Fallback matrix

### 16.1. Причины fallback

Использовать стандартизированные коды:

```text
answer_mode_template
llm_disabled
llm_client_null
no_context
empty_recipes
missing_recipe_context
llm_timeout
llm_http_error
llm_empty_response
llm_exception
postcheck_failed
postcheck_too_long
postcheck_hallucinated_recipe
postcheck_hallucinated_nutrition
postcheck_medical_guarantee
```

### 16.2. Правила

```text
Любая ошибка LLM не должна приводить к 500.
Любая ошибка LLM должна возвращать fallback answer.
Любая ошибка LLM должна быть видна в logs.
Если include_debug=true, причина fallback должна быть видна в debug.llm.fallback_reason.
```

### 16.3. Исключение

Ошибки в deterministic pipeline не маскировать как LLM fallback.

Например:

- БД недоступна → 503;
- пустой message → 400;
- слишком длинный message → 400;
- recipe not found в `GET /v1/recipes/{id}` → 404.

---

## 17. Интеграция с `ChatPipeline`

Файл:

```text
app/orchestrator/pipeline.py
```

### 17.1. Общий паттерн

В каждом сценарии:

1. Получить deterministic data.
2. Сформировать fallback answer.
3. Вызвать `AnswerGenerator`.
4. Получить `AnswerGenerationResult`.
5. Положить `result.answer` в `ChatResponse.answer`.
6. При `include_debug=true` добавить `debug.llm`.

### 17.2. Search/recommend/allergy

Уже частично сделано:

```python
fallback_answer = self._render_recipe_list_answer(decision.intent, recipes)
answer = self._answer_generator.generate_recipe_list_answer(...)
```

Нужно заменить на result:

```python
answer_result = self._answer_generator.generate_recipe_list_answer(
    user_message=message,
    fallback_answer=fallback_answer,
    recipes=recipes,
    constraints=constraints,
    warnings=warnings,
    intent=decision.intent,
    route=decision.route,
    sources=self._sources_from_cards(recipes),
)
```

И в response:

```python
answer=answer_result.answer
```

### 17.3. Nutrition selected recipe

Сейчас answer формируется так:

```python
answer = self._nutrition_service.format_answer(detail.title, nutrition, nutrient)
```

Нужно:

```python
fallback_answer = self._nutrition_service.format_answer(detail.title, nutrition, nutrient)
answer_result = self._answer_generator.generate_nutrition_answer(
    user_message=message,
    fallback_answer=fallback_answer,
    recipe=detail,
    nutrition=nutrition,
    nutrient=nutrient,
    warnings=warnings,
    intent=decision.intent,
    route=decision.route,
)
```

### 17.4. Nutrition candidates

Сейчас answer формируется так:

```python
answer = self._render_nutrition_candidate_answer(...)
```

Нужно:

```python
fallback_answer = self._render_nutrition_candidate_answer(...)
answer_result = self._answer_generator.generate_nutrition_candidates_answer(
    user_message=message,
    fallback_answer=fallback_answer,
    recipes=recipes,
    nutrients=nutrients,
    constraints=constraints,
    warnings=warnings,
    intent=decision.intent,
    route="hybrid_search",
)
```

### 17.5. Recipe details

Сейчас:

```python
answer=self._render_recipe_detail_answer(message, detail)
```

Нужно:

```python
fallback_answer = self._render_recipe_detail_answer(message, detail)
answer_result = self._answer_generator.generate_recipe_detail_answer(
    user_message=message,
    fallback_answer=fallback_answer,
    recipe=detail,
    warnings=warnings,
    intent=decision.intent,
    route=decision.route,
)
```

### 17.6. General substitution

Сейчас:

```python
answer = self._render_general_substitutions_answer(target, substitution.options)
```

Нужно:

```python
fallback_answer = self._render_general_substitutions_answer(target, substitution.options)
answer_result = self._answer_generator.generate_general_substitution_answer(
    user_message=message,
    fallback_answer=fallback_answer,
    target_ingredient=target,
    substitutions=substitution.options,
    warnings=warnings,
    intent=decision.intent,
    route=decision.route,
)
```

### 17.7. Recipe-bound substitution

Сейчас:

```python
answer = self._render_substitutions_answer(detail.title, str(target), substitution.options)
```

Нужно:

```python
fallback_answer = self._render_substitutions_answer(detail.title, str(target), substitution.options)
answer_result = self._answer_generator.generate_substitution_answer(
    user_message=message,
    fallback_answer=fallback_answer,
    recipe=detail,
    target_ingredient=str(target),
    substitutions=substitution.options,
    warnings=warnings,
    intent=decision.intent,
    route=decision.route,
)
```

### 17.8. Similar recipes

Уже используется recipe list generator. Нужно передавать base recipe title в context.

---

## 18. LLMClient layer

Файлы:

```text
app/services/llm/base.py
app/services/llm/null.py
app/services/llm/ollama.py
```

### 18.1. Текущий интерфейс

Сейчас `LLMClient.generate(...)` возвращает `str`.

Для MVP можно оставить такой интерфейс, но желательно добавить отдельный result с метаданными позже.

### 18.2. Минимальная доработка

Добавить custom exceptions:

```text
app/services/llm/errors.py
```

```python
class LLMError(Exception):
    pass

class LLMDisabledError(LLMError):
    pass

class LLMTimeoutError(LLMError):
    pass

class LLMEmptyResponseError(LLMError):
    pass

class LLMProviderError(LLMError):
    pass
```

`NullLLMClient` должен бросать `LLMDisabledError`, а не generic `RuntimeError`.

`OllamaLLMClient` должен:

- ловить `httpx.TimeoutException`;
- бросать `LLMTimeoutError`;
- ловить HTTP errors;
- бросать `LLMProviderError`;
- при пустом response бросать `LLMEmptyResponseError`.

Пример:

```python
try:
    response = client.post(...)
    response.raise_for_status()
except httpx.TimeoutException as exc:
    raise LLMTimeoutError("LLM request timed out") from exc
except httpx.HTTPError as exc:
    raise LLMProviderError("LLM provider error") from exc
```

---

## 19. Логирование

На каждый вызов LLM логировать:

```json
{
  "event": "llm_answer_generation",
  "request_id": "...",
  "conversation_id": "...",
  "intent": "search_recipes",
  "route": "hybrid_search",
  "scenario": "recipe_list",
  "answer_mode": "auto",
  "provider": "ollama",
  "model": "qwen3:4b",
  "used_llm": true,
  "fallback_reason": null,
  "latency_ms": 1820,
  "prompt_chars": 3120,
  "response_chars": 860,
  "postcheck_passed": true,
  "postcheck_errors": []
}
```

Не логировать prompt и response по умолчанию.

Если `LLM_LOG_PROMPTS=true`, логировать только в dev-режиме и без персональных данных.

---

## 20. Безопасность и privacy

### 20.1. Не отправлять лишнее в LLM

В prompt нельзя передавать:

- внутренние debug structures;
- DSN;
- env-переменные;
- сырые stack traces;
- системные ошибки;
- персональные данные пользователя, если они не нужны для ответа.

### 20.2. Аллергии

Если пользователь указал аллергию или запрет:

- deterministic pipeline добавляет warning;
- LLM обязана включить warning в ответ;
- LLM не может писать “рецепт безопасен”;
- LLM может писать только “отфильтровано по данным базы”.

Разрешенная формулировка:

```text
Я отфильтровал рецепты по данным базы, но при аллергиях обязательно проверьте состав конкретных продуктов и возможные следы аллергенов на упаковке.
```

Запрещенная формулировка:

```text
Этот рецепт полностью безопасен при аллергии.
```

### 20.3. Медицинские ограничения

LLM не должна:

- ставить диагноз;
- рекомендовать лечебную диету;
- говорить, что блюдо подходит при заболевании;
- обещать безопасность для диабета, целиакии, аллергии и других состояний.

---

## 21. Требования к качеству ответа

Ответ должен быть:

- на русском языке;
- коротким, но полезным;
- конкретным;
- без выдуманных фактов;
- с сохранением порядка рецептов;
- с понятными предупреждениями;
- без чрезмерного markdown;
- без длинных вступлений;
- без фраз вроде “как искусственный интеллект”.

Для списка рецептов оптимальная структура:

```text
Я нашел несколько вариантов под ваш запрос:

1. Название — почему подходит.
2. Название — почему подходит.
3. Название — почему подходит.

Предупреждение, если нужно.
```

Для деталей рецепта:

```text
Вот детали рецепта “Название”.

Ингредиенты:
- ...
- ...

Первые шаги:
1. ...
2. ...
```

Для КБЖУ:

```text
В рецепте “Название” указаны значения на 100 г:
- калории: ... кКал;
- белки: ... г;
- жиры: ... г;
- углеводы: ... г.
```

Для замены:

```text
В рецепте “Название” вместо “молоко” можно попробовать:

1. Растительное молоко — 1:1. Может немного изменить вкус.
2. Вода — 1:1. Вкус может стать менее насыщенным.

Это адаптация рецепта, а не исходная инструкция из базы. КБЖУ после замены не пересчитаны.
```

---

## 22. Тестирование

### 22.1. Unit-тесты `AnswerGenerator`

Файл:

```text
tests/test_answer_generator.py
```

Покрыть:

```text
- NullLLMClient → возвращается fallback.
- LLM disabled → возвращается fallback.
- ANSWER_MODE=template → LLM не вызывается.
- recipes=[] → LLM не вызывается для recipe_list.
- LLM возвращает нормальный ответ → используется LLM answer.
- LLM бросает timeout → fallback.
- LLM бросает provider error → fallback.
- LLM возвращает пустую строку → fallback.
- LLM возвращает слишком длинный ответ → fallback.
- LLM возвращает запрещенную medical guarantee → fallback.
- LLM возвращает unknown recipe title → fallback.
```

Пример fake client:

```python
class FakeLLMClient:
    def __init__(self, response: str | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls = []

    def generate(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.response or ""
```

### 22.2. Unit-тесты post-check

Файл:

```text
tests/test_llm_postcheck.py
```

Проверить:

```text
- empty answer rejected;
- answer over max chars rejected;
- <think>...</think> stripped;
- answer with only think block rejected after strip;
- unknown recipe title rejected in strict mode;
- allowed recipe title accepted;
- forbidden allergy guarantee rejected;
- substitution answer without adaptation warning rejected;
- nutrition answer with unknown numeric value rejected in strict mode.
```

### 22.3. Pipeline tests

Файл:

```text
tests/test_chat_pipeline_llm.py
```

Проверить:

```text
- search_recipes вызывает AnswerGenerator;
- recipe_details вызывает AnswerGenerator;
- nutrition_question вызывает AnswerGenerator;
- ingredient_substitution вызывает AnswerGenerator;
- missing context не вызывает LLM в auto mode;
- empty recipes не вызывает LLM в auto mode;
- debug.llm заполняется при include_debug=true;
- debug.llm отсутствует или null при include_debug=false.
```

### 22.4. API tests

Расширить:

```text
tests/test_api.py
```

Добавить проверки:

```text
- /v1/chat возвращает answer при LLM unavailable;
- /v1/chat не меняет recipes из-за LLM;
- /v1/chat include_debug=true содержит debug.llm;
- /v1/chat при слишком длинном message не вызывает LLM;
- /v1/chat при DB error не вызывает LLM.
```

### 22.5. Eval cases

Создать файл:

```text
tests/eval_cases/chat_llm_answer_cases.jsonl
```

Пример:

```json
{"message":"Найди легкий ужин с курицей без грибов","expected_intent_any":["search_recipes","recommend_recipes"],"must_use_llm_when_available":true,"must_not_hallucinate_recipe":true,"must_keep_recipe_order":true}
{"message":"Найди рецепт без молока","expected_route":"hybrid_search","must_include_warning_if_allergy":false,"must_not_include_excluded_ingredient":"молоко"}
{"message":"У меня аллергия на яйцо, что подойдет?","expected_intent_any":["allergy_or_exclusion","search_recipes"],"must_include_allergy_warning":true,"must_not_say_medically_safe":true}
{"message":"Сколько калорий и белка в рецепте с курицей?","expected_intent":"nutrition_question","must_not_recalculate_nutrition":true,"must_include_units":true}
{"message":"Чем заменить молоко?","expected_intent":"general_substitution","must_say_general_not_recipe_bound":true}
```

Создать скрипт:

```text
scripts/eval/run_chat_llm_eval.py
```

Минимальная логика:

```text
1. Читать jsonl cases.
2. Отправлять запросы в TestClient или живой API.
3. Проверять intent/route.
4. Проверять, что answer не пустой.
5. Проверять базовые must_not фразы.
6. Проверять отсутствие unknown recipe titles, если есть recipes.
7. Выводить summary pass/fail.
```

---

## 23. Ручные проверки

### 23.1. Поднять сервисы

```bash
docker compose up -d db ollama api
```

Если модель не загружена:

```bash
docker compose exec ollama ollama pull qwen3:4b
```

Health:

```bash
curl http://localhost:8000/health
```

### 23.2. Проверка LLM recipe list

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Посоветуй легкий ужин с курицей без грибов",
    "options": {"top_k": 5, "include_debug": true}
  }'
```

Ожидаемо:

```text
- HTTP 200;
- answer звучит естественно;
- recipes не пустой;
- debug.llm.used_llm=true, если LLM доступна;
- debug.llm.fallback_reason=null или понятная причина fallback.
```

### 23.3. Проверка fallback при выключенной LLM

В `.env` или compose:

```text
ANSWER_MODE=template
```

Перезапустить API:

```bash
docker compose restart api
```

Повторить запрос.

Ожидаемо:

```text
- HTTP 200;
- answer есть;
- debug.llm.used_llm=false;
- debug.llm.fallback_reason=answer_mode_template.
```

### 23.4. Проверка recipe details

Сначала поиск:

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Найди рецепты с творогом","options":{"top_k":3,"include_debug":true}}'
```

Потом взять `conversation_id` и выполнить:

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id":"PASTE_CONVERSATION_ID",
    "message":"Покажи первый рецепт подробнее",
    "options":{"top_k":3,"include_debug":true}
  }'
```

Ожидаемо:

```text
- selected_recipe заполнен;
- answer использует данные selected_recipe;
- LLM не добавляет чужие ингредиенты.
```

### 23.5. Проверка allergy warning

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message":"У меня аллергия на яйцо, что можно приготовить?",
    "options":{"top_k":5,"include_debug":true}
  }'
```

Ожидаемо:

```text
- warnings содержит предупреждение;
- answer не говорит “полностью безопасно”;
- answer советует проверять состав продуктов и следы аллергенов.
```

---

## 24. Критерии приемки

### 24.1. Функциональные

```text
[ ] ANSWER_MODE=template работает без LLM.
[ ] ANSWER_MODE=auto вызывает LLM только при наличии context.
[ ] ANSWER_MODE=llm вызывает LLM там, где сценарий поддержан.
[ ] При ошибке Ollama API возвращает fallback answer.
[ ] При пустом ответе Ollama API возвращает fallback answer.
[ ] При post-check failure API возвращает fallback answer.
[ ] Recipe list answer не добавляет рецепты вне recipes.
[ ] Recipe detail answer не добавляет ингредиенты/шаги вне selected_recipe.
[ ] Nutrition answer не пересчитывает КБЖУ.
[ ] Substitution answer не добавляет варианты вне substitution options в strict mode.
[ ] Allergy answer не дает медицинских гарантий.
[ ] ChatResponse сохраняет прежний JSON-контракт.
[ ] include_debug=true показывает LLM debug info.
```

### 24.2. Тестовые

```text
[ ] Добавлены unit-тесты AnswerGenerator.
[ ] Добавлены unit-тесты post-check.
[ ] Добавлены pipeline-тесты LLM/fallback.
[ ] Расширены API smoke tests.
[ ] Добавлен jsonl eval-набор.
[ ] python -m pytest -q проходит локально.
[ ] docker compose exec embed python -m pytest tests/ -q проходит в контейнере.
```

### 24.3. Нефункциональные

```text
[ ] API не падает при недоступной LLM.
[ ] LLM timeout ограничен настройкой.
[ ] Prompt не содержит секретов и DSN.
[ ] Raw prompt не логируется по умолчанию.
[ ] Ответ LLM ограничен по длине.
[ ] Логи содержат provider/model/latency/fallback_reason.
[ ] Поведение без LLM остается стабильным.
```

---

## 25. Пошаговый план внедрения

### Этап 1. Конфигурация и режимы ответа

Задачи:

```text
[ ] Добавить ANSWER_MODE в Settings.
[ ] Добавить LLM_POSTCHECK_ENABLED.
[ ] Добавить LLM_STRICT_CONTEXT.
[ ] Добавить LLM_MAX_ANSWER_CHARS.
[ ] Добавить LLM_STRIP_THINK_TAGS.
[ ] Обновить docker-compose.yaml.
[ ] Обновить docs/docker-compose.md.
```

Результат:

```text
Проект умеет явно работать в template/auto/llm режиме.
```

### Этап 2. Context и prompts

Задачи:

```text
[ ] Создать app/services/llm/context.py.
[ ] Создать app/services/llm/prompts.py.
[ ] Добавить функции сборки context из RecipeCard/RecipeDetail/Nutrition/Substitution.
[ ] Ограничить размер context.
[ ] Добавить unit-тесты context builder.
```

Результат:

```text
LLM получает контролируемый JSON-context, а не произвольные внутренние модели.
```

### Этап 3. Расширение AnswerGenerator

Задачи:

```text
[ ] Добавить AnswerGenerationResult.
[ ] Добавить общий _generate_or_fallback.
[ ] Переписать generate_recipe_list_answer на новый result.
[ ] Добавить generate_recipe_detail_answer.
[ ] Добавить generate_nutrition_answer.
[ ] Добавить generate_nutrition_candidates_answer.
[ ] Добавить generate_substitution_answer.
[ ] Добавить generate_general_substitution_answer.
[ ] Добавить generate_similar_recipes_answer.
[ ] Добавить тесты ошибок LLM.
```

Результат:

```text
Все основные user-facing сценарии могут получить LLM answer, но имеют fallback.
```

### Этап 4. Post-check

Задачи:

```text
[ ] Создать app/services/llm/postcheck.py.
[ ] Реализовать empty/length checks.
[ ] Реализовать strip think tags.
[ ] Реализовать allergy medical guarantee check.
[ ] Реализовать basic recipe title guard.
[ ] Реализовать basic nutrition number guard.
[ ] Реализовать substitution strict guard.
[ ] Добавить tests/test_llm_postcheck.py.
```

Результат:

```text
Грубые hallucinations ловятся до ответа пользователю.
```

### Этап 5. Интеграция в ChatPipeline

Задачи:

```text
[ ] Подключить result-based AnswerGenerator в search/recommend/allergy.
[ ] Подключить в similar_recipes.
[ ] Подключить в recipe_details.
[ ] Подключить в nutrition_question selected recipe.
[ ] Подключить в nutrition candidates.
[ ] Подключить в ingredient_substitution.
[ ] Подключить в general_substitution.
[ ] Не вызывать LLM при missing context в auto mode.
[ ] Не вызывать LLM при empty recipes в auto mode.
```

Результат:

```text
LLM покрывает основные chat branches.
```

### Этап 6. Debug и logging

Задачи:

```text
[ ] Добавить LLMDebugInfo.
[ ] Протянуть answer_result в _build_debug.
[ ] Логировать llm_answer_generation event.
[ ] Не логировать prompt/response по умолчанию.
[ ] Добавить тест include_debug=true.
```

Результат:

```text
Можно понять, использовалась ли LLM и почему случился fallback.
```

### Этап 7. Eval и документация

Задачи:

```text
[ ] Добавить tests/eval_cases/chat_llm_answer_cases.jsonl.
[ ] Добавить scripts/eval/run_chat_llm_eval.py.
[ ] Обновить docs/api-test-requests.md.
[ ] Добавить docs/llm-answer-generator-mvp.md.
[ ] Добавить README-секцию про ANSWER_MODE.
```

Результат:

```text
Есть воспроизводимый способ проверить качество LLM answer layer.
```

---

## 26. Пример целевой структуры файлов

```text
app/
  core/
    config.py
  orchestrator/
    pipeline.py
  services/
    answer_generator.py
    llm/
      __init__.py
      base.py
      context.py
      errors.py
      null.py
      ollama.py
      postcheck.py
      prompts.py
      result.py
  schemas/
    chat.py

tests/
  test_answer_generator.py
  test_llm_postcheck.py
  test_chat_pipeline_llm.py
  test_api.py
  eval_cases/
    chat_llm_answer_cases.jsonl

scripts/
  eval/
    run_chat_llm_eval.py

docs/
  llm-answer-generator-mvp.md
  llm-answer-generator-mvp-tz.md
```

---

## 27. Пример псевдокода `AnswerGenerator`

```python
class AnswerGenerator:
    def generate_recipe_list_answer(
        self,
        *,
        user_message: str,
        fallback_answer: str,
        recipes: list[RecipeCard],
        constraints: QueryConstraints,
        warnings: list[str],
        intent: str,
        route: str,
        sources: list[SourceInfo],
    ) -> AnswerGenerationResult:
        if not recipes:
            return AnswerGenerationResult(
                answer=fallback_answer,
                used_llm=False,
                fallback_reason="empty_recipes",
            )

        context = build_recipe_list_context(
            user_message=user_message,
            intent=intent,
            route=route,
            recipes=recipes,
            constraints=constraints,
            warnings=warnings,
            sources=sources,
            max_recipes=self._settings.llm_max_context_recipes,
        )

        return self._generate_or_fallback(
            scenario="recipe_list",
            user_message=user_message,
            fallback_answer=fallback_answer,
            context=context,
            allow_llm=True,
            postcheck_policy=PostcheckPolicy(
                scenario="recipe_list",
                strict_context=self._settings.llm_strict_context,
                max_answer_chars=self._settings.llm_max_answer_chars,
                strip_think_tags=self._settings.llm_strip_think_tags,
            ),
        )
```

---

## 28. Пример `_generate_or_fallback`

```python
def _generate_or_fallback(
    self,
    *,
    scenario: str,
    user_message: str,
    fallback_answer: str,
    context: LLMAnswerContext,
    allow_llm: bool,
    postcheck_policy: PostcheckPolicy,
) -> AnswerGenerationResult:
    if self._settings.answer_mode == "template":
        return AnswerGenerationResult(
            answer=fallback_answer,
            used_llm=False,
            fallback_reason="answer_mode_template",
        )

    if not self._settings.llm_enabled:
        return AnswerGenerationResult(
            answer=fallback_answer,
            used_llm=False,
            fallback_reason="llm_disabled",
        )

    if not allow_llm and self._settings.answer_mode == "auto":
        return AnswerGenerationResult(
            answer=fallback_answer,
            used_llm=False,
            fallback_reason="no_context",
        )

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(scenario=scenario, context=context)

    started = time.perf_counter()
    try:
        raw_answer = self._llm_client.generate(
            LLMGenerateRequest(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=self._settings.llm_temperature,
                max_tokens=self._settings.llm_max_tokens,
                num_ctx=self._settings.llm_num_ctx,
                think=self._settings.llm_think,
            )
        )
    except LLMTimeoutError:
        return AnswerGenerationResult(fallback_answer, False, "llm_timeout")
    except LLMEmptyResponseError:
        return AnswerGenerationResult(fallback_answer, False, "llm_empty_response")
    except LLMError:
        return AnswerGenerationResult(fallback_answer, False, "llm_exception")
    except Exception:
        return AnswerGenerationResult(fallback_answer, False, "llm_exception")

    latency_ms = int((time.perf_counter() - started) * 1000)

    if self._settings.llm_postcheck_enabled:
        postcheck = validate_llm_answer(
            answer=raw_answer,
            context=context,
            policy=postcheck_policy,
        )
        if not postcheck.ok:
            return AnswerGenerationResult(
                answer=fallback_answer,
                used_llm=False,
                fallback_reason="postcheck_failed",
                latency_ms=latency_ms,
                prompt_chars=len(user_prompt),
                response_chars=len(raw_answer),
                postcheck_passed=False,
                postcheck_errors=postcheck.errors,
            )
        final_answer = postcheck.sanitized_answer or raw_answer
    else:
        final_answer = raw_answer.strip()

    if not final_answer:
        return AnswerGenerationResult(
            answer=fallback_answer,
            used_llm=False,
            fallback_reason="llm_empty_response",
            latency_ms=latency_ms,
        )

    return AnswerGenerationResult(
        answer=final_answer,
        used_llm=True,
        fallback_reason=None,
        latency_ms=latency_ms,
        prompt_chars=len(user_prompt),
        response_chars=len(final_answer),
        postcheck_passed=True,
    )
```

---

## 29. Важные ограничения MVP

В этот этап не входит:

- LLM-router;
- tool calling;
- LangChain/LlamaIndex agent;
- генерация новых рецептов;
- пересчет КБЖУ после замены;
- персональный профиль пользователя;
- meal planner;
- shopping list;
- fine-tuning;
- RAG over external websites;
- медицинские рекомендации;
- гарантия аллергенной безопасности;
- frontend.

Эти вещи можно рассматривать после того, как answer generator станет стабильным и покрытым тестами.

---

## 30. Риски и как их снизить

### 30.1. Риск: LLM выдумывает рецепт

Снижение:

```text
- strict context;
- prompt rule “только рецепты из JSON”;
- post-check по titles;
- fallback при нарушении.
```

### 30.2. Риск: LLM выдумывает КБЖУ

Снижение:

```text
- nutrition prompt;
- запрет пересчета;
- numeric guard;
- fallback.
```

### 30.3. Риск: LLM дает медицинские гарантии

Снижение:

```text
- allergy warning из deterministic pipeline;
- system prompt;
- forbidden phrases check;
- fallback.
```

### 30.4. Риск: Ollama медленно отвечает

Снижение:

```text
- ANSWER_MODE=template для быстрого режима;
- timeout;
- max_tokens;
- ограничение context;
- логирование latency;
- fallback при timeout.
```

### 30.5. Риск: prompt слишком большой

Снижение:

```text
- max recipes;
- max ingredients;
- max steps;
- no raw fields;
- prompt_chars in debug/logs.
```

---

## 31. Definition of Done

MVP считается завершенным, когда выполнено следующее:

```text
[ ] Все основные ветки ChatPipeline имеют fallback answer.
[ ] Все основные ветки ChatPipeline могут использовать AnswerGenerator.
[ ] LLM never controls recipe selection.
[ ] LLM never controls filters.
[ ] LLM never controls intent/route.
[ ] LLM output проходит post-check.
[ ] При любой ошибке LLM возвращается fallback.
[ ] Добавлен debug.llm.
[ ] Добавлены unit/pipeline/API тесты.
[ ] Добавлены eval cases.
[ ] Обновлена документация по запуску.
[ ] Docker Compose сценарий с Ollama проверен вручную.
[ ] ANSWER_MODE=template проверен вручную.
[ ] ANSWER_MODE=auto проверен вручную.
```

---

## 32. Рекомендуемый следующий этап после MVP

После стабилизации answer generator можно переходить к следующему этапу:

```text
LLM = structured parser для сложных пользовательских запросов
```

Но только после того, как:

- есть eval-набор;
- post-check работает;
- fallback стабилен;
- понятно, где ошибается deterministic parser;
- есть логи качества intent/constraints.

Следующий этап не должен заменять текущий `IntentRouter` полностью. Лучше добавить LLM parser как fallback для сложных запросов с обязательной JSON schema validation.

---

## 33. Источники по текущему проекту

Этот документ составлен под текущую структуру проекта `food_helper`:

- README проекта: `https://github.com/ShirinKhan1/food_helper`
- Архитектурное ТЗ RAG: `https://raw.githubusercontent.com/ShirinKhan1/food_helper/main/docs/food_helper_rag_tz.md`
- Chat pipeline: `https://raw.githubusercontent.com/ShirinKhan1/food_helper/main/app/orchestrator/pipeline.py`
- Intent router: `https://raw.githubusercontent.com/ShirinKhan1/food_helper/main/app/orchestrator/intent_router.py`
- Query constraints: `https://raw.githubusercontent.com/ShirinKhan1/food_helper/main/app/orchestrator/query_constraints.py`
- Answer generator: `https://raw.githubusercontent.com/ShirinKhan1/food_helper/main/app/services/answer_generator.py`
- LLM base/null/ollama clients: `https://github.com/ShirinKhan1/food_helper/tree/main/app/services/llm`
- Docker Compose: `https://raw.githubusercontent.com/ShirinKhan1/food_helper/main/docker-compose.yaml`
- API manual checks: `https://raw.githubusercontent.com/ShirinKhan1/food_helper/main/docs/api-test-requests.md`
