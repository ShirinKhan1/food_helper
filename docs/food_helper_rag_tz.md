# Техническое задание: RAG-приложение по рецептам `food_helper`

## 1. Цель проекта

Разработать RAG-приложение по рецептам, в котором пользователь может задавать вопросы на естественном языке, а система отвечает с опорой на существующую базу рецептов и векторную базу эмбеддингов.

Приложение должно уметь:

- искать рецепты по названию, ингредиентам, описанию и смыслу запроса;
- подбирать рецепты под ограничения: без мяса, без сахара, без молока, без глютена, низкокалорийное, быстрое, легкое;
- отвечать на вопросы о калориях, белках, жирах и углеводах;
- помогать заменять ингредиенты в конкретном рецепте;
- учитывать аллергию или отсутствие продукта;
- поддерживать диалоговые ссылки вида “третий рецепт”, “этот рецепт”, “а во втором?”;
- возвращать понятный ответ пользователю и структурированные данные для фронтенда.

Система не должна выдумывать факты о конкретном рецепте. Калории, БЖУ, ингредиенты, шаги, аллергенные свойства и ссылки должны браться из БД.

---

## 2. Текущий статус проекта

В репозитории уже есть:

- Postgres + pgvector через Docker Compose;
- таблица `recipes`;
- таблица `recipe_embeddings`;
- загрузчик JSONL-рецептов в Postgres;
- скрипт расчета эмбеддингов;
- CLI-поиск по pgvector;
- FastAPI HTTP API с `/health`, `/v1/chat`, `/v1/search/debug`, `/v1/recipes/{recipe_id}`;
- deterministic-first чатовый orchestrator (`IntentRouter` + `ChatPipeline`);
- гибридный поиск с vector + keyword + rule score;
- структурированные ограничения запроса: include/exclude ingredients, allergy/forbidden, meal type, calorie/fat/time/difficulty limits;
- hard-filter по исключенным ингредиентам и аллергенам для `final_results`;
- состояние диалога с `last_recipe_results` и `selected_recipe_id`;
- обработка ссылок “первый / второй / третий рецепт”, “этот рецепт”, “в нём”;
- сервис калорий и БЖУ на данных рецепта;
- recipe-bound и общий rule-based сервис замены ингредиентов;
- unit, API, scenario и eval-тесты для основных RAG-сценариев.

Пока не реализовано или остается за следующими этапами:

- генерация финального ответа через LLM;
- fallback-политики;
- frontend;
- авторизация;
- production monitoring;
- медицинские гарантии по аллергенам;
- пересчет калорийности после замены ингредиентов.

---

## 3. Принятый стек для разработки

Для MVP использовать текущий стек проекта:

- Python 3.12;
- PostgreSQL;
- pgvector;
- SentenceTransformers;
- `intfloat/multilingual-e5-small`;
- FastAPI;
- Pydantic;
- psycopg2 или asyncpg;
- Docker Compose;
- pytest.

LLM-провайдер должен быть подключаемым через отдельный интерфейс. В MVP можно сделать абстракцию `LLMClient`, чтобы в дальнейшем подключить OpenAI-compatible API, GigaChat, YandexGPT, локальную модель или другой провайдер без переписывания бизнес-логики.

---

## 4. Главный архитектурный принцип

Система должна быть не “одним RAG-запросом”, а управляемым пайплайном:

```text
User message
→ Intent Router
→ Source selection
→ SQL / vector / hybrid / conversation memory
→ Context assembly
→ LLM answer generation
→ Structured response
→ Conversation state update
```

Источники истины должны иметь приоритет:

```text
1. SQL-поля recipes
2. JSONB-поля ingredients / steps / properties / nutrition / raw
3. recipe_embeddings / vector search
4. LLM-рассуждение
```

LLM может объяснять, переформулировать и предлагать адаптации, но не должна придумывать:

- калории;
- БЖУ;
- ингредиенты;
- шаги рецепта;
- наличие аллергена в конкретном рецепте;
- ссылку на источник;
- количество порций.

---

## 5. Что нужно сделать сейчас в первую очередь

### 5.1. Исправить нормализацию запроса

Проблема: текущая нормализация удаляет слово `без`, из-за чего запросы с исключениями могут интерпретироваться неверно.

Нужно:

- убрать `без` из стоп-слов;
- убрать или осторожно обрабатывать `нельзя`, `нет`, `не`, если они выражают ограничение;
- добавить отдельный слой извлечения ограничений до нормализации;
- добавить тесты на отрицания.

Примеры обязательных тестов:

```python
def test_normalize_preserves_without_constraint():
    out = normalize_query_for_search("борщ без мяса")
    assert "борщ" in out
    assert "мясо" in out
    # Само слово "без" можно не оставлять в векторном запросе,
    # но ограничение должно быть извлечено отдельным parser'ом.


def test_extract_exclusions_without_meat():
    result = extract_query_constraints("борщ без мяса")
    assert result.exclude_ingredients == ["мясо"]


def test_extract_allergy_milk():
    result = extract_query_constraints("мне нельзя молоко")
    assert result.exclude_ingredients == ["молоко"]
    assert result.restriction_type == "allergy_or_forbidden"


def test_extract_without_sugar():
    result = extract_query_constraints("рецепт без сахара")
    assert result.exclude_ingredients == ["сахар"]
```

