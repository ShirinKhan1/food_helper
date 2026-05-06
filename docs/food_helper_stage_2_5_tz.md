<!--
Фрагмент для вставки в docs/food_helper_rag_tz.md.
Рекомендуемое место: после раздела «4. Главный архитектурный принцип» или в конец файла как следующий этап разработки.
Назначение: зафиксировать ближайшее ТЗ на стабилизацию текущего conversational MVP перед подключением LLM-оркестрации.
-->

## Этап 2.5 — Conversational MVP Hardening

### 1. Назначение этапа

Цель этапа — довести текущий deterministic-orchestration MVP до стабильного состояния, чтобы поверх него можно было безопасно добавлять LLM-assisted и agentic-сценарии.

На этом этапе не нужно переписывать систему под полноценного LLM-агента. Основной принцип остается прежним:

```text
Код управляет маршрутом и бизнес-правилами.
LLM может быть подключена позже как помощник для отдельных задач.
```

Этап считается завершенным, когда Food Helper стабильно обрабатывает многошаговые диалоговые сценарии:

```text
поиск → выбор рецепта → детали → КБЖУ → замена ингредиента → похожие рецепты
```

и при этом не теряет ограничения пользователя вроде `без молока`, `без сахара`, `до 300 ккал`, `аллергия на яйцо`.

---

### 2. Что уже считается реализованным и не должно делаться заново

В текущей версии проекта уже есть базовая реализация следующих компонентов:

- FastAPI-приложение;
- endpoint `POST /v1/chat`;
- endpoint `POST /v1/search/debug`;
- endpoint `GET /v1/recipes/{recipe_id}`;
- endpoint `GET /health`;
- `ChatPipeline` как основной orchestrator;
- `IntentRouter` на правилах;
- `extract_query_constraints` для базовых ограничений;
- гибридный поиск: vector + keyword + rule score;
- фильтрация по исключенным ингредиентам, аллергиям, калориям, жирам, белку, времени и сложности;
- `ConversationStateService` с `last_recipe_results` и `selected_recipe_id`;
- rule-based `SubstitutionService`;
- базовые API/unit/integration tests.

На этом этапе нельзя снова реализовывать “с нуля” API, роутер, сервисный слой или таблицы состояния диалога. Нужно усиливать и расширять текущую архитектуру.

---

### 3. Scope этапа

В scope входят:

1. Исправление и расширение сценария замены ингредиентов.
2. Добавление general substitution без привязки к конкретному рецепту.
3. Усиление parsing/constraints для пользовательских ограничений.
4. E2E-тесты на многошаговый chat-flow.
5. Проверки, что запрещенные ингредиенты реально не попадают в финальную выдачу.
6. Улучшение fallback-поведения при неоднозначности.
7. Подготовка безопасной границы для будущего LLM-слоя.
8. Актуализация документации и Postman/manual smoke-сценариев.

В scope не входят:

- полноценный LLM-agent, который сам выбирает любые инструменты;
- генерация новых рецептов “с нуля”;
- медицинские рекомендации;
- персональные диеты по диагнозам;
- расчет новой калорийности после замены ингредиентов;
- фронтенд;
- авторизация пользователей;
- production monitoring уровня Sentry/Prometheus, если его еще нет в проекте.

---

### 4. Главный архитектурный принцип этапа

Система должна остаться deterministic-first:

```text
User message
→ rule-based intent router
→ structured constraints
→ deterministic service route
→ SQL/vector/keyword/substitution service
→ structured response
→ optional human-readable answer
→ conversation state update
```

LLM на этом этапе не является обязательной. Если LLM будет добавлена, она должна использоваться только для безопасных задач:

- переформулировка ответа;
- query rewrite;
- генерация уточняющего вопроса;
- объяснение, почему рецепты подходят;
- выбор лучшей формулировки из уже полученных structured facts.

LLM не должна:

- выполнять произвольный SQL;
- менять hard filters;
- игнорировать allergy/exclusion constraints;
- придумывать калории, БЖУ, ингредиенты, шаги или ссылки;
- принимать финальное решение о медицинской безопасности блюда.

---

### 5. Поддерживаемые сценарии после этапа

После реализации этапа система должна стабильно поддерживать следующие сценарии.

#### 5.1. Поиск рецептов

Примеры:

```text
Найди рецепты с курицей.
Какие есть рецепты борща?
Есть что-нибудь с творогом?
Покажи блюда с яблоком.
```

