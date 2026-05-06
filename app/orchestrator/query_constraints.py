from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable

from app.schemas.search import QueryConstraints

_SEPARATOR_RE = re.compile(r"\s*(?:,|/)\s*|\s+(?:и|или)\s+")
_WITHOUT_RE = re.compile(
    r"(?:^|[\s,])(без|исключая)\s+([а-яёa-z0-9\-%\s,/-]+?)(?=(?:[?.!,]|$| чтобы | где | который | которая | которые ))",
    re.IGNORECASE,
)
_FORBIDDEN_RE = re.compile(
    r"(?:мне\s+)?(?:нельзя|не\s+подходит|не\s+переношу|не\s+ем)\s+([а-яёa-z0-9\-%\s,/-]+?)(?=(?:[?.!,]|$| но | что | чтобы ))",
    re.IGNORECASE,
)
_ALLERGY_RE = re.compile(
    r"(?:аллергия|аллерген(?:ы)?|аллергич(?:ен|на))\s+(?:на\s+)?([а-яёa-z0-9\-%\s,/-]+?)(?=(?:[?.!,]|$| но | что | чтобы ))",
    re.IGNORECASE,
)
_INCLUDE_RE_LIST = [
    re.compile(
        r"(?:рецепт\w*|блюд[ао]?|ужин|обед|завтрак|перекус)\s+(?:[^?.!,]*?\s)?с\s+([а-яёa-z0-9\-%\s,/-]+?)(?=(?:\s+без\b|\s+до\b|\s+для\b|\s+чтобы\b|\s+котор|[?.!,]|$))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:что\s+)?(?:можно\s+)?приготовить\s+из\s+([а-яёa-z0-9\-%\s,/-]+?)(?=(?:\s+без\b|\s+до\b|\s+для\b|\s+чтобы\b|\s+котор|[?.!,]|$))",
        re.IGNORECASE,
    ),
]
_CALORIES_LIMIT_RE = re.compile(r"до\s+(\d{2,4})\s*к?кал", re.IGNORECASE)
_SERVICE_INCLUDE_TOKENS = {
    "рецепт",
    "рецепты",
    "блюдо",
    "блюда",
    "ужин",
    "обед",
    "завтрак",
    "перекус",
    "легкий",
    "лёгкий",
    "быстрый",
    "низкокалорийный",
}


def _clean_token(value: str) -> str:
    token = " ".join(value.strip().lower().split())
    return token.strip(" .,!?:;")


@lru_cache(maxsize=1)
def _morph_analyzer():
    from pymorphy3 import MorphAnalyzer

    return MorphAnalyzer()


def _lemmatize_phrase(value: str) -> str:
    parts = []
    morph = _morph_analyzer()
    for part in value.split():
        parsed = morph.parse(part)[0].normal_form
        parts.append(parsed)
    return " ".join(parts)


def _unique(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _normalize_ingredient_phrase(value: str) -> str:
    cleaned = _clean_token(value)
    if not cleaned:
        return ""
    lemmatized = _lemmatize_phrase(cleaned)
    if lemmatized in {"куриный филе", "куриный грудка", "куриный бедро"}:
        return "курица"
    return lemmatized


def _extract_list(pattern: re.Pattern[str], message: str) -> list[str]:
    values: list[str] = []
    for match in pattern.finditer(message):
        chunk = _clean_token(match.group(2 if pattern is _WITHOUT_RE else 1))
        if not chunk:
            continue
        for part in _SEPARATOR_RE.split(chunk):
            cleaned = _clean_token(part)
            if cleaned:
                values.append(_normalize_ingredient_phrase(cleaned))
    return _unique(values)


def _extract_include_ingredients(message: str) -> list[str]:
    values: list[str] = []
    for pattern in _INCLUDE_RE_LIST:
        for match in pattern.finditer(message):
            chunk = _clean_token(match.group(1))
            if not chunk:
                continue
            for part in _SEPARATOR_RE.split(chunk):
                normalized = _normalize_ingredient_phrase(part)
                if normalized and normalized not in _SERVICE_INCLUDE_TOKENS:
                    values.append(normalized)
    return _unique(values)


def extract_query_constraints(message: str) -> QueryConstraints:
    text = " ".join(message.strip().lower().split())
    if not text:
        return QueryConstraints()

    exclude_ingredients = _extract_list(_WITHOUT_RE, text)
    forbidden = _extract_list(_FORBIDDEN_RE, text)
    allergy = _extract_list(_ALLERGY_RE, text)
    include_ingredients = _extract_include_ingredients(text)

    meal_type = None
    if "завтрак" in text:
        meal_type = "breakfast"
    elif "обед" in text:
        meal_type = "lunch"
    elif "ужин" in text:
        meal_type = "dinner"
    elif "перекус" in text:
        meal_type = "snack"

    diet_goal = None
    max_calories_kcal = None
    max_fat_g = None
    max_cooking_time_minutes = None
    max_difficulty = None

    if "низкокалори" in text:
        diet_goal = "low_calorie"
        max_calories_kcal = 150.0

    if "легк" in text:
        diet_goal = "light"
        if "по калори" in text:
            max_calories_kcal = 150.0
        elif "в приготов" in text:
            max_cooking_time_minutes = 30
            max_difficulty = 2
        else:
            max_calories_kcal = 150.0
            max_fat_g = 8.0
            max_cooking_time_minutes = 30
            max_difficulty = 2

    calories_limit = _CALORIES_LIMIT_RE.search(text)
    if calories_limit:
        max_calories_kcal = float(calories_limit.group(1))

    restriction_type = None
    if allergy:
        restriction_type = "allergy_or_forbidden"
    elif forbidden:
        restriction_type = "forbidden"

    return QueryConstraints(
        include_ingredients=[
            item
            for item in include_ingredients
            if item not in {*exclude_ingredients, *forbidden, *allergy}
        ],
        exclude_ingredients=_unique([*exclude_ingredients, *forbidden]),
        allergy_exclusions=allergy,
        restriction_type=restriction_type,
        meal_type=meal_type,
        diet_goal=diet_goal,
        max_calories_kcal=max_calories_kcal,
        max_fat_g=max_fat_g,
        max_cooking_time_minutes=max_cooking_time_minutes,
        max_difficulty=max_difficulty,
    )