Важно: нормализованный текст нужен для поиска, но ограничения должны жить отдельно в structured object.

---

### 5.2. Добавить Intent Router

Создать компонент:

```text
app/orchestrator/intent_router.py
```

Он должен принимать:

```json
{
  "message": "На что в третьем рецепте можно заменить сахар?",
  "conversation_id": "uuid",
  "conversation_state": {
    "last_recipe_results": []
  }
}
```

И возвращать:

```json
{
  "intent": "ingredient_substitution",
  "route": "conversation_recipe_fetch",
  "entities": {
    "recipe_reference": {
      "type": "rank",
      "value": 3
    },
    "target_ingredient": "сахар",
    "include_ingredients": [],
    "exclude_ingredients": []
  },
  "needs_conversation_context": true,
  "needs_recipe_fetch": true,
  "needs_vector_search": false,
  "needs_sql": true,
  "needs_llm": true
}
```

В MVP роутер можно сделать детерминированным на правилах и регулярках. LLM-router можно добавить позже.

---

### 5.3. Перенести CLI-поиск в сервисный слой

Сейчас поиск реализован как CLI-скрипт. Нужно выделить его в сервисы, чтобы API мог использовать эту логику без запуска скриптов.

Создать структуру:

```text
app/
  main.py
  core/
    config.py
    db.py
  schemas/
    chat.py
    recipe.py
    search.py
  services/
    embeddings.py
    recipe_repository.py
    vector_search.py
    keyword_search.py
    hybrid_search.py
    nutrition.py
    substitution.py
    conversation_state.py
  orchestrator/
    intent_router.py
    query_constraints.py
    pipeline.py
  llm/
    client.py
    prompts.py
  api/
    routes_chat.py
    routes_recipes.py
    routes_debug.py
```

CLI-скрипты можно оставить для отладки, но бизнес-логика должна быть в `app/services`.

---

### 5.4. Добавить FastAPI API

Добавить API-сервис:

```text
POST /v1/chat
GET /v1/recipes/{recipe_id}
POST /v1/search/debug
GET /health
```

Добавить Docker Compose service:

```yaml
api:
  build:
    context: .
    dockerfile: docker/Dockerfile.api
  container_name: food_helper_api
  environment:
    DB_HOST: db
    DB_PORT: "5432"
    DB_NAME: food_helper
    DB_USER: food
    DB_PASSWORD: foodpass
  ports:
    - "8000:8000"
  depends_on:
    db:
      condition: service_healthy
```

---

### 5.5. Добавить Conversation State

Для сценариев вида:

```text
На что в третьем рецепте можно заменить сахар?
А во втором сколько калорий?
Покажи первый подробнее.
```

нужно хранить последние найденные рецепты.

На MVP можно хранить состояние в Postgres.

Добавить таблицы:

```sql
CREATE TABLE IF NOT EXISTS chat_sessions (
  id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id BIGSERIAL PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversation_state (
  session_id UUID PRIMARY KEY REFERENCES chat_sessions(id) ON DELETE CASCADE,
  state JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Пример `state`:

```json
{
  "last_recipe_results": [
    {
      "rank": 1,
      "recipe_id": 7,
      "title": "Конвертики из лаваша с творогом и бананом"
    },
    {
      "rank": 2,
      "recipe_id": 3,
      "title": "ПП-чизкейк без выпечки"
    },
    {
      "rank": 3,
      "recipe_id": 9,
      "title": "Салат из свежей капусты как в столовой"
    }
  ],
  "selected_recipe_id": null
}
```

---

## 6. Функциональные требования

### 6.1. Поиск рецептов

Система должна поддерживать запросы:

```text
Какие есть рецепты с борщом без мяса?
Найди рецепты с курицей.
Есть что-нибудь с творогом?
Покажи рецепты без сахара.
Хочу что-то с яблоком.
```

Маршрут:

```text
search_recipes → hybrid_search
```

Алгоритм:

```text
1. Извлечь intent.
2. Извлечь блюдо, ингредиенты, исключения.
3. Выполнить keyword/full-text search.
4. Выполнить vector search.
5. Объединить кандидатов.
6. Применить жесткие фильтры.
7. Отранжировать.
8. Вернуть top-N рецептов.
9. Сохранить выдачу в conversation_state.last_recipe_results.
```

Для MVP `top_n = 5`.

Ответ должен включать:

- название рецепта;
- краткое описание;
- калории на 100 г;
- БЖУ на 100 г;
- время готовки, если есть;
- сложность, если есть;
- аллергенные свойства, если есть;
- ссылку на рецепт;
- объяснение, почему рецепт подходит.

---

### 6.2. Поиск с исключениями

Система должна корректно обрабатывать:

```text
без мяса
без сахара
без молока
без яиц
без глютена
без сельдерея
мне нельзя молоко
у меня аллергия на яйцо
```

Нужно различать:

```text
exclude_ingredients — пользователь не хочет продукт;
allergy_exclusions — пользователь указывает аллергию или медицинское ограничение;
dietary_preference — пользовательская диета или предпочтение.
```

Пример результата парсинга:

```json
{
  "include_ingredients": [],
  "exclude_ingredients": ["мясо"],
  "allergy_exclusions": [],
  "dietary_preference": null
}
```

Если запрос связан с аллергией, ответ должен содержать предупреждение:

```text
Проверьте состав конкретных продуктов и возможные следы аллергенов на упаковке. Я могу отфильтровать рецепты по данным из базы, но не могу гарантировать медицинскую безопасность блюда.
```

---

### 6.3. Подбор рецептов под ситуацию

Система должна поддерживать запросы:

```text
Что можно приготовить на завтрак, чтобы оно было легкое?
Что быстро приготовить на ужин?
Хочу низкокалорийный перекус.
Что приготовить после тренировки?
```

Маршрут:

```text
recommend_recipes → vector_search_with_sql_filters
```

Для слова “легкое” в MVP использовать дефолтную интерпретацию:

```text
легкое = невысокая калорийность + не слишком жирное + простое в приготовлении
```

MVP-фильтры:

```text
calories_kcal <= 150
fat_g <= 8
сложность <= 2 из 5
время на кухне <= 30 минут, если поле доступно
```

Если пользователь явно уточняет:

```text
легкое в приготовлении
```

то приоритет должен быть у сложности и времени, а не у калорий.

Если пользователь говорит:

```text
легкое по калориям
```

то приоритет должен быть у `calories_kcal`.

---

### 6.4. Калории и БЖУ

Система должна поддерживать запросы:

```text
Сколько калорий в яблочном пироге?
Сколько белка в третьем рецепте?
Какие БЖУ у этого блюда?
Это низкокалорийный рецепт?
```

Маршрут:

```text
nutrition_question → sql_nutrition
```

Правила:

- если пользователь ссылается на “третий рецепт”, сначала использовать conversation state;
- если пользователь называет блюдо, сначала найти рецепт;
- если найден один явный рецепт — вернуть нутриенты;
- если найдено несколько похожих рецептов — попросить уточнить или показать список;
- не пересчитывать калории после замены ингредиента в MVP;
- всегда указывать, что значения относятся к 100 г, если это указано в данных.

Формат ответа:

```text
В рецепте “...” указано:
- калории: ... кКал на 100 г;
- белки: ... г;
- жиры: ... г;
- углеводы: ... г.
```

---

### 6.5. Детали рецепта

Система должна поддерживать:

```text
Покажи третий рецепт.
Какие ингредиенты нужны для второго?
Как готовить первый?
Покажи шаги этого рецепта.
```

Маршрут:

```text
recipe_details → conversation_recipe_fetch
```

Алгоритм:

```text
1. Определить recipe_reference.
2. Найти recipe_id в conversation_state.last_recipe_results.
3. Получить полный рецепт из БД.
4. Вернуть ингредиенты, шаги и основные свойства.
5. Обновить selected_recipe_id.
```

Если state пустой, ответить:

```text
Я пока не показывал список рецептов в этом диалоге. Напишите, какой рецепт найти, или задайте поиск.
```

---

### 6.6. Замена ингредиента

Система должна поддерживать:

```text
На что в третьем рецепте можно заменить сахар?
Чем заменить молоко в этом рецепте?
У меня нет банана, что можно вместо него?
Можно этот рецепт без яйца?
```

Маршрут:

```text
ingredient_substitution → recipe_fetch + substitution_service + llm
```

Алгоритм:

```text
1. Определить рецепт:
   - по номеру из предыдущей выдачи;
   - по selected_recipe_id;
   - по названию из запроса;
   - если не найден — дать общий ответ или попросить выбрать рецепт.

2. Получить полный рецепт из БД.

3. Найти целевой ингредиент в ingredients.

4. Определить роль ингредиента:
   - подсластитель;
   - жидкость;
   - жир;
   - белковый продукт;
   - связующий ингредиент;
   - ароматизатор;
   - гарнир;
   - основа блюда.

5. Сформировать варианты замены.

6. Указать влияние:
   - на вкус;
   - на текстуру;
   - на калорийность;
   - на аллергенность;
   - на технологию приготовления.