Ожидаемо:

```text
intent = search_recipes
route = hybrid_search
recipes не пустой, если в базе есть подходящие рецепты
conversation_state.last_recipe_results обновлен
selected_recipe_id сброшен в null
```

#### 5.2. Поиск с ограничениями

Примеры:

```text
борщ без мяса
завтрак без молока до 300 ккал
ужин с курицей без грибов
мне нельзя яйцо
у меня аллергия на молоко
```

Ожидаемо:

```text
exclude_ingredients / allergy_exclusions заполнены
hard filters применены к final_results
при allergy_exclusions добавлен warning
```

#### 5.3. Рекомендации под ситуацию

Примеры:

```text
Что можно приготовить на завтрак, чтобы было легкое?
Что быстро приготовить на ужин?
Хочу низкокалорийный перекус.
Что приготовить после тренировки?
```

Ожидаемо:

```text
intent = recommend_recipes
route = hybrid_search
meal_type / diet_goal / numeric constraints заполнены, если они извлекаются из текста
```

#### 5.4. Детали рецепта через диалоговый контекст

Примеры:

```text
Покажи первый рецепт.
Расскажи подробнее про второй.
Какие ингредиенты нужны для третьего?
Как готовить этот рецепт?
```

Ожидаемо:

```text
recipe_reference распознан
recipe_id найден через conversation_state.last_recipe_results или selected_recipe_id
selected_recipe заполнен
conversation_state.selected_recipe_id обновлен
```

#### 5.5. КБЖУ через выбранный рецепт

Примеры:

```text
Сколько в нем белка?
Какие БЖУ у этого рецепта?
Сколько калорий во втором?
Сколько жиров в яблочном пироге?
```

Ожидаемо:

```text
intent = nutrition_question
nutrition заполнен, если рецепт найден
если рецепт неоднозначен — возвращается список кандидатов для уточнения
значения не выдумываются и берутся только из данных рецепта
```

#### 5.6. Замена ингредиента в конкретном рецепте

Примеры:

```text
Чем заменить сахар в третьем рецепте?
Можно этот рецепт без молока?
У меня нет банана, что можно вместо него?
```

Ожидаемо:

```text
intent = ingredient_substitution
рецепт найден через rank / selected_recipe_id / title query
target_ingredient распознан
substitutions заполнены, если есть rule-based варианты
answer содержит предупреждение, что это адаптация рецепта
```

#### 5.7. Общая замена ингредиента без рецепта

Примеры:

```text
Чем заменить сливочное масло в выпечке?
Чем заменить сахар?
Что можно использовать вместо молока?
Альтернатива яйцу в выпечке?
```

Ожидаемо:

```text
intent = general_substitution
route = substitution_catalog
selected_recipe = null
substitutions заполнены из rule-based словаря, если варианты есть
answer не требует выбрать конкретный рецепт
answer содержит предупреждение, что это общая рекомендация, а не инструкция из конкретного рецепта
```

#### 5.8. Похожие рецепты

Примеры:

```text
Покажи похожие.
Есть что-то похожее, но без курицы?
Найди альтернативу этому рецепту.
Похожие на второй, но без молока.
```

Ожидаемо:

```text
intent = similar_recipes
base recipe найден через selected_recipe_id или rank reference
исходный рецепт исключен из результатов
дополнительные constraints применены к final_results
conversation_state.last_recipe_results обновлен новой выдачей
```

---

### 6. Функциональные требования к реализации

#### FR-1. Добавить `general_substitution`

Проблема: текущий сценарий замены ингредиента привязан к конкретному рецепту. Запросы вида `Чем заменить сливочное масло в выпечке?` должны работать без предварительного выбора рецепта.

Нужно изменить:

```text
app/schemas/chat.py
app/orchestrator/intent_router.py
app/orchestrator/pipeline.py
app/services/substitution.py
app/services/ingredient_catalog.py, если потребуется
```

Минимальный контракт:

```python
IntentDecision.intent includes "general_substitution"
IntentDecision.route includes "substitution_catalog"
```

Логика:

```text
Если запрос содержит замену ингредиента, но нет явной ссылки на рецепт:
  → general_substitution

Если запрос содержит замену ингредиента и есть recipe_reference / selected_recipe_id / recipe_title_query:
  → ingredient_substitution
```

Так как `IntentRouter` сейчас не знает `selected_recipe_id`, допустим один из двух подходов:

```text
Вариант A:
IntentRouter возвращает ingredient_substitution,
а ChatPipeline после неуспешного _resolve_recipe переключается в general_substitution,
если target_ingredient найден.

Вариант B:
IntentRouter возвращает general_substitution для общих формулировок,
а ChatPipeline оставляет ingredient_substitution для rank/title/selected-reference формулировок.
```

Предпочтительный вариант — A, потому что он лучше использует текущий state: если в диалоге уже выбран рецепт, запрос `чем заменить сахар?` должен относиться к выбранному рецепту.

Acceptance criteria:

```text
POST /v1/chat: "Чем заменить сливочное масло в выпечке?"
→ 200
→ intent = general_substitution или ingredient_substitution с route = substitution_catalog
→ selected_recipe = null
→ substitutions не пустой, если правило есть в data/substitution_rules.json
→ answer не просит выбрать рецепт, если target_ingredient распознан
```

```text
POST /v1/chat: "Чем заменить сахар в третьем рецепте?" после поиска
→ 200
→ intent = ingredient_substitution
→ selected_recipe заполнен
→ substitutions заполнены, если правило есть
```

---

#### FR-2. Расширить `SubstitutionService`

Добавить метод для общих замен:

```python
class SubstitutionService:
    def suggest(self, recipe: RecipeDetail, target_ingredient: str) -> SubstitutionResult:
        ...

    def suggest_general(self, target_ingredient: str, *, context: str | None = None) -> SubstitutionResult:
        ...
```

Для `suggest_general`:

```text
found_in_recipe = false или отдельное поле not_applicable
options берутся из IngredientCatalog.substitutions
warnings включают предупреждение об общей рекомендации
```

Пример warning:

```text
Это общая рекомендация по замене ингредиента, а не инструкция из конкретного рецепта. Вкус, текстура и калорийность могут измениться.
```

Если вариантов нет:

```text
answer = "Для ингредиента '...' пока нет готовых замен в rule-based словаре."
warnings содержит "Для этого ингредиента пока нет готового rule-based словаря замен."
```

---

#### FR-3. Усилить extraction ограничений

Текущий `QueryConstraints` уже содержит поля:

```text
dish
include_ingredients
exclude_ingredients
allergy_exclusions
dietary_preference
restriction_type
meal_type
diet_goal
max_calories_kcal
min_protein_g
max_fat_g
max_cooking_time_minutes
max_difficulty
```

Нужно расширить `extract_query_constraints`, чтобы он лучше извлекал `include_ingredients`.

Добавить поддержку паттернов:

```text
с курицей
с творогом
с яблоком
из курицы
из творога
на основе банана
хочу что-то с рисом
```

Ограничение: parser не должен превращать служебные слова в ингредиенты.

Примеры, которые не должны становиться ingredient:

```text
с учетом
с низкой калорийностью
с быстрым приготовлением
с похожим вкусом
```

Acceptance criteria:

```python
def test_extract_include_chicken():
    result = extract_query_constraints("ужин с курицей без грибов")
    assert "курица" in result.include_ingredients
    assert "гриб" in result.exclude_ingredients


def test_extract_include_cottage_cheese():
    result = extract_query_constraints("что приготовить с творогом")
    assert "творог" in result.include_ingredients


def test_do_not_extract_service_phrase_as_ingredient():
    result = extract_query_constraints("найди рецепт с учетом аллергии на молоко")
    assert "учет" not in result.include_ingredients
```

---

#### FR-4. Гарантировать hard filtering запрещенных ингредиентов

`HybridSearchService._passes_filters` должен оставаться источником истины для исключений.

Нужно добавить тесты, которые проверяют не только extracted constraints, но и итоговый `final_results`.

Минимальные тесты:

```python
def test_hybrid_search_excludes_forbidden_ingredient_from_final_results():
    ...


def test_hybrid_search_excludes_allergy_ingredient_from_final_results():
    ...


def test_similar_recipes_respect_exclusions():
    ...
```

Acceptance criteria:

```text
Если constraints.exclude_ingredients содержит "молоко",
то final_results не содержит рецепты, где IngredientCatalog.matches_any(row, ["молоко"]) == True.
```

```text
Если constraints.allergy_exclusions содержит "яйцо",
то final_results не содержит рецепты, где IngredientCatalog.matches_any(row, ["яйцо"]) == True,
а response.warnings содержит allergy warning.
```

