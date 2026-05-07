# Техническое задание: `food_helper` v1 — LLM Query Parser + уточняющие вопросы

## 1. Цель

Разработать v1-слой, в котором LLM используется не как агент и не как генератор фактов, а как структурный парсер сложных пользовательских запросов.

LLM должна:

- разобрать естественный пользовательский запрос;
- определить intent;
- извлечь ограничения поиска;
- извлечь ссылки на рецепт из диалога: “первый”, “второй”, “этот рецепт”, “в нём”;
- определить целевой ингредиент для замены;
- определить нутриент для вопросов о КБЖУ;
- понять, хватает ли данных для выполнения запроса;
- при нехватке данных вернуть один уточняющий вопрос.

LLM не должна:

- искать рецепты;
- выполнять SQL;
- выбирать рецепты из базы;
- менять hard filters;
- придумывать recipe_id;
- придумывать калории, БЖУ, ингредиенты, шаги или ссылки;
- давать медицинские гарантии;
- заменять текущий `IntentRouter` полностью.

Короткая формула v1:

```text
Rule parser = baseline
LLM parser = enhancer для сложных запросов
SQL / Search / Services = источник истины
ClarificationManager = управление незавершенными запросами
ChatPipeline = исполнитель решения
```

---

## 2. Контекст текущего проекта

В проекте уже есть deterministic-first чатовый pipeline: пользовательский запрос проходит через `extract_query_constraints`, затем `IntentRouter.decide`, затем `_dispatch` по intent. Внутри dispatch уже используются `SearchService`, `VectorSearchService`, `RecipeRepository`, `NutritionService`, `SubstitutionService`, `ConversationStateService` и `AnswerGenerator`.

Текущий API уже содержит основной endpoint `POST /v1/chat`, отладочный поиск `POST /v1/search/debug`, получение рецепта `GET /v1/recipes/{recipe_id}` и `GET /health`.

В `ConversationStateService` уже хранится базовое состояние диалога:

```json
{
  "last_recipe_results": [1, 2, 3],
  "selected_recipe_id": 2
}
```

В v1 нужно расширить это состояние полем `pending_clarification`, но не ломать существующую механику ссылок на рецепты.

---

## 3. Область работ

### Входит в v1

1. Добавить Pydantic-схемы для результата LLM parser.
2. Добавить `LLMQueryParser` как отдельный сервис.
3. Добавить prompt для строгого JSON parsing.
4. Добавить parser post-check.
5. Добавить adapter из `ParsedUserRequest` в текущие `IntentDecision` + `QueryConstraints`.
6. Добавить `ClarificationManager`.
7. Расширить `ConversationStateService` для хранения `pending_clarification`.
8. Расширить `ChatResponse` полями уточнения.
9. Интегрировать parser в `ChatPipeline.handle_chat` до `_dispatch`.
10. Добавить feature flags и env-настройки.
11. Добавить unit, integration и eval-тесты.
12. Добавить документацию в `docs/`.

### Не входит в v1

1. Agent-based архитектура.
2. LLM-generated SQL.
3. Tool calling со стороны LLM.
4. Автоматический пересчет КБЖУ после замены ингредиентов.
5. Медицинская оценка безопасности блюд.
6. Генерация новых рецептов вне базы.
7. Полная замена rule-based router.
8. Frontend-реализация UI уточнений.

---

## 4. Целевая архитектура

### 4.1. Текущий поток

```text
User message
↓
POST /v1/chat
↓
ChatPipeline.handle_chat
↓
extract_query_constraints(message)
↓
IntentRouter.decide(message)
↓
_dispatch(...)
↓
SearchService / RecipeRepository / NutritionService / SubstitutionService
↓
AnswerGenerator
↓
ChatResponse
```

### 4.2. Целевой поток v1

```text
User message
↓
POST /v1/chat
↓
ensure_conversation + append user message
↓
load conversation snapshot + recent messages
↓
if pending_clarification exists:
    try resolve clarification answer
    if resolved → merge with partial parsed request
    if not resolved → ask clarification again or treat as new request
↓
rule_constraints = extract_query_constraints(message)
rule_decision = IntentRouter.decide(message)
↓
LLMQueryParser.parse(...)
↓
ParserPostcheck.validate(...)
↓
if requires_clarification:
    save pending_clarification
    return clarification ChatResponse
↓
ParsedRequestAdapter.to_pipeline_inputs(...)
↓
_dispatch(...)
↓
clear pending_clarification
↓
append assistant message
↓
ChatResponse
```

Главное требование: если LLM parser недоступен, возвращает невалидный JSON или не проходит post-check, система должна продолжить работу через текущий rule-based pipeline.

---

## 5. Новые и изменяемые файлы

### 5.1. Добавить