7. Если замена может сильно изменить рецепт, предупредить.
```

Для MVP можно использовать rule-based словарь замен:

```json
{
  "сахар": [
    {
      "name": "эритрит",
      "ratio": "примерно 1:1, но зависит от производителя",
      "note": "подходит для снижения сахара, может отличаться по сладости"
    },
    {
      "name": "мед",
      "ratio": "примерно 0.7 от количества сахара",
      "note": "добавит вкус и влагу, калорийность сохранится или изменится незначительно"
    },
    {
      "name": "банан",
      "ratio": "по ситуации",
      "note": "подходит не для всех рецептов, меняет текстуру"
    }
  ],
  "молоко": [
    {
      "name": "растительное молоко",
      "ratio": "1:1",
      "note": "выбирать без сахара, если важно снизить калорийность"
    },
    {
      "name": "вода",
      "ratio": "1:1",
      "note": "может сделать вкус менее насыщенным"
    }
  ],
  "яйцо": [
    {
      "name": "льняное яйцо",
      "ratio": "1 ст. л. молотого льна + 3 ст. л. воды вместо 1 яйца",
      "note": "подходит как связующий компонент, но не всегда работает в воздушной выпечке"
    }
  ],
  "сливочное масло": [
    {
      "name": "растительное масло",
      "ratio": "примерно 0.8 от массы сливочного масла",
      "note": "изменит вкус и текстуру"
    }
  ]
}
```

Ответ должен быть помечен как рекомендация:

```text
Это адаптация рецепта, а не исходная инструкция из базы. Калорийность и вкус могут измениться.
```

---

### 6.7. Похожие рецепты

Система должна поддерживать:

```text
Покажи похожие.
Есть что-то похожее, но без курицы?
Найди альтернативу этому рецепту.
```

Маршрут:

```text
similar_recipes → vector_search_by_recipe_embedding + filters
```

Алгоритм:

```text
1. Определить исходный recipe_id.
2. Взять embedding выбранного рецепта.
3. Найти ближайшие рецепты в recipe_embeddings.
4. Исключить сам рецепт.
5. Применить дополнительные фильтры пользователя.
6. Вернуть top-N.
```

---

## 7. Нефункциональные требования

### 7.1. Надежность

Система должна:

- не падать на пустом запросе;
- не падать на слишком длинном запросе;
- возвращать понятную ошибку при недоступности БД;
- возвращать понятную ошибку при недоступности LLM;
- иметь timeout на вызов LLM;
- иметь timeout на запросы к БД;
- логировать route, intent, найденные recipe_id и итоговый ответ.

---

### 7.2. Безопасность

Система не должна:

- выполнять произвольный SQL, сгенерированный LLM;
- передавать пользовательские персональные данные во внешний LLM без необходимости;
- выдавать медицинские гарантии;
- гарантировать безопасность при аллергии;
- выдумывать данные о рецептах.

Все SQL-запросы должны быть параметризованы.

---

### 7.3. Производительность

Для MVP целевые показатели:

```text
POST /v1/chat без LLM: до 1 секунды
POST /v1/chat с LLM: до 10 секунд
Vector search top-20: до 500 мс после прогрева
SQL fetch recipes by ids: до 300 мс
```

Модель эмбеддингов должна загружаться один раз при старте API, а не на каждый запрос.

---

### 7.4. Наблюдаемость

На каждый запрос логировать:

```json
{
  "request_id": "uuid",
  "conversation_id": "uuid",
  "user_message": "...",
  "intent": "search_recipes",
  "route": "hybrid_search",
  "recipe_ids": [1, 2, 3],
  "used_llm": true,
  "latency_ms": 1200,
  "error": null
}
```

---

## 8. API-контракты

### 8.1. `POST /v1/chat`

Запрос:

```json
{
  "conversation_id": "optional-uuid",
  "message": "Что можно приготовить на завтрак, чтобы оно было легкое?",
  "options": {
    "top_k": 5,
    "include_debug": false
  }
}
```

Ответ:

```json
{
  "conversation_id": "uuid",
  "answer": "Я нашел несколько легких вариантов на завтрак...",
  "intent": "recommend_recipes",
  "route": "hybrid_search",
  "recipes": [
    {
      "rank": 1,
      "recipe_id": 7,
      "title": "Конвертики из лаваша с творогом и бананом",
      "description": "...",
      "calories_kcal": 146.27,
      "protein_g": 11.05,
      "fat_g": 3.79,
      "carbs_g": 16.64,
      "servings": 2,
      "cooking_time": "10 минут",
      "difficulty": "1 из 5",
      "allergens": [
        "Белок коровьего молока",
        "Злаки, содержащие глютен",
        "Яйцо"
      ],
      "recipe_url": "https://..."
    }
  ],
  "selected_recipe": null,
  "nutrition": null,
  "substitutions": [],
  "warnings": [],
  "sources": [
    {
      "type": "recipe",
      "recipe_id": 7,
      "title": "Конвертики из лаваша с творогом и бананом",
      "url": "https://..."
    }
  ],
  "debug": null
}
```

---

### 8.2. `GET /v1/recipes/{recipe_id}`

Ответ:

```json
{
  "recipe_id": 7,
  "title": "...",
  "description": "...",
  "ingredients": [
    {
      "name": "Творог 5%",
      "quantity": "250 г",
      "block": "Для блюда"
    }
  ],
  "steps": [
    {
      "position": 1,
      "title": "Шаг 1",
      "text": "..."
    }
  ],
  "nutrition": {
    "calories_kcal": 146.27,
    "protein_g": 11.05,
    "fat_g": 3.79,
    "carbs_g": 16.64,
    "serving_size": "100 г"
  },
  "properties": {
    "cooking_time": "10 минут",
    "difficulty": "1 из 5",
    "allergens": []
  },
  "recipe_url": "https://..."
}
```

---

### 8.3. `POST /v1/search/debug`

Запрос:

```json
{
  "query": "борщ без мяса",
  "top_k": 10,
  "filters": {
    "exclude_ingredients": ["мясо"],
    "max_calories_kcal": null
  }
}
```

Ответ:

```json
{
  "normalized_query": "борщ мясо",
  "constraints": {
    "include_ingredients": [],
    "exclude_ingredients": ["мясо"]
  },
  "vector_results": [],
  "keyword_results": [],
  "final_results": []
}
```

Этот endpoint нужен для отладки качества поиска и не обязан быть публичным.

---

### 8.4. `GET /health`

Ответ:

```json
{
  "status": "ok",
  "db": "ok",
  "embedding_model": "loaded"
}
```

---

## 9. Внутренние модели данных

### 9.1. `IntentDecision`

```python
class IntentDecision(BaseModel):
    intent: Literal[
        "search_recipes",
        "recommend_recipes",
        "nutrition_question",
        "ingredient_substitution",
        "recipe_details",
        "similar_recipes",
        "allergy_or_exclusion",
        "fallback"
    ]
    route: Literal[
        "no_retrieval",
        "sql",
        "vector_search",
        "hybrid_search",
        "conversation_recipe_fetch",
        "substitution"
    ]
    entities: dict
    needs_conversation_context: bool
    needs_recipe_fetch: bool
    needs_vector_search: bool
    needs_sql: bool
    needs_llm: bool