---

#### FR-5. Добавить E2E-тесты chat-flow

Создать файл:

```text
tests/test_chat_pipeline_flows.py
```

Покрыть многошаговые сценарии через `ChatPipeline` или через `TestClient`.

Минимальный сценарий 1:

```text
1. User: "Посоветуй легкий завтрак без молока до 300 ккал"
   Expected:
   - intent in {recommend_recipes, allergy_or_exclusion, search_recipes}
   - recipes не пустой в fake setup
   - constraints.exclude_ingredients содержит "молоко"

2. User: "Покажи первый рецепт" с тем же conversation_id
   Expected:
   - intent = recipe_details
   - selected_recipe заполнен
   - selected_recipe.recipe_id == recipes[0].recipe_id

3. User: "Сколько в нем белка?" с тем же conversation_id
   Expected:
   - intent = nutrition_question
   - nutrition.protein_g заполнен
   - selected_recipe не потерян

4. User: "Покажи похожие, но без яйца" с тем же conversation_id
   Expected:
   - intent = similar_recipes
   - constraints.exclude_ingredients содержит "яйцо"
   - final recipes не содержат яйцо
```

Минимальный сценарий 2:

```text
1. User: "Найди десерты без сахара"
2. User: "Чем заменить сахар в первом?"

Expected:
- second response intent = ingredient_substitution
- selected_recipe заполнен
- substitutions не пустой, если правило для сахара есть
- warnings содержит предупреждение об адаптации рецепта
```

Минимальный сценарий 3:

```text
User: "Чем заменить сливочное масло в выпечке?"

Expected:
- response не требует сначала найти рецепт
- substitutions возвращаются из словаря
- selected_recipe = null
```

---

#### FR-6. Усилить fallback при неоднозначности

Если `_resolve_recipe` находит несколько кандидатов по названию, ответ должен не падать и не выбирать случайный рецепт.

Требование:

```text
Если candidates > 1:
  → вернуть список кандидатов
  → обновить conversation_state.last_recipe_results
  → попросить пользователя выбрать номер
```

Формат ответа:

```text
Я нашел несколько похожих рецептов. Уточните, какой именно нужен:
1. ...
2. ...
3. ...
```

Acceptance criteria:

```python
def test_recipe_title_ambiguity_returns_candidates():
    ...
```

---

#### FR-7. Не терять `selected_recipe_id`

Правила обновления conversation state:

```text
search_recipes / recommend_recipes / allergy_or_exclusion:
  last_recipe_results = ids из новой выдачи
  selected_recipe_id = null

recipe_details:
  selected_recipe_id = выбранный recipe_id

nutrition_question:
  selected_recipe_id = recipe_id, по которому отвечали

ingredient_substitution:
  selected_recipe_id = recipe_id, по которому отвечали

similar_recipes:
  last_recipe_results = ids новой похожей выдачи
  selected_recipe_id лучше оставить равным base_recipe_id или явно задокументировать сброс
```

Рекомендация для MVP:

```text
similar_recipes не должен сбрасывать selected_recipe_id,
чтобы пользователь мог сказать: "а сколько в нем белка?" про исходный рецепт.
```

Если будет принято другое поведение, его нужно зафиксировать в тестах.

---

#### FR-8. Добавить eval-набор пользовательских запросов

Создать файл:

```text
tests/evals/test_conversation_eval_set.py
```

или JSONL-файл:

```text
tests/evals/conversation_cases.jsonl
```

Минимальный формат case:

```json
{
  "name": "breakfast_without_milk",
  "messages": [
    "Посоветуй легкий завтрак без молока до 300 ккал"
  ],
  "expected": {
    "intent": "recommend_recipes",
    "constraints": {
      "exclude_ingredients_contains": ["молоко"],
      "max_calories_kcal_lte": 300
    },
    "no_ingredients_in_results": ["молоко"]
  }
}
```

Минимум на этапе:

```text
30 eval cases
```

Категории:

```text
5 поисков без ограничений
5 поисков с include ingredients
5 поисков с exclude ingredients
5 allergy/forbidden cases
5 follow-up cases через rank/selected_recipe
5 substitution/similar/nutrition cases
```

DoD по eval:

```text
pytest по eval-набору проходит
или не менее 90% cases проходят, а failures описаны в отдельном known_issues.md
```

---

### 7. API-контракты, которые должны сохраниться

#### 7.1. `POST /v1/chat`

