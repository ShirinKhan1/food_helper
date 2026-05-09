from __future__ import annotations

import json

from app.schemas.chat import IntentDecision
from app.schemas.search import QueryConstraints


PARSER_SYSTEM_PROMPT = """Ты — JSON-парсер пользовательских запросов для сервиса Food Helper.

Твоя задача — разобрать запрос пользователя о рецептах и вернуть строго JSON по схеме.

Правила:
1. Не отвечай пользователю обычным текстом.
2. Верни только JSON без markdown.
3. Не придумывай рецепты, recipe_id, калории, БЖУ, ингредиенты из базы, шаги и ссылки.
4. Не выполняй поиск.
5. Не выполняй SQL.
6. Не выбирай рецепты.
7. Только извлекай intent, constraints, event_profile, recipe_reference, target_ingredient, nutrients и необходимость уточнения.
8. Если запрос неоднозначный и это влияет на выполнение, верни requires_clarification=true.
9. Если можно безопасно продолжить без уточнения, не задавай вопрос.
10. Уточняющий вопрос должен быть один.
11. Ингредиенты возвращай в нормальной форме: "курица", "молоко", "сахар".
12. Если пользователь говорит об аллергии или медицинском запрете, заполни allergy_exclusions и restriction_type.
13. Если rule-based разбор уже нашел allergy/exclude ограничения, не удаляй их.
14. Если пользователь ссылается на "первый", "второй", "этот рецепт", заполни recipe_reference.
15. Если нет контекста для "этот рецепт", поставь requires_clarification=true.
16. Для меню под событие (праздник, свидание, друзья, день рождения, пикник и т.д.) используй intent=event_recommendation и при необходимости заполни event_profile (event_type из whitelist ТЗ, guests_count, vibe, meal_roles).
"""

PARSER_SCHEMA_HINT = """JSON-поля верхнего уровня:
- intent: search_recipes | recommend_recipes | event_recommendation | nutrition_question | ingredient_substitution | general_substitution | recipe_details | similar_recipes | allergy_or_exclusion | conversation_recall | fallback
- confidence: число 0..1
- search_query: строка или null
- constraints: объект с полями dish, include_ingredients[], exclude_ingredients[], allergy_exclusions[], dietary_preference, restriction_type, meal_type (breakfast|lunch|dinner|snack|null), diet_goal, max_calories_kcal, min_protein_g, max_fat_g, max_cooking_time_minutes, max_difficulty
- recipe_reference: {type: rank|selected|title|unknown, value: number|string|null} или null
- recipe_title_query: строка или null
- target_ingredient: строка или null
- nutrients: массив строк из: calories, protein, fat, carbs, bju
- event_profile: {event_type, guests_count, format, vibe[], meal_roles[], preparation_style} или null
- requires_clarification: boolean
- clarification: {reason, question, expected_fields[], options[]} или null (если requires_clarification=false, clarification=null)
"""


def build_parser_user_prompt(
    *,
    message: str,
    recent_messages_json: str,
    conversation_state_json: str,
    rule_parse_json: str,
) -> str:
    return f"""Сообщение пользователя:
{message}

Последние сообщения диалога:
{recent_messages_json}

Состояние диалога:
{conversation_state_json}

Rule-based разбор:
{rule_parse_json}

JSON Schema (описание полей):
{PARSER_SCHEMA_HINT}

Верни только JSON по схеме.
"""


def rule_parse_json_for_prompt(
    *,
    rule_decision: IntentDecision,
    rule_constraints: QueryConstraints,
) -> str:
    payload = {
        "intent": rule_decision.intent,
        "route": rule_decision.route,
        "entities": rule_decision.entities,
        "constraints": rule_constraints.model_dump(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