```

---

### 9.2. `QueryConstraints`

```python
class QueryConstraints(BaseModel):
    dish: str | None = None
    include_ingredients: list[str] = []
    exclude_ingredients: list[str] = []
    allergy_exclusions: list[str] = []
    meal_type: str | None = None
    diet_goal: str | None = None
    max_calories_kcal: float | None = None
    min_protein_g: float | None = None
    max_fat_g: float | None = None
    max_cooking_time_minutes: int | None = None
    max_difficulty: int | None = None
```

---

### 9.3. `RecipeCard`

```python
class RecipeCard(BaseModel):
    rank: int
    recipe_id: int
    title: str
    description: str | None
    calories_kcal: float | None
    protein_g: float | None
    fat_g: float | None
    carbs_g: float | None
    servings: int | None
    cooking_time: str | None
    difficulty: str | None
    allergens: list[str]
    recipe_url: str
    similarity: float | None = None
```

---

## 10. Поисковый пайплайн

### 10.1. Vector Search

Использовать текущую таблицу `recipe_embeddings`.

Алгоритм:

```text
1. Подготовить текст запроса.
2. Добавить E5-префикс query:
3. Получить embedding запроса.
4. Выполнить pgvector search.
5. Получить top-K recipe_id.
6. Обогатить recipes-строками из SQL.
```

Важно: модель эмбеддингов должна быть той же, что использовалась для базы.

---

### 10.2. Keyword Search

Добавить keyword/full-text поиск по:

- `title`;
- `description`;
- `ingredients`;
- `raw`.

Для MVP можно использовать:

```sql
websearch_to_tsquery('russian', :query)
```

и GIN-индексы.

---

### 10.3. Hybrid Search

Hybrid search должен объединять:

```text
vector_results + keyword_results + SQL filters
```

Пример формулы ранжирования MVP:

```text
final_score =
  0.65 * vector_score
  + 0.25 * keyword_score
  + 0.10 * rules_score
