# API test requests for Postman

Файл содержит ручные проверки работоспособности Food Helper API через Postman.

## Перед проверкой

1. Подними API:

```powershell
docker compose up -d api
```

2. В Postman создай environment:

| Variable | Initial value | Current value |
|---|---:|---:|
| `base_url` | `http://localhost:8000` | `http://localhost:8000` |
| `conversation_id` |  |  |
| `recipe_id` |  |  |

3. Для `POST`-запросов в Postman открой `Body`, выбери `raw`, справа в выпадающем списке выбери `JSON` и вставляй тело запроса без дополнительных кавычек.

Postman при выборе `JSON` сам выставит header, но можно проверить, что он есть:

```http
Content-Type: application/json
```

## 1. Health check

Проверяет, что FastAPI отвечает, БД доступна, а статус модели эмбеддингов виден приложению.

```http
GET {{base_url}}/health
```

Ожидаемо:

- HTTP `200`.
- `status` равен `ok`, если БД доступна.
- `db` равен `ok`.
- `embedding_model` содержит статус модели.

Пример ответа:

```json
{
  "status": "ok",
  "db": "ok",
  "embedding_model": "not_loaded"
}
```

## 2. Chat: поиск рецептов

Базовая проверка основного пользовательского сценария.

```http
POST {{base_url}}/v1/chat
```

Body:

```json
{
  "message": "Посоветуй легкий ужин с курицей без грибов",
  "options": {
    "top_k": 5,
    "include_debug": true
  }
}
```

Ожидаемо:

- HTTP `200`.
- Есть `conversation_id`.
- `intent` обычно `search_recipes` или `recommend_recipes`.
- В `recipes` вернулся список рецептов.
- Если `include_debug=true`, поле `debug` заполнено.

После ответа можно сохранить:

- `conversation_id` из ответа в переменную Postman `conversation_id`.
- `recipes[0].recipe_id` в переменную Postman `recipe_id`.

## 3. Chat: продолжение диалога

Проверяет, что приложение принимает `conversation_id` и может использовать контекст предыдущего ответа.

```http
POST {{base_url}}/v1/chat
```

Body:

```json
{
  "conversation_id": "{{conversation_id}}",
  "message": "Расскажи подробнее про первый рецепт",
  "options": {
    "top_k": 3,
    "include_debug": true
  }
}
```

Ожидаемо:

- HTTP `200`.
- `conversation_id` совпадает с переданным.
- Заполнено `selected_recipe`, если контекст позволил выбрать рецепт.
- В `sources` есть ссылка на использованный рецепт.

## 4. Chat: общая замена ингредиента

Проверяет `general_substitution`: подбор замен без привязки к конкретному рецепту.

```http
POST {{base_url}}/v1/chat
```

Body:

```json
{
  "message": "Чем заменить молоко?",
  "options": {
    "top_k": 5,
    "include_debug": true
  }
}
```

Ожидаемо:

- HTTP `200`.
- `intent` равен `general_substitution`.
- `route` равен `substitution_catalog`.
- В `substitutions` есть варианты замен, если правило найдено.
- `recipes` пустой, `selected_recipe` равен `null`.
- В `warnings` есть предупреждение, что рекомендация общая и не привязана к рецепту.
- `answer` содержит человекочитаемый ответ.

## 4.1. Chat: замена ингредиента в выбранном рецепте

Проверяет recipe-bound substitution после поисковой выдачи в том же `conversation_id`.

```http
POST {{base_url}}/v1/chat
```

Body:

```json
{
  "conversation_id": "{{conversation_id}}",
  "message": "На что в первом рецепте можно заменить сахар?",
  "options": {
    "top_k": 5,
    "include_debug": true
  }
}
```

Ожидаемо:

- HTTP `200`.
- `intent` равен `ingredient_substitution`, если рецепт найден по позиции, или `general_substitution`, если контекста рецепта нет.
- При recipe-bound ответе заполнен `selected_recipe`.
- В `substitutions` есть варианты замен, если правило найдено.

## 4.2. Chat: фильтр “без ингредиента” не считается заменой

Проверяет, что поисковый запрос с `без молока` идет в hybrid search, а не в substitution.

```http
POST {{base_url}}/v1/chat
```

Body:

```json
{
  "message": "Найди рецепт без молока",
  "options": {
    "top_k": 5,
    "include_debug": true
  }
}
```

Ожидаемо:

- HTTP `200`.
- `intent` равен `search_recipes` или `allergy_or_exclusion`.
- `route` равен `hybrid_search`.
- В `debug.constraints.exclude_ingredients` есть `молоко`.
- В `debug.final_results` не должно быть рецептов со структурированным ингредиентом `молоко`.

## 5. Chat: вопрос по питательности

Проверяет обработку запроса про КБЖУ.

```http
POST {{base_url}}/v1/chat
```