Запрос:

```json
{
  "conversation_id": "optional-uuid",
  "message": "Чем заменить сливочное масло в выпечке?",
  "options": {
    "top_k": 5,
    "include_debug": true
  }
}
```

Ответ должен оставаться совместимым с текущим `ChatResponse`:

```json
{
  "conversation_id": "uuid",
  "answer": "...",
  "intent": "general_substitution",
  "route": "substitution_catalog",
  "recipes": [],
  "selected_recipe": null,
  "nutrition": null,
  "substitutions": [
    {
      "name": "растительное масло",
      "ratio": "примерно 0.8 от массы сливочного масла",
      "note": "изменит вкус и текстуру"
    }
  ],
  "warnings": [
    "Это общая рекомендация по замене ингредиента, а не инструкция из конкретного рецепта. Вкус, текстура и калорийность могут измениться."
  ],
  "sources": [],
  "debug": {
    "constraints": {},
    "intent_decision": {}
  }
}
```

Допустимо сохранить `intent = ingredient_substitution`, если в `route` или `debug.intent_decision.entities` явно видно, что это general substitution. Но предпочтительно добавить отдельный intent.

---

#### 7.2. `POST /v1/search/debug`

Endpoint должен продолжать возвращать:

```text
normalized_query
constraints
vector_results
keyword_results
final_results
```

Для отладки фильтров желательно добавить в `debug` или в отдельное поле сведения:

```text
filtered_out_count
filter_reasons
```

Это optional. На этапе 2.5 достаточно тестов, которые проверяют hard filtering.

---

### 8. Тестовые требования

После реализации должны проходить:

```bash
pytest -q
```

Обязательные новые или обновленные тесты:

```text
tests/test_intent_router.py
tests/test_query_constraints.py
tests/test_substitution_service.py
tests/test_chat_pipeline_flows.py
tests/test_hybrid_search_filters.py
tests/evals/test_conversation_eval_set.py или эквивалент
```

Минимальные test cases:

```python
def test_general_substitution_without_recipe():
    ...


def test_substitution_with_rank_reference_still_uses_recipe():
    ...


def test_chat_flow_search_then_details_then_nutrition():
    ...


def test_chat_flow_search_then_similar_with_exclusion():
    ...


def test_constraints_include_and_exclude_ingredients():
    ...


def test_allergy_warning_is_returned():
    ...


def test_no_excluded_ingredient_in_final_results():
    ...
```

Integration tests that require database may remain marked as:

```python
@pytest.mark.integration
```

и должны skip-аться, если DSN не задан.

---

### 9. Manual smoke checklist

Перед завершением этапа вручную проверить через Postman или curl.

#### 9.1. Health

```http
GET /health
```

Ожидаемо:

```text
200
status = ok
```

#### 9.2. Поиск с ограничениями

```json
{
  "message": "Посоветуй легкий завтрак без молока до 300 ккал",
  "options": {
    "top_k": 5,
    "include_debug": true
  }
}
```

Ожидаемо:

```text
200
recipes не пустой, если база содержит подходящие рецепты
constraints.exclude_ingredients содержит молоко
final recipes не содержат молоко
```

#### 9.3. Детали по rank-reference

```json
{
  "conversation_id": "{{conversation_id}}",
  "message": "Покажи первый рецепт",
  "options": {
    "include_debug": true
  }
}
```

Ожидаемо:

```text
selected_recipe заполнен
```

#### 9.4. Follow-up nutrition

```json
{
  "conversation_id": "{{conversation_id}}",
  "message": "Сколько в нем белка?",
  "options": {
    "include_debug": true
  }
}
```

Ожидаемо:

```text
nutrition заполнен
ответ относится к selected_recipe
```

#### 9.5. Замена в рецепте

```json
{
  "conversation_id": "{{conversation_id}}",
  "message": "Чем заменить сахар в этом рецепте?",
  "options": {
    "include_debug": true
  }
}
```

Ожидаемо:

```text
substitutions заполнены, если сахар есть в рецепте и правило есть в словаре
если сахара нет — понятный ответ без 500
```

#### 9.6. Общая замена без рецепта

```json
{
  "message": "Чем заменить сливочное масло в выпечке?",
  "options": {
    "include_debug": true
  }
}
```

Ожидаемо:

```text
ответ не требует выбрать рецепт
substitutions заполнены, если правило есть
selected_recipe = null
```