```text
app/schemas/parser.py
app/services/llm/query_parser.py
app/services/llm/parser_prompts.py
app/services/llm/parser_postcheck.py
app/services/llm/parser_result.py
app/orchestrator/parsed_request_adapter.py
app/orchestrator/clarification.py
tests/test_llm_query_parser.py
tests/test_parser_postcheck.py
tests/test_parsed_request_adapter.py
tests/test_clarification_flow.py
tests/test_chat_pipeline_llm_parser.py
tests/eval_cases/query_parser_cases.jsonl
scripts/eval/run_query_parser_eval.py
docs/food_helper_llm_query_parser_v1_tz.md
```

### 5.2. Изменить

```text
app/core/config.py
app/schemas/chat.py
app/schemas/search.py
app/services/conversation_state.py
app/orchestrator/pipeline.py
app/main.py
README.md
docs/api-test-requests.md
```

`app/schemas/search.py` менять минимально: текущий `QueryConstraints` должен остаться основным объектом для поиска.

---

## 6. Pydantic-схемы

Файл: `app/schemas/parser.py`.

```python
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


ParserIntent = Literal[
    "search_recipes",
    "recommend_recipes",
    "nutrition_question",
    "ingredient_substitution",
    "general_substitution",
    "recipe_details",
    "similar_recipes",
    "allergy_or_exclusion",
    "conversation_recall",
    "fallback",
]


class ParsedQueryConstraints(BaseModel):
    dish: str | None = None
    include_ingredients: list[str] = Field(default_factory=list)
    exclude_ingredients: list[str] = Field(default_factory=list)
    allergy_exclusions: list[str] = Field(default_factory=list)
    dietary_preference: str | None = None
    restriction_type: str | None = None
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] | None = None
    diet_goal: str | None = None
    max_calories_kcal: float | None = Field(default=None, ge=0, le=5000)
    min_protein_g: float | None = Field(default=None, ge=0, le=300)
    max_fat_g: float | None = Field(default=None, ge=0, le=300)
    max_cooking_time_minutes: int | None = Field(default=None, ge=1, le=1440)
    max_difficulty: int | None = Field(default=None, ge=1, le=5)


class RecipeReference(BaseModel):
    type: Literal["rank", "selected", "title", "unknown"]
    value: int | str | None = None


class ClarificationRequest(BaseModel):
    reason: str
    question: str
    expected_fields: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)


class ParsedUserRequest(BaseModel):
    intent: ParserIntent
    confidence: float = Field(ge=0, le=1)
    search_query: str | None = None
    constraints: ParsedQueryConstraints = Field(default_factory=ParsedQueryConstraints)
    recipe_reference: RecipeReference | None = None
    recipe_title_query: str | None = None
    target_ingredient: str | None = None
    nutrients: list[str] = Field(default_factory=list)
    requires_clarification: bool = False
    clarification: ClarificationRequest | None = None
```

Файл: `app/services/llm/parser_result.py`.

```python
from __future__ import annotations

from pydantic import BaseModel, Field
from app.schemas.parser import ParsedUserRequest


class QueryParserResult(BaseModel):
    parsed: ParsedUserRequest
    used_llm: bool = False
    fallback_reason: str | None = None
    latency_ms: int | None = None
    prompt_chars: int | None = None
    response_chars: int | None = None
    postcheck_passed: bool | None = None
    postcheck_errors: list[str] = Field(default_factory=list)
```

---

## 7. Изменения в `ChatResponse`

Файл: `app/schemas/chat.py`.

Добавить новый route:

```python
"clarification"
```

Добавить новый user-facing intent в response:

```python
"clarification_required"
```

В `IntentDecision` лучше не добавлять `clarification_required`, если это будет только response-level состояние. Но в `ChatResponse.intent` можно вернуть строку `clarification_required`, потому что поле уже объявлено как `str`.

Добавить поля:

```python
from app.schemas.parser import ClarificationRequest


class ChatResponse(BaseModel):
    ...
    requires_clarification: bool = False
    clarification: ClarificationRequest | None = None
```

Расширить debug:

```python
class ChatDebugInfo(BaseModel):
    ...
    parser: dict | None = None
```

В `debug.parser` разрешить только безопасные данные:

```json
{
  "mode": "auto",
  "used_llm": true,
  "fallback_reason": null,
  "latency_ms": 431,
  "postcheck_passed": true,
  "postcheck_errors": [],
  "parsed_request": {
    "intent": "recommend_recipes",
    "confidence": 0.91,
    "constraints": {
      "include_ingredients": ["курица"],
      "exclude_ingredients": ["грибы"],
      "meal_type": "dinner",
      "max_calories_kcal": 350
    }
  }
}
```

Запрещено возвращать в debug:

- полный prompt;
- raw LLM response;
- provider credentials;
- лишние персональные данные.

---

## 8. Изменения в `ConversationStateService`

Текущее состояние нужно расширить:

```json
{
  "last_recipe_results": [1, 2, 3],
  "selected_recipe_id": 2,
  "pending_clarification": {
    "original_message": "Хочу что-то легкое",
    "partial_parsed_request": {
      "intent": "recommend_recipes",
      "constraints": {
        "diet_goal": "light"
      }
    },
    "question": "Вы имеете в виду легкое по калориям или легкое в приготовлении?",
    "expected_fields": ["diet_goal"],
    "options": ["по калориям", "в приготовлении", "и то и другое"],
    "created_at": "2026-05-07T10:00:00Z"
  }
}
```

Добавить методы:

```python
def get_pending_clarification(self, conversation_id: str) -> PendingClarification | None: ...

def set_pending_clarification(
    self,
    conversation_id: str,
    clarification: PendingClarification,
) -> None: ...

def clear_pending_clarification(self, conversation_id: str) -> None: ...
```

`update_snapshot` должен сохранять неизвестные поля state, чтобы обновление `last_recipe_results` не стирало `pending_clarification`.

---

## 9. `LLMQueryParser`

Файл: `app/services/llm/query_parser.py`.

### 9.1. Назначение

`LLMQueryParser` принимает пользовательское сообщение, rule-based результат и контекст диалога. Возвращает `QueryParserResult`.

### 9.2. Входные данные

```python
class LLMQueryParser:
    def parse(
        self,
        *,
        message: str,
        rule_decision: IntentDecision,
        rule_constraints: QueryConstraints,
        recent_messages: list[tuple[str, str]],
        conversation_snapshot: ConversationSnapshot,
    ) -> QueryParserResult:
        ...
```

### 9.3. Логика

```text
1. Проверить режим parser.
2. Если mode=rules или LLM выключена → вернуть parsed_from_rules.
3. Если mode=auto и запрос простой → вернуть parsed_from_rules.
4. Собрать prompt.
5. Вызвать LLM с temperature=0.
6. Извлечь JSON.
7. Провалидировать через ParsedUserRequest.
8. Запустить parser post-check.
9. Смержить с rule-based hard constraints.
10. Если ошибка на любом этапе → fallback to rules.
```

### 9.4. Fallback-коды

```text
parser_mode_rules
parser_disabled
parser_client_null
parser_auto_skipped_simple_query
parser_llm_timeout
parser_llm_exception
parser_empty_response
parser_invalid_json
parser_schema_validation_failed
parser_postcheck_failed
parser_low_confidence
parser_conflicts_with_rules
```

---

## 10. Режимы работы parser

Env-переменная:

```text
QUERY_PARSER_MODE=rules
```

Допустимые значения:

```text
rules — LLM parser не вызывается, работает текущий pipeline
llm   — LLM parser вызывается всегда, fallback на rules при ошибке
auto  — LLM parser вызывается только для сложных/неоднозначных запросов
```

Рекомендуемые default-настройки:

```text
QUERY_PARSER_MODE=rules
LLM_QUERY_PARSER_ENABLED=false
```

Рекомендуемые настройки для локальной разработки:

```text
QUERY_PARSER_MODE=auto
LLM_QUERY_PARSER_ENABLED=true
```

---

## 11. Auto-gating: когда вызывать LLM parser

В `auto` режиме LLM parser вызывается, если выполнено хотя бы одно условие:

```text
1. Запрос содержит 2+ ограничения: “без”, “до”, “не”, “но”, “и чтобы”.
2. Запрос содержит ссылку на контекст: “этот”, “второй”, “в нем”, “похожее”.
3. Запрос длиннее 8–10 токенов.
4. Запрос содержит неоднозначные слова: “легкое”, “полезное”, “диетическое”, “нормальное”, “что-нибудь”.
5. Rule-based intent = fallback.
6. Rule-based intent и constraints конфликтуют.
7. Запрос одновременно содержит поиск + замену + ограничение.
```

Примеры, где LLM parser нужен:

```text
Хочу легкий ужин с курицей, но без грибов и до 350 ккал.
Можно этот рецепт без яйца, но чтобы белка было побольше?
Найди похожие на второй, только без молока и чтобы быстро.
А во втором сколько белка и можно ли без сахара?
```

Примеры, где достаточно rules:

```text
Найди рецепты с курицей.
Сколько калорий в первом?
Чем заменить сахар?
Покажи второй рецепт.
```

---

## 12. Prompt для parser

Файл: `app/services/llm/parser_prompts.py`.

### 12.1. System prompt