```

`rules_score` повышает рецепты, которые соответствуют жестким условиям:

- блюдо найдено в title;
- ингредиент найден в ingredients;
- время подходит;
- калории подходят;
- сложность подходит.

Жесткие исключения должны применяться после объединения результатов:

```text
если пользователь сказал “без мяса”, рецепт с курицей/говядиной/свининой не должен попасть в финальную выдачу
```

---

## 11. Доработки БД

### 11.1. Добавить нормализованную таблицу ингредиентов

JSONB достаточно для хранения, но неудобен для надежной фильтрации.

Добавить таблицу:

```sql
CREATE TABLE IF NOT EXISTS recipe_ingredients (
  id BIGSERIAL PRIMARY KEY,
  recipe_id BIGINT NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  canonical_name TEXT NOT NULL,
  quantity_raw TEXT,
  block TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS recipe_ingredients_recipe_id_idx
  ON recipe_ingredients(recipe_id);

CREATE INDEX IF NOT EXISTS recipe_ingredients_canonical_name_idx
  ON recipe_ingredients(canonical_name);

CREATE INDEX IF NOT EXISTS recipe_ingredients_name_trgm_idx
  ON recipe_ingredients USING GIN (name gin_trgm_ops);
```

Также включить extension:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

---

### 11.2. Добавить справочник ингредиентов

Создать файл:

```text
data/ingredient_aliases.json
```

Пример:

```json
{
  "куриная грудка": "курица",
  "куриное филе": "курица",
  "говядина": "мясо",
  "свинина": "мясо",
  "фарш": "мясо",
  "сахар": "сахар",
  "мед": "мед",
  "творог 5%": "творог",
  "греческий йогурт": "йогурт"
}
```

Создать справочник групп:

```text
data/ingredient_groups.json
```

Пример:

```json
{
  "meat": [
    "мясо",
    "курица",
    "куриная грудка",
    "куриное филе",
    "говядина",
    "свинина",
    "фарш",
    "индейка",
    "бекон",
    "ветчина",
    "колбаса"
  ],
  "dairy": [
    "молоко",
    "творог",
    "йогурт",
    "сыр",
    "моцарелла",
    "сливки",
    "сливочное масло"
  ],
  "gluten": [
    "мука",
    "пшеничная мука",
    "лаваш",
    "макароны",
    "лапша",
    "хлеб",
    "сухарики"
  ],
  "sugar": [
    "сахар",
    "мед",
    "сироп"
  ]
}
```

---

### 11.3. Изменить primary key в `recipe_embeddings`

Сейчас `recipe_embeddings` имеет primary key только по `recipe_id`. Для MVP это допустимо, но лучше подготовить схему к нескольким моделям эмбеддингов.

Рекомендуемая схема:

```sql
ALTER TABLE recipe_embeddings DROP CONSTRAINT IF EXISTS recipe_embeddings_pkey;

ALTER TABLE recipe_embeddings
ADD PRIMARY KEY (recipe_id, model);
```

После этого можно хранить несколько embeddings для одного рецепта под разные модели.

---

### 11.4. Добавить индексы для фильтров

```sql
CREATE INDEX IF NOT EXISTS recipes_calories_idx ON recipes(calories_kcal);
CREATE INDEX IF NOT EXISTS recipes_protein_idx ON recipes(protein_g);
CREATE INDEX IF NOT EXISTS recipes_fat_idx ON recipes(fat_g);
CREATE INDEX IF NOT EXISTS recipes_carbs_idx ON recipes(carbs_g);
CREATE INDEX IF NOT EXISTS recipes_category_idx ON recipes(category);
CREATE INDEX IF NOT EXISTS recipes_subcategory_idx ON recipes(subcategory);
CREATE INDEX IF NOT EXISTS recipes_properties_gin_idx ON recipes USING GIN(properties);
CREATE INDEX IF NOT EXISTS recipes_ingredients_gin_idx ON recipes USING GIN(ingredients);
```

---

## 12. LLM-слой

### 12.1. Требования к LLM

LLM используется только после того, как система получила данные из БД/поиска.

LLM должна:

- формировать понятный ответ;
- объяснять, почему рецепты подходят;
- предлагать замены ингредиентов;
- учитывать контекст диалога;
- не выдумывать отсутствующие данные;
- явно говорить, если данных недостаточно.

---

### 12.2. System prompt

```text
Ты — кулинарный ассистент по базе рецептов.

Правила:
1. Отвечай на основе переданного контекста рецептов.
2. Не выдумывай калории, БЖУ, ингредиенты, шаги и ссылки.
3. Если данных недостаточно, скажи об этом.
4. Если предлагаешь замену ингредиента, явно пометь это как адаптацию рецепта.
5. При аллергиях предупреждай, что нужно проверять состав продуктов и следы аллергенов.
6. Не давай медицинских гарантий.
7. Если пользователь ссылается на “первый”, “второй”, “третий рецепт”, используй переданный conversation state.
8. Отвечай кратко, но достаточно конкретно.
```

---

### 12.3. Prompt для ответа с рецептами

```text
Пользовательский вопрос:
{user_message}

Найденные рецепты:
{recipes_context}

Ограничения пользователя:
{constraints}

Сформируй ответ:
- перечисли подходящие рецепты;
- укажи ключевые параметры: калории, время, сложность, аллергены;
- объясни, почему они подходят;
- не добавляй рецепты, которых нет в контексте.
```

---

### 12.4. Prompt для замены ингредиента

```text
Пользовательский вопрос:
{user_message}

Исходный рецепт:
{recipe_context}

Ингредиент для замены:
{target_ingredient}

Ограничения пользователя:
{constraints}

Задача:
Предложи 2-4 варианта замены ингредиента.
Для каждого варианта укажи:
- чем заменить;
- примерную пропорцию;
- как изменится вкус или текстура;
- изменится ли калорийность;
- есть ли риск по аллергенам.

Важно:
Это адаптация рецепта, а не исходная инструкция из базы.
Не меняй шаги рецепта радикально, если пользователь не просил.
```

---

## 13. Conversation RAG

### 13.1. Зачем нужен

Сценарий:

```text
User: Что можно приготовить на завтрак, чтобы было легкое?
Assistant: 1. ... 2. ... 3. ...

User: На что в третьем рецепте можно заменить сахар?
```

Второй вопрос невозможно корректно обработать без памяти предыдущей выдачи.

---

### 13.2. Правила resolution

Если пользователь говорит:

```text
первый рецепт
первом
1
```

то система берет `last_recipe_results[0]`.

Если пользователь говорит:

```text
третий рецепт
3 рецепт
в третьем
```

то система берет `last_recipe_results[2]`.

Если пользователь говорит:

```text
этот рецепт
текущий рецепт
здесь
```

то система берет `selected_recipe_id`.

Если `selected_recipe_id` отсутствует, использовать последний recipe из последнего ответа, если он был один.

Если нельзя определить рецепт — задать уточнение.

---

## 14. Этапы разработки

### Этап 0. Исправление текущего поискового ядра

Задачи:

- исправить обработку отрицаний;
- добавить `extract_query_constraints`;
- добавить тесты на “без мяса”, “без сахара”, “мне нельзя молоко”;
- вынести часть CLI-логики в сервисы;
- убедиться, что pgvector-поиск работает из импортируемой функции.

Результат:

- `pytest` проходит;
- запрос “борщ без мяса” не теряет ограничение;
- в коде есть structured constraints.

Критерии приемки:

```text
- [ ] normalize_query_for_search не ломает кириллицу.
- [ ] extract_query_constraints извлекает exclude_ingredients.
- [ ] “без мяса” не превращается в “мясо” как положительное условие.
- [ ] Добавлены тесты на отрицания.
```

---

### Этап 1. API-каркас

Задачи:

- добавить FastAPI;
- добавить `app/main.py`;
- добавить `/health`;
- добавить `/v1/chat`;
- добавить `/v1/search/debug`;
- добавить Dockerfile API;
- добавить API service в docker-compose;
- добавить Pydantic-схемы.

Результат:

```text
docker compose up api
```

поднимает API.

Критерии приемки:

```text
- [ ] GET /health возвращает 200.
- [ ] POST /v1/chat принимает сообщение.
- [ ] Пустой запрос возвращает 400.
- [ ] Слишком длинный запрос возвращает 400.
- [ ] Ошибка БД возвращает понятный ответ.
```

---

### Этап 2. Recipe Repository

Задачи:

- реализовать получение рецепта по id;
- реализовать получение рецептов по списку id;
- реализовать поиск по title/description;
- реализовать получение nutrition;
- реализовать парсинг `properties`;
- реализовать преобразование строки БД в `RecipeCard`.

Критерии приемки:

```text
- [ ] get_recipe_by_id возвращает ingredients, steps, nutrition.
- [ ] get_recipes_by_ids сохраняет порядок ids.
- [ ] nutrition берется из SQL-полей, а не из LLM.
- [ ] allergens извлекаются из properties.
```

---

### Этап 3. Hybrid Search

Задачи:

- реализовать vector search как сервис;
- реализовать keyword search как сервис;
- реализовать объединение результатов;
- реализовать фильтрацию по exclude ingredients;
- реализовать фильтрацию по калориям;
- реализовать фильтрацию по времени/сложности, если данные доступны.

Критерии приемки:

```text
- [ ] “рецепты с курицей” возвращают рецепты с курицей.
- [ ] “без мяса” не возвращает курицу/говядину/свинину.
- [ ] “низкокалорийное” учитывает calories_kcal.
- [ ] “быстрое” учитывает время на кухне или “Будет готово через”.
- [ ] search/debug показывает vector_results, keyword_results, final_results.
```

---

### Этап 4. Intent Router

Задачи:

- реализовать rule-based классификацию intent;
- реализовать извлечение recipe reference;
- реализовать извлечение target ingredient;
- реализовать извлечение nutrient;
- реализовать fallback.

Критерии приемки:

```text
- [ ] “Какие есть рецепты с борщом без мяса” → search_recipes.
- [ ] “На что в третьем рецепте можно заменить сахар” → ingredient_substitution.
- [ ] “Что можно приготовить на завтрак, чтобы оно было легкое” → recommend_recipes.
- [ ] “Сколько калорий в яблочном пироге” → nutrition_question.
- [ ] “Покажи второй рецепт” → recipe_details.
```

---

### Этап 5. Conversation State

Задачи:

- добавить таблицы chat_sessions, chat_messages, conversation_state;
- сохранять user/assistant messages;
- сохранять last_recipe_results;
- сохранять selected_recipe_id;
- реализовать resolution “первый / второй / третий”.

Критерии приемки:

```text
- [ ] После ответа со списком рецептов state содержит last_recipe_results.
- [ ] Запрос “покажи третий” достает правильный recipe_id.
- [ ] Запрос “а в первом сколько калорий?” работает.
- [ ] При отсутствии state система задает уточнение.
```

---

### Этап 6. Nutrition Service

Задачи:

- отвечать на вопросы о calories_kcal;
- отвечать на вопросы о protein_g/fat_g/carbs_g;
- поддерживать recipe reference;
- поддерживать поиск рецепта по названию;
- возвращать уточнение при нескольких вариантах.

Критерии приемки:

```text
- [ ] “Сколько калорий в третьем рецепте?” работает через conversation state.
- [ ] “Сколько калорий в яблочном пироге?” ищет рецепт и возвращает калории.
- [ ] Если найдено несколько рецептов, система предлагает выбрать.
- [ ] Ответ указывает “на 100 г”, если это следует из данных.
```

---

### Этап 7. Substitution Service

Задачи:

- добавить словарь замен;
- определить роль ингредиента;
- найти ингредиент в рецепте;
- сформировать prompt для LLM;
- вернуть варианты замены;
- добавить предупреждения.

Критерии приемки:

```text
- [ ] “Чем заменить сахар в третьем рецепте?” работает.
- [ ] Если сахара нет в рецепте, система говорит об этом.
- [ ] При аллергии ответ содержит warning.
- [ ] Ответ не утверждает, что калорийность осталась прежней.
```

---

### Этап 8. LLM Answer Generator

Задачи:

- реализовать `LLMClient`;
- реализовать prompts;
- реализовать сборку контекста;
- реализовать fallback без LLM;
- добавить timeout;
- добавить логирование.

Критерии приемки:

```text
- [ ] Ответ с рецептами использует только переданные рецепты.
- [ ] При пустом поиске система не выдумывает рецепты.
- [ ] При ошибке LLM API возвращается fallback.
- [ ] Все источники доступны в response.sources.
```

---

### Этап 9. Бизнес-функциональные тесты

Создать файл:

```text
tests/evals/test_rag_scenarios.py
```

Тестовые сценарии:

```text
1. Какие есть рецепты с борщом без мяса?
2. На что в третьем рецепте можно заменить сахар?
3. Что можно приготовить на завтрак, чтобы оно было легкое?
4. Сколько калорий в яблочном пироге?
5. Покажи второй рецепт.
6. Сколько белка в первом?
7. Мне нельзя молоко, что подойдет?
8. Есть что-то похожее, но без курицы?
```

Критерии приемки:

```text
- [ ] intent выбран правильно.
- [ ] route выбран правильно.
- [ ] SQL/Vector используются там, где нужно.
- [ ] Не используются там, где не нужно.
- [ ] В ответе нет выдуманных рецептов.
- [ ] “третий рецепт” корректно разрешается через state.
```

---

## 15. Fallback-политики

### 15.1. Если рецепты не найдены

Ответ:

```text
Я не нашел подходящих рецептов в базе. Могу предложить изменить условия поиска: убрать часть ограничений, выбрать другой ингредиент или искать похожие блюда.
```

Не нужно генерировать новый рецепт, если пользователь явно ищет по базе.

---

### 15.2. Если недостаточно контекста

Пример:

```text
На что в третьем рецепте заменить сахар?
```

но предыдущей выдачи нет.

Ответ:

```text
Я пока не вижу списка рецептов в этом диалоге, поэтому не могу понять, какой рецепт третий. Напишите название рецепта или сначала попросите найти рецепты.
```

---

### 15.3. Если LLM недоступна

Для поиска рецептов можно вернуть шаблонный ответ без LLM:

```text
Я нашел подходящие рецепты:
1. ...
2. ...
3. ...

LLM-объяснение временно недоступно, но данные рецептов получены из базы.
```

---

## 16. Что не входит в MVP

В MVP не входит:

- точный пересчет калорий после замены ингредиента;
- генерация полностью нового рецепта без опоры на БД;
- персональные медицинские рекомендации;
- учет хронических заболеваний;
- автоматический meal plan на неделю;
- покупка продуктов;
- интеграция с внешними сайтами в режиме онлайн;
- пользовательские профили питания;
- авторизация;
- фронтенд, если сначала делается только API.

---

## 17. Definition of Done для MVP

MVP считается готовым, если:

```text
- [ ] API запускается через Docker Compose.
- [ ] БД поднимается через Docker Compose.
- [ ] Рецепты загружаются в БД.
- [ ] Эмбеддинги записываются в recipe_embeddings.
- [ ] /health работает.
- [ ] /v1/chat работает.
- [ ] Поиск рецептов работает через hybrid search.
- [ ] Запросы с “без X” корректно фильтруются.
- [ ] Калории и БЖУ берутся из БД.
- [ ] “третий рецепт” работает через conversation state.
- [ ] Замена ингредиента работает для выбранного рецепта.
- [ ] При аллергии есть предупреждение.
- [ ] При пустой выдаче система не выдумывает рецепты.
- [ ] Есть тесты для основных сценариев.
- [ ] Есть debug endpoint для диагностики поиска.
```

---

## 18. Приоритет реализации

Сначала делать в таком порядке:

```text
1. Исправить отрицания и constraints.
2. Вынести поиск из CLI в сервисы.
3. Добавить FastAPI.
4. Добавить /v1/search/debug.
5. Добавить /v1/chat без LLM, только structured response.
6. Добавить conversation state.
7. Добавить intent router.
8. Добавить nutrition service.
9. Добавить substitution service.
10. Добавить LLM answer generator.
11. Добавить бизнес-функциональные тесты.
12. Добавить Docker API service.
```

Почему именно так:

```text
Сначала нужно сделать надежную маршрутизацию и получение данных.
LLM подключается после этого.
Иначе модель будет маскировать ошибки поиска красивым текстом.
```

---

## 19. Самый первый конкретный task для разработки

### Task: `query_constraints`

Создать файл:

```text
app/orchestrator/query_constraints.py
```

Реализовать:

```python
def extract_query_constraints(message: str) -> QueryConstraints:
    ...
```

Минимально должно извлекаться:

```text
без мяса → exclude_ingredients=["мясо"]
без сахара → exclude_ingredients=["сахар"]
без молока → exclude_ingredients=["молоко"]
мне нельзя молоко → exclude_ingredients=["молоко"], restriction_type="forbidden"
аллергия на яйцо → allergy_exclusions=["яйцо"]
низкокалорийное → max_calories_kcal=150
легкое → diet_goal="light"
на завтрак → meal_type="breakfast"
```

Добавить тесты:

```text
tests/test_query_constraints.py
```

Критерии приемки:

```text
- [ ] pytest проходит.
- [ ] “без мяса” корректно извлекается.
- [ ] “без сахара” корректно извлекается.
- [ ] “аллергия на яйцо” корректно извлекается.
- [ ] “легкое на завтрак” корректно извлекается.
```

---

## 20. Второй task после constraints

### Task: `FastAPI skeleton`

Создать:

```text
app/main.py
app/api/routes_chat.py
app/api/routes_debug.py
app/core/config.py
app/core/db.py
app/schemas/chat.py
docker/Dockerfile.api
```

Минимальная реализация:

```text
GET /health
POST /v1/chat
POST /v1/search/debug
```

На этом этапе `/v1/chat` может возвращать:

```json
{
  "answer": "API работает, intent распознан",
  "intent": "...",
  "route": "...",
  "debug": {
    "constraints": {}
  }
}
```

LLM пока не подключать.

---

## 21. Критически важное правило разработки

Не начинать с LangChain/агента.

Сначала нужно сделать:

```text
intent router
+ structured constraints
+ SQL/vector services
+ conversation state
+ deterministic API response
```

И только после этого добавлять LLM.

Причина:

```text
Если сначала подключить LLM, она будет красиво отвечать даже тогда, когда поиск, фильтры и state работают неверно.
```