#### 9.7. Похожие рецепты с ограничением

```json
{
  "conversation_id": "{{conversation_id}}",
  "message": "Покажи похожие, но без яйца",
  "options": {
    "top_k": 5,
    "include_debug": true
  }
}
```

Ожидаемо:

```text
intent = similar_recipes
recipes не содержат яйцо
```

---

### 10. Definition of Done

Этап 2.5 считается завершенным, если выполнены все условия:

1. `pytest -q` проходит локально.
2. General substitution работает без выбранного рецепта.
3. Замена ингредиента в конкретном рецепте продолжает работать.
4. Multi-turn сценарий `search → details → nutrition` покрыт тестом.
5. Multi-turn сценарий `search → substitution` покрыт тестом.
6. Multi-turn сценарий `search → similar with exclusion` покрыт тестом.
7. Hard filters проверяются тестами на `final_results`.
8. Allergy/forbidden constraints возвращают warning.
9. Неоднозначный recipe title не выбирается случайно, а возвращает candidates.
10. Документация `docs/api-test-requests.md` обновлена под actual behavior.
11. В `docs/food_helper_rag_tz.md` больше нет утверждений, что уже реализованные компоненты “пока не реализованы”.
12. В коде нет full LLM orchestrator без eval-защиты и typed contracts.

---

### 11. Рекомендуемый порядок реализации

#### Шаг 1. Актуализировать документацию

Обновить раздел “Текущий статус проекта” в `docs/food_helper_rag_tz.md`, чтобы он соответствовал текущему состоянию репозитория.

#### Шаг 2. Добавить general substitution

Изменить schema/router/pipeline/service так, чтобы общие вопросы о замене ингредиента не требовали выбранного рецепта.

#### Шаг 3. Добавить тесты на substitution

Покрыть:

```text
общая замена без рецепта
замена в выбранном рецепте
замена по rank-reference
ингредиент не найден в рецепте
нет правила в словаре
```

#### Шаг 4. Расширить constraints extraction

Добавить include ingredients и дополнительные негативные кейсы.

#### Шаг 5. Добавить hard-filter tests

Проверить, что final results не содержат excluded/allergy ingredients.

#### Шаг 6. Добавить chat-flow tests

Проверить многошаговые сценарии через один `conversation_id`.

#### Шаг 7. Обновить manual smoke docs

Обновить `docs/api-test-requests.md` под новые сценарии.

#### Шаг 8. Только после этого готовить LLM-assisted слой

Следующий этап после 2.5:

```text
Stage 3 — LLM-assisted response layer
```

На Stage 3 LLM можно подключать как `AnswerFormatter` или `QueryRewriter`, но не как главный agentic orchestrator.

---

### 12. Риски и ограничения

#### Риск 1. False positive в ingredient matching

Текущий matching может находить ингредиент по substring. Это полезно для MVP, но может давать ложные совпадения.

Митигация:

```text
добавить alias/group dictionary
добавить тесты на частые false positives
по возможности сравнивать canonical ingredient names, а не весь raw JSON text
```

#### Риск 2. Слово “легкое” неоднозначно

`легкое` может значить:

```text
легкое по калориям
легкое в приготовлении
легкое для желудка
```

MVP-решение:

```text
если явно сказано “по калориям” → calories priority
если явно сказано “в приготовлении” → cooking_time/difficulty priority
если не уточнено → calories + fat + cooking_time + difficulty
```

#### Риск 3. Пользователь ожидает медицинскую безопасность

При allergy/forbidden constraints всегда добавлять warning.

Система не должна гарантировать, что рецепт безопасен при аллергии.

#### Риск 4. LLM может нарушить ограничения

На этапе 2.5 LLM не должна менять hard filters. Даже если LLM будет подключена, финальная выдача должна строиться только после deterministic filtering.

---

### 13. Что считать готовностью к Stage 3

К Stage 3 можно переходить, когда Stage 2.5 закрыт по DoD и есть стабильный eval-набор.

Stage 3 можно начинать с ограниченных LLM-компонентов:

```text
LLMAnswerFormatter
LLMQueryRewriter
LLMClarificationQuestionGenerator
LLMReasoningExplainer
```

Запрещено начинать Stage 3 с:

```text
LLM выбирает произвольный SQL
LLM сама решает, игнорировать ли аллергию
LLM генерирует рецепты как будто они из базы
LLM меняет список final_results без повторного deterministic filtering
```