```text
Ты — JSON-парсер пользовательских запросов для сервиса Food Helper.

Твоя задача — разобрать запрос пользователя о рецептах и вернуть строго JSON по схеме.

Правила:
1. Не отвечай пользователю обычным текстом.
2. Верни только JSON без markdown.
3. Не придумывай рецепты, recipe_id, калории, БЖУ, ингредиенты из базы, шаги и ссылки.
4. Не выполняй поиск.
5. Не выполняй SQL.
6. Не выбирай рецепты.
7. Только извлекай intent, constraints, recipe_reference, target_ingredient, nutrients и необходимость уточнения.
8. Если запрос неоднозначный и это влияет на выполнение, верни requires_clarification=true.
9. Если можно безопасно продолжить без уточнения, не задавай вопрос.
10. Уточняющий вопрос должен быть один.
11. Ингредиенты возвращай в нормальной форме: "курица", "молоко", "сахар".
12. Если пользователь говорит об аллергии или медицинском запрете, заполни allergy_exclusions и restriction_type.
13. Если rule-based разбор уже нашел allergy/exclude ограничения, не удаляй их.
14. Если пользователь ссылается на "первый", "второй", "этот рецепт", заполни recipe_reference.
15. Если нет контекста для "этот рецепт", поставь requires_clarification=true.
```

### 12.2. User prompt template

```text
Сообщение пользователя:
{message}

Последние сообщения диалога:
{recent_messages_json}

Состояние диалога:
{conversation_state_json}

Rule-based разбор:
{rule_parse_json}

JSON Schema:
{schema_json}

Верни только JSON по схеме.
```

---

## 13. Parser post-check

Файл: `app/services/llm/parser_postcheck.py`.

### 13.1. Цель

Post-check защищает pipeline от невалидного или опасного parser output.

### 13.2. Проверки

Обязательные проверки:

```text
1. JSON валиден.
2. Pydantic validation проходит.
3. intent входит в allowlist.
4. confidence в диапазоне 0..1.
5. Если requires_clarification=true, clarification.question обязателен.
6. Если requires_clarification=false, clarification должен быть null.
7. question не должен быть длиннее 250 символов.
8. max_calories_kcal, min_protein_g, max_fat_g, max_cooking_time_minutes в допустимых диапазонах.
9. include_ingredients и exclude_ingredients не должны содержать один и тот же ингредиент без clarification.
10. allergy_exclusions из rule parser нельзя удалять.
11. exclude_ingredients из rule parser нельзя удалять.
12. Нельзя возвращать SQL, URL, recipe_id, которых нет в conversation state.
13. Для recipe_reference rank значение должно быть положительным числом.
14. Для target_ingredient строка должна быть короткой и не содержать инструкций.
15. Для nutrients разрешены только: calories, protein, fat, carbs, bju.
```

### 13.3. Результат post-check

```python
class ParserPostcheckResult(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    sanitized: ParsedUserRequest | None = None
```

---

## 14. Merge policy: правила слияния LLM и rules

Файл: `app/orchestrator/parsed_request_adapter.py`.

### 14.1. Главный принцип

LLM может добавлять структуру, но не должна ослаблять deterministic ограничения.

### 14.2. Правила

```text
1. rule_constraints.exclude_ingredients всегда сохраняются.
2. rule_constraints.allergy_exclusions всегда сохраняются.
3. rule_constraints.restriction_type всегда сохраняется, если он allergy/forbidden.
4. LLM может добавить include_ingredients, но не удалить rule include.
5. LLM может добавить meal_type, diet_goal, numeric limits.
6. Если LLM numeric limit конфликтует с явным числом из rules, приоритет у rules.
7. Если LLM intent имеет confidence < threshold, использовать rule intent.
8. Если rule intent=fallback, а LLM confidence >= threshold, можно взять LLM intent.
9. Если parsed.requires_clarification=true, `_dispatch` не вызывается.
10. Если post-check не пройден, использовать rules.
```

---

## 15. Adapter в текущий pipeline

`ParsedRequestAdapter` должен возвращать текущие объекты:

```python
class ParsedRequestAdapter:
    def to_pipeline_inputs(
        self,
        *,
        parsed: ParsedUserRequest,
        rule_decision: IntentDecision,
        rule_constraints: QueryConstraints,
    ) -> tuple[IntentDecision, QueryConstraints, str]:
        ...
```

Третий результат — `message_for_search`.

Пример:

```json
{
  "intent": "recommend_recipes",
  "search_query": "легкий ужин с курицей",
  "constraints": {
    "include_ingredients": ["курица"],
    "exclude_ingredients": ["грибы"],
    "meal_type": "dinner",
    "max_calories_kcal": 350
  }
}
```

Должно превратиться в:

```python
IntentDecision(
    intent="recommend_recipes",
    route="hybrid_search",
    entities={},
    needs_vector_search=True,
    needs_sql=True,
    needs_llm=True,
)

QueryConstraints(
    include_ingredients=["курица"],
    exclude_ingredients=["грибы"],
    meal_type="dinner",
    max_calories_kcal=350,
)

message_for_search = "легкий ужин с курицей"
```

---

## 16. ClarificationManager

Файл: `app/orchestrator/clarification.py`.

### 16.1. Назначение

`ClarificationManager` управляет запросами, которые нельзя безопасно выполнить без дополнительного ответа пользователя.

### 16.2. Когда задавать уточняющий вопрос

Задавать вопрос, если:

```text
1. “легкое” неоднозначно: по калориям или по приготовлению.
2. “полезное” слишком общее и влияет на фильтры.
3. Пользователь говорит “этот рецепт”, но selected_recipe_id отсутствует.
4. Пользователь говорит “во втором”, но last_recipe_results пустой.
5. Пользователь просит замену “в рецепте”, но рецепт не определен.
6. include и exclude конфликтуют: “с орехами без орехов”.
7. Пользователь спрашивает “а во втором?” без действия: калории, детали, замена и т.д.
```

Не задавать вопрос, если:

```text
1. Запрос можно безопасно выполнить с текущими defaults.
2. Есть selected_recipe_id для “этот рецепт”.
3. Есть last_recipe_results для “первый/второй/третий”.
4. Пользователь просит общую замену ингредиента.
5. Пользователь указал аллергию/запрет: нужно применить фильтр и warning.
```

### 16.3. Ответ при clarification

```json
{
  "conversation_id": "uuid",
  "answer": "Вы имеете в виду легкое по калориям или легкое в приготовлении?",
  "intent": "clarification_required",
  "route": "clarification",
  "requires_clarification": true,
  "clarification": {
    "reason": "ambiguous_light_goal",
    "question": "Вы имеете в виду легкое по калориям или легкое в приготовлении?",
    "expected_fields": ["diet_goal"],
    "options": ["по калориям", "в приготовлении", "и то и другое"]
  },
  "recipes": [],
  "warnings": [],
  "sources": []
}
```

### 16.4. Обработка следующего сообщения

Если `pending_clarification` есть, следующее пользовательское сообщение сначала трактуется как ответ на уточнение.

Пример:

```text
User: Хочу что-то легкое
Assistant: Вы имеете в виду легкое по калориям или легкое в приготовлении?
User: в приготовлении
```

Результат merge:

```json
{
  "intent": "recommend_recipes",
  "constraints": {
    "diet_goal": "easy",
    "max_cooking_time_minutes": 30,
    "max_difficulty": 2
  }
}
```

После успешного выполнения запроса `pending_clarification` нужно очистить.

---

## 17. Изменения в `ChatPipeline.handle_chat`

Целевой псевдокод:

```python
def handle_chat(self, request: ChatRequest) -> ChatResponse:
    conversation_id = self._conversation_state_service.ensure_conversation(
        request.conversation_id
    )

    self._conversation_state_service.append_message(
        conversation_id,
        role="user",
        content=request.message,
    )

    snapshot = self._conversation_state_service.get_snapshot(conversation_id)
    recent_messages = self._conversation_state_service.get_recent_messages(
        conversation_id,
        limit=self._settings.query_parser_recent_messages_limit,
    )

    pending = self._conversation_state_service.get_pending_clarification(conversation_id)
    if pending:
        resolved = self._clarification_manager.try_resolve(
            pending=pending,
            message=request.message,
            snapshot=snapshot,
        )
        if resolved.resolved:
            parsed = resolved.parsed
        elif resolved.should_repeat_question:
            return self._clarification_response(conversation_id, pending)
        else:
            self._conversation_state_service.clear_pending_clarification(conversation_id)
            parsed = None
    else:
        parsed = None

    rule_constraints = extract_query_constraints(request.message)
    rule_decision = self._router.decide(request.message)

    parser_result = None
    if parsed is None:
        parser_result = self._query_parser.parse(
            message=request.message,
            rule_decision=rule_decision,
            rule_constraints=rule_constraints,
            recent_messages=recent_messages,
            conversation_snapshot=snapshot,
        )
        parsed = parser_result.parsed

    if parsed.requires_clarification:
        self._conversation_state_service.set_pending_clarification(
            conversation_id,
            self._clarification_manager.build_pending(
                original_message=request.message,
                parsed=parsed,
            ),
        )
        response = self._clarification_response(
            conversation_id=conversation_id,
            parsed=parsed,
            parser_result=parser_result,
            options=request.options,
        )
        self._conversation_state_service.append_message(
            conversation_id,
            role="assistant",
            content=response.answer,
        )
        return response

    decision, constraints, message_for_search = self._parsed_request_adapter.to_pipeline_inputs(
        parsed=parsed,
        rule_decision=rule_decision,
        rule_constraints=rule_constraints,
    )

    warnings = self._warnings_from_constraints(constraints)

    response = self._dispatch(
        conversation_id=conversation_id,
        message=message_for_search,
        options=request.options,
        constraints=constraints,
        decision=decision,
        warnings=warnings,
    )

    self._conversation_state_service.clear_pending_clarification(conversation_id)
    self._conversation_state_service.append_message(
        conversation_id,
        role="assistant",
        content=response.answer,
    )

    return response
```