Body:

```json
{
  "message": "Сколько калорий и белка в рецепте с курицей?",
  "options": {
    "top_k": 5,
    "include_debug": true
  }
}
```

Ожидаемо:

- HTTP `200`.
- `intent` равен `nutrition_question` или связанному intent.
- В ответе есть `nutrition` или рецепты с полями `calories_kcal`, `protein_g`, `fat_g`, `carbs_g`.

## 6. Search debug: гибридный поиск

Проверяет поисковый слой отдельно от chat pipeline.

```http
POST {{base_url}}/v1/search/debug
```

Body:

```json
{
  "query": "легкий завтрак без молока до 300 ккал",
  "top_k": 5,
  "filters": {
    "exclude_ingredients": ["молоко"],
    "meal_type": "breakfast",
    "max_calories_kcal": 300
  }
}
```

Ожидаемо:

- HTTP `200`.
- `normalized_query` заполнен.
- `constraints` содержит ограничения из текста и `filters`.
- `vector_results`, `keyword_results`, `final_results` возвращают массивы.
- В элементах результатов есть `recipe_id`, `title`, `score` или `similarity`.

## 7. Recipe detail

Проверяет получение полной карточки рецепта по ID.

```http
GET {{base_url}}/v1/recipes/{{recipe_id}}
```

Если переменная `recipe_id` еще не сохранена, возьми любой `recipe_id` из `recipes` или `final_results` предыдущих запросов.

Ожидаемо:

- HTTP `200`.
- Есть `recipe_id`, `title`, `ingredients`, `steps`, `nutrition`, `recipe_url`.
- `ingredients` и `steps` возвращаются массивами.

## 8. Negative: пустой chat message

Проверяет валидацию пустого сообщения.

```http
POST {{base_url}}/v1/chat
```

Body:

```json
{
  "message": "   "
}
```

Ожидаемо:

- HTTP `400`.
- `detail` равен `Message must not be empty.`

## 9. Negative: слишком длинное chat message

Проверяет ограничение `MAX_MESSAGE_CHARS`.

```http
POST {{base_url}}/v1/chat
```

Body:

```json
{
  "message": "Повтори этот текст много раз, чтобы превысить лимит MAX_MESSAGE_CHARS в 1000 символов. Повтори этот текст много раз, чтобы превысить лимит MAX_MESSAGE_CHARS в 1000 символов. Повтори этот текст много раз, чтобы превысить лимит MAX_MESSAGE_CHARS в 1000 символов. Повтори этот текст много раз, чтобы превысить лимит MAX_MESSAGE_CHARS в 1000 символов. Повтори этот текст много раз, чтобы превысить лимит MAX_MESSAGE_CHARS в 1000 символов. Повтори этот текст много раз, чтобы превысить лимит MAX_MESSAGE_CHARS в 1000 символов. Повтори этот текст много раз, чтобы превысить лимит MAX_MESSAGE_CHARS в 1000 символов. Повтори этот текст много раз, чтобы превысить лимит MAX_MESSAGE_CHARS в 1000 символов. Повтори этот текст много раз, чтобы превысить лимит MAX_MESSAGE_CHARS в 1000 символов. Повтори этот текст много раз, чтобы превысить лимит MAX_MESSAGE_CHARS в 1000 символов. Повтори этот текст много раз, чтобы превысить лимит MAX_MESSAGE_CHARS в 1000 символов."
}
```

Ожидаемо:

- HTTP `400`.
- `detail` начинается с `Message is too long.`

## 10. Negative: пустой search query

Проверяет валидацию debug search.

```http
POST {{base_url}}/v1/search/debug
```

Body:

```json
{
  "query": "   "
}
```

Ожидаемо:

- HTTP `400`.
- `detail` равен `Query must not be empty.`

## 11. Negative: рецепт не найден

Проверяет корректный `404` для неизвестного рецепта.

```http
GET {{base_url}}/v1/recipes/999999999
```

Ожидаемо:

- HTTP `404`.
- `detail` равен `Recipe not found.`

## Быстрый smoke checklist

Минимальный набор перед ручной демонстрацией:

1. `GET /health` возвращает `200` и `db: ok`.
2. `POST /v1/search/debug` возвращает непустой `final_results`.
3. `POST /v1/chat` возвращает `answer` и хотя бы один рецепт для поискового запроса.
4. `POST /v1/chat` с `"Чем заменить молоко?"` возвращает `general_substitution` и `substitutions`.
5. `POST /v1/chat` с `"Найди рецепт без молока"` возвращает `hybrid_search`, а `debug.constraints.exclude_ingredients` содержит `молоко`.
6. `GET /v1/recipes/{recipe_id}` возвращает полный рецепт по ID из поиска или чата.
7. Негативные запросы возвращают ожидаемые `400`/`404`, а не `500`.