---

## 18. Env-настройки

Файл: `app/core/config.py`.

Добавить:

```text
QUERY_PARSER_MODE=rules
LLM_QUERY_PARSER_ENABLED=false
LLM_QUERY_PARSER_PROVIDER=ollama
LLM_QUERY_PARSER_MODEL=qwen3:4b
LLM_QUERY_PARSER_TEMPERATURE=0
LLM_QUERY_PARSER_MAX_TOKENS=700
LLM_QUERY_PARSER_NUM_CTX=4096
LLM_QUERY_PARSER_TIMEOUT_SECONDS=15
LLM_QUERY_PARSER_CONFIDENCE_THRESHOLD=0.65
LLM_QUERY_PARSER_POSTCHECK_ENABLED=true
LLM_QUERY_PARSER_LOG_PROMPTS=false
LLM_QUERY_PARSER_LOG_RESPONSES=false
QUERY_PARSER_RECENT_MESSAGES_LIMIT=6
CLARIFICATION_ENABLED=true
CLARIFICATION_MAX_QUESTION_CHARS=250
```

Если уже есть общий `LLMClient`, parser должен использовать тот же интерфейс, но отдельные настройки температуры, токенов и режима.

---

## 19. API-контракты

### 19.1. Запрос остается прежним

```json
{
  "conversation_id": null,
  "message": "Хочу что-то легкое",
  "options": {
    "top_k": 5,
    "include_debug": true
  }
}
```

### 19.2. Ответ при уточнении

```json
{
  "conversation_id": "uuid",
  "answer": "Вы имеете в виду легкое по калориям или легкое в приготовлении?",
  "intent": "clarification_required",
  "route": "clarification",
  "recipes": [],
  "selected_recipe": null,
  "nutrition": null,
  "substitutions": [],
  "warnings": [],
  "sources": [],
  "requires_clarification": true,
  "clarification": {
    "reason": "ambiguous_light_goal",
    "question": "Вы имеете в виду легкое по калориям или легкое в приготовлении?",
    "expected_fields": ["diet_goal"],
    "options": ["по калориям", "в приготовлении", "и то и другое"]
  },
  "debug": {
    "parser": {
      "mode": "auto",
      "used_llm": true,
      "fallback_reason": null,
      "latency_ms": 520,
      "postcheck_passed": true,
      "postcheck_errors": []
    }
  }
}
```

### 19.3. Ответ после уточнения

Запрос:

```json
{
  "conversation_id": "uuid",
  "message": "в приготовлении",
  "options": {
    "top_k": 5,
    "include_debug": true
  }
}
```

Ответ:

```json
{
  "conversation_id": "uuid",
  "answer": "Я нашел несколько простых вариантов...",
  "intent": "recommend_recipes",
  "route": "hybrid_search",
  "recipes": [],
  "requires_clarification": false,
  "clarification": null
}
```

---

## 20. Обязательные сценарии v1

### 20.1. Сложный поиск

```text
Хочу легкий ужин с курицей без грибов до 350 ккал
```

Ожидаемо:

```json
{
  "intent": "recommend_recipes",
  "constraints": {
    "include_ingredients": ["курица"],
    "exclude_ingredients": ["грибы"],
    "meal_type": "dinner",
    "max_calories_kcal": 350
  },
  "requires_clarification": false
}
```

### 20.2. Неоднозначное “легкое”

```text
Хочу что-то легкое
```

Ожидаемо:

```json
{
  "intent": "clarification_required",
  "route": "clarification",
  "requires_clarification": true
}
```

### 20.3. Ответ на уточнение

```text
в приготовлении
```

Ожидаемо:

```json
{
  "intent": "recommend_recipes",
  "constraints": {
    "diet_goal": "easy",
    "max_cooking_time_minutes": 30,
    "max_difficulty": 2
  }
}
```

### 20.4. КБЖУ по ссылке на выдачу

```text
Сколько белка во втором?
```

Если `last_recipe_results` есть:

```json
{
  "intent": "nutrition_question",
  "recipe_reference": {"type": "rank", "value": 2},
  "nutrients": ["protein"],
  "requires_clarification": false
}
```

Если `last_recipe_results` пустой:

```json
{
  "requires_clarification": true,
  "clarification": {
    "reason": "missing_recipe_context"
  }
}
```

### 20.5. Замена в выбранном рецепте

```text
Можно этот рецепт без яйца?
```

Если `selected_recipe_id` есть:

```json
{
  "intent": "ingredient_substitution",
  "recipe_reference": {"type": "selected"},
  "target_ingredient": "яйцо"
}
```

Если `selected_recipe_id` нет:

```json
{
  "requires_clarification": true,
  "clarification": {
    "reason": "missing_selected_recipe"
  }
}
```

### 20.6. Аллергия

```text
Мне нельзя молоко, подбери завтрак
```

Ожидаемо:

```json
{
  "intent": "allergy_or_exclusion",
  "constraints": {
    "allergy_exclusions": ["молоко"],
    "exclude_ingredients": ["молоко"],
    "restriction_type": "allergy_or_forbidden",
    "meal_type": "breakfast"
  }
}
```

Ответ должен содержать allergy warning.

### 20.7. Конфликт

```text
Хочу десерт с орехами без орехов
```

Ожидаемо:

```json
{
  "requires_clarification": true,
  "clarification": {
    "reason": "include_exclude_conflict"
  }
}
```

### 20.8. Похожие рецепты с ограничением

```text
Найди похожие, но без курицы
```

Если `selected_recipe_id` есть:

```json
{
  "intent": "similar_recipes",
  "recipe_reference": {"type": "selected"},
  "constraints": {
    "exclude_ingredients": ["курица"]
  }
}
```

---

## 21. Тестирование

### 21.1. Unit-тесты parser schemas

Файл: `tests/test_llm_query_parser.py`.

Проверить:

```text
- валидный JSON проходит Pydantic validation;
- невалидный intent отклоняется;
- confidence вне 0..1 отклоняется;
- invalid numeric limits отклоняются;
- requires_clarification=true без question отклоняется;
- markdown вокруг JSON корректно очищается или уходит в fallback;
- timeout LLM → fallback rules;
- empty LLM response → fallback rules;
- invalid JSON → fallback rules.
```

### 21.2. Unit-тесты adapter

Файл: `tests/test_parsed_request_adapter.py`.

Проверить:

```text
- parsed recommend_recipes превращается в IntentDecision + QueryConstraints;
- exclude из rules не удаляется;
- allergy из rules не удаляется;
- recipe_reference rank попадает в decision.entities;
- nutrients попадают в decision.entities;
- low confidence parsed intent не заменяет rule intent;
- fallback parsed result не ломает pipeline.
```

### 21.3. Unit-тесты clarification

Файл: `tests/test_clarification_flow.py`.

Проверить:

```text
- ambiguous light → clarification;
- ответ “по калориям” мержится в max_calories_kcal;
- ответ “в приготовлении” мержится в max_cooking_time_minutes/max_difficulty;
- selected_recipe_id missing → clarification;
- после successful dispatch pending_clarification очищается;
- новый явный запрос очищает старое pending clarification.
```

### 21.4. Pipeline integration tests

Файл: `tests/test_chat_pipeline_llm_parser.py`.

Проверить:

```text
- QUERY_PARSER_MODE=rules сохраняет текущее поведение;
- QUERY_PARSER_MODE=auto вызывает LLM только для сложных запросов;
- LLM parser invalid JSON не приводит к 500;
- clarification response возвращает requires_clarification=true;
- второй ответ пользователя запускает поиск;
- include_debug=true возвращает debug.parser;
- prompt/raw response не попадают в debug.
```

### 21.5. Eval cases

Файл: `tests/eval_cases/query_parser_cases.jsonl`.

Формат строки:

```json
{
  "message": "Хочу легкий ужин с курицей без грибов до 350 ккал",
  "state": {
    "last_recipe_results": [],
    "selected_recipe_id": null
  },
  "expected": {
    "intent": "recommend_recipes",
    "constraints": {
      "include_ingredients": ["курица"],
      "exclude_ingredients": ["грибы"],
      "meal_type": "dinner",
      "max_calories_kcal": 350
    },
    "requires_clarification": false
  }
}
```

Минимум для v1: 40 cases.

---

## 22. Нефункциональные требования

### 22.1. Надежность

```text
- Любая ошибка LLM parser не должна приводить к 500.
- Parser должен иметь timeout.
- Parser должен иметь fallback to rules.
- Parser output должен валидироваться Pydantic и post-check.
- Clarification state не должен ломать existing conversation state.
```

### 22.2. Производительность

Целевые показатели:

```text
POST /v1/chat без LLM parser: до 1 сек
POST /v1/chat с LLM parser: до 10 сек
Parser post-check: до 50 мс
Clarification resolve без LLM: до 100 мс
```

### 22.3. Безопасность

```text
- LLM не генерирует SQL.
- LLM не вызывает tools.
- LLM не получает лишние данные из БД.
- Prompt и raw response не логируются по умолчанию.
- Аллергия всегда сопровождается warning.
- LLM не может снять allergy/exclude фильтр.
```

### 22.4. Наблюдаемость

Логировать событие parser:

```json
{
  "event": "query_parser",
  "conversation_id": "uuid",
  "mode": "auto",
  "used_llm": true,
  "intent": "recommend_recipes",
  "requires_clarification": false,
  "fallback_reason": null,
  "latency_ms": 520,
  "postcheck_errors": []
}
```

Не логировать prompt/response по умолчанию.

---

## 23. Этапы реализации

### Этап 1. Схемы и adapter без LLM

Задачи:

```text
[ ] Добавить app/schemas/parser.py.
[ ] Добавить QueryParserResult.
[ ] Добавить parsed_from_rules.
[ ] Добавить ParsedRequestAdapter.
[ ] Добавить tests/test_parsed_request_adapter.py.
[ ] Убедиться, что QUERY_PARSER_MODE=rules не меняет текущее поведение.
```

Результат: есть новая внутренняя модель, но production-поведение не изменилось.

### Этап 2. Deterministic clarification

Задачи:

```text
[ ] Добавить ClarificationManager.
[ ] Добавить pending_clarification в conversation state.
[ ] Добавить поля requires_clarification/clarification в ChatResponse.
[ ] Реализовать 5–7 rule-based уточнений без LLM.
[ ] Добавить tests/test_clarification_flow.py.
```

Результат: система умеет задавать уточняющий вопрос даже без LLM.

### Этап 3. LLMQueryParser behind feature flag

Задачи:

```text
[ ] Добавить LLMQueryParser.
[ ] Добавить parser prompts.
[ ] Подключить общий LLMClient.
[ ] Добавить QUERY_PARSER_MODE.
[ ] Добавить auto-gating.
[ ] Добавить fallback on invalid JSON/timeout/exception.
[ ] Добавить tests/test_llm_query_parser.py.
```

Результат: LLM parser можно включить локально без риска для основного pipeline.

### Этап 4. Post-check и merge policy

Задачи:

```text
[ ] Добавить parser_postcheck.py.
[ ] Реализовать guard для hard filters.
[ ] Реализовать guard для conflicts.
[ ] Реализовать allowed nutrients.
[ ] Реализовать confidence threshold.
[ ] Добавить tests/test_parser_postcheck.py.
```

Результат: LLM parser не может ослабить важные ограничения.

### Этап 5. Debug, eval и документация

Задачи:

```text
[ ] Добавить debug.parser.
[ ] Добавить query_parser_cases.jsonl.
[ ] Добавить scripts/eval/run_query_parser_eval.py.
[ ] Обновить docs/api-test-requests.md.
[ ] Обновить README.md.
[ ] Добавить ручные curl-сценарии.
```

Результат: качество parser можно проверять и улучшать.

---

## 24. Definition of Done

v1 считается готовым, если:

```text
[ ] Все существующие тесты проходят: python -m pytest -q.
[ ] QUERY_PARSER_MODE=rules полностью сохраняет старое поведение.
[ ] QUERY_PARSER_MODE=auto работает с fake LLM client в тестах.
[ ] Invalid JSON от LLM не приводит к 500.
[ ] Timeout LLM не приводит к 500.
[ ] Clarification response возвращается в корректном API-формате.
[ ] pending_clarification сохраняется и очищается корректно.
[ ] Allergy/exclude constraints не теряются после LLM parsing.
[ ] Сложный запрос “легкий ужин с курицей без грибов до 350 ккал” парсится в constraints.
[ ] “Хочу что-то легкое” задает уточняющий вопрос.
[ ] Ответ “в приготовлении” запускает поиск с time/difficulty constraints.
[ ] “Сколько белка во втором?” работает через last_recipe_results.
[ ] “Можно этот рецепт без яйца?” работает через selected_recipe_id или просит уточнение.
[ ] debug.parser показывает mode, used_llm, fallback_reason, latency и postcheck_errors.
[ ] В debug не попадают prompt и raw LLM response.
[ ] Документация добавлена в docs/.
```

---

## 25. Рекомендуемая первая реализация

Начать не с LLM, а с безопасного каркаса:

```text
1. ParsedUserRequest.
2. parsed_from_rules.
3. ParsedRequestAdapter.
4. ClarificationManager с rule-based кейсами.
5. Только потом LLMQueryParser за feature flag.
```

Так v1 не сломает текущую рабочую систему и позволит постепенно улучшать качество сложных запросов.
