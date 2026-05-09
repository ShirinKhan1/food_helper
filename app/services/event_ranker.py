from __future__ import annotations

import re
from typing import Any

from app.schemas.event import EventProfile
from app.schemas.search import QueryConstraints
from app.services.event_profiles import EVENT_PROFILES

_DIFFICULTY_RE = re.compile(r"(\d)\s*из\s*5")

W_ROLE = 0.25
W_TAG = 0.20
W_SERV = 0.15
W_PRAC = 0.15
W_DIFF = 0.10
W_ING = 0.10
W_NUT = 0.05

TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "festive": ("икра", "лосось", "семг", "утк", "индейк", "шампан", "оливье", "форел"),
    "romantic": ("паста", "ризотто", "лосось", "кревет", "шоколад", "клубник", "сырник", "тирамису"),
    "shareable": ("запеканк", "плов", "лазань", "гнезды", "пицц", "больш", "порц"),
    "finger_food": ("канапе", "тарталетк", "рулет", "ролл", "мини-", "шашлычк", "крокет"),
    "make_ahead": ("холодильник", "охлад", "накануне", "заранее", "настоять", "марин"),
    "serve_cold": ("холодн", "охлад", "сервировк холод", "закуска холод"),
    "serve_hot": ("горяч", "сразу подав", "подавайте сразу", "разогрет"),
    "portable": ("бутерброд", "сэндвич", "перекус", "контейнер", "завернуть"),
    "light": ("салат", "суп", "крем-", "йогурт", "фрукт"),
    "easy": (),
    "beautiful": ("украс", "украсьте", "слоями", "подач", "формочк"),
    "not_messy": (),
    "comfort": ("запеканк", "пюре", "жаркое", "тушён", "котлет"),
    "home_style": ("домашн", "семейн", "простой рецепт"),
    "casual_party": ("закуск", "соус", "дип", "начос", "крылышк"),
    "fun": ("печень", "кекс", "кекса", "шоколад", "маршмеллоу"),
}

ROLE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("salad", ("салат",)),
    ("soup", ("суп", "борщ", "солянк", "бульон")),
    ("dessert", ("десерт", "торт", "пирог", "пирожн", "мусс", "кекс", "печень", "морож", "варень")),
    ("sauce", ("соус", "дип", "заправк")),
    ("starter", ("закуск", "канапе", "тарталет", "брускетт", "рулет")),
    ("snack", ("перекус", "бутерброд", "сендвич", "фингер")),
    ("side", ("гарнир", "гарниры", "картофельн", "круп")),
    ("main", ("горяч", "запек", "котлет", "мясо", "куриц", "рыба", "паста", "ризотто", "гуляш", "жаркое")),
]

INGREDIENT_BONUS: dict[str, tuple[str, ...]] = {
    "new_year": ("лосось", "икра", "сыр", "кревет", "утк", "индейк", "шоколад", "ягод", "оливье"),
    "date_night": ("паста", "рыба", "кревет", "сыр", "шоколад", "ягод", "лосось"),
    "friends_gathering": ("куриц", "сыр", "лаваш", "тесто", "фарш", "картофел", "соус"),
    "birthday": ("торт", "крем", "шоколад", "ягод", "мусс"),
    "family_dinner": ("картофел", "мясо", "куриц", "рыба", "суп"),
    "picnic": ("бутерброд", "лаваш", "сыр", "колбас", "овощ", "фрукт"),
    "kids_party": ("котлет", "картофел", "макарон", "печень", "пирож", "кекс"),
    "generic_event": (),
}


def _row_text_blob(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("title") or ""),
        str(row.get("description") or ""),
        str(row.get("category") or ""),
        str(row.get("subcategory") or ""),
    ]
    ing = row.get("ingredients")
    if isinstance(ing, list):
        for item in ing:
            if isinstance(item, dict):
                parts.append(str(item.get("name") or ""))
            else:
                parts.append(str(item))
    elif isinstance(ing, str):
        parts.append(ing)
    steps = row.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict):
                parts.append(str(step.get("text") or ""))
            elif isinstance(step, str):
                parts.append(step)
    return " ".join(parts).lower()


def _parse_difficulty(props: dict[str, Any] | None) -> int | None:
    if not isinstance(props, dict):
        return None
    raw = props.get("Сложность")
    if not raw:
        return None
    match = _DIFFICULTY_RE.search(str(raw))
    return int(match.group(1)) if match else None


def infer_recipe_tags(row: dict[str, Any]) -> set[str]:
    text = _row_text_blob(row)
    tags: set[str] = set()
    for tag, kws in TAG_KEYWORDS.items():
        if not kws:
            continue
        if any(k in text for k in kws):
            tags.add(tag)
    props = row.get("properties") or {}
    diff = _parse_difficulty(props if isinstance(props, dict) else None)
    if diff is not None and diff <= 2:
        tags.add("easy")
    steps = row.get("steps")
    n_steps = len(steps) if isinstance(steps, list) else 0
    ingredients = row.get("ingredients")
    n_ing = len(ingredients) if isinstance(ingredients, list) else 0
    if n_steps and n_steps <= 6 and n_ing <= 10:
        tags.add("not_messy")
    return tags


def infer_recipe_roles(row: dict[str, Any]) -> list[str]:
    text = _row_text_blob(row)
    roles: list[str] = []
    for role, kws in ROLE_RULES:
        if any(k in text for k in kws):
            roles.append(role)
    if not roles:
        cat = f"{row.get('category') or ''} {row.get('subcategory') or ''}".lower()
        for role, kws in ROLE_RULES:
            if any(k in cat for k in kws):
                roles.append(role)
    if not roles:
        roles = ["main"]
    return roles


def _servings_score(row: dict[str, Any], guests: int | None) -> float:
    if guests is None:
        return 0.55
    servings = row.get("servings")
    if servings is None:
        return 0.35
    try:
        s = float(servings)
    except (TypeError, ValueError):
        return 0.35
    if s >= guests:
        return 1.0
    if s >= guests * 0.6:
        return 0.65
    return 0.25


def _role_score(roles: list[str], meal_roles: list[str]) -> float:
    if not meal_roles:
        return 0.5
    overlap = set(roles) & set(meal_roles)
    if overlap:
        return 0.85 + 0.15 * min(len(overlap) / len(meal_roles), 1.0)
    return 0.2


def _tag_score(tags: set[str], vibe: list[str]) -> float:
    if not vibe:
        return 0.5
    pref = set(vibe)
    hit = tags & pref
    if not hit:
        return 0.25
    return min(0.4 + 0.6 * (len(hit) / len(pref)), 1.0)


def _practicality_score(tags: set[str], vibe: list[str]) -> float:
    if not vibe:
        return 0.5
    score = 0.4
    for v in vibe:
        if v in tags:
            score += 0.15
    return min(score, 1.0)


def _difficulty_score(row: dict[str, Any], event_type: str | None) -> float:
    props = row.get("properties") or {}
    diff = _parse_difficulty(props if isinstance(props, dict) else None)
    max_d = 5
    if event_type and event_type in EVENT_PROFILES:
        max_d = int(EVENT_PROFILES[event_type].get("max_difficulty") or 5)
    if diff is None:
        return 0.5
    if diff <= max_d:
        return 0.75 + (max_d - diff) * 0.05
    return max(0.15, 0.5 - (diff - max_d) * 0.15)


def _ingredient_bonus_score(row: dict[str, Any], event_type: str | None) -> float:
    et = event_type or "generic_event"
    kws = INGREDIENT_BONUS.get(et) or ()
    if not kws:
        return 0.5
    text = _row_text_blob(row)
    hits = sum(1 for k in kws if k in text)
    return min(0.35 + 0.2 * hits, 1.0)


def _nutrition_score(row: dict[str, Any], constraints: QueryConstraints) -> float:
    light = bool(
        constraints.max_calories_kcal is not None
        or constraints.max_fat_g is not None
        or (constraints.diet_goal and any(x in str(constraints.diet_goal).lower() for x in ("легк", "пп", "низкокалор")))
    )
    if not light:
        return 0.5
    cal = row.get("calories_kcal")
    fat = row.get("fat_g")
    score = 0.5
    try:
        if cal is not None and float(cal) <= 200:
            score += 0.2
        if fat is not None and float(fat) <= 12:
            score += 0.2
    except (TypeError, ValueError):
        pass
    return min(score, 1.0)


def _build_reasons(tags: set[str], roles: list[str], guests: int | None) -> list[str]:
    reasons: list[str] = []
    if "shareable" in tags:
        reasons.append("удобно подать на общий стол")
    if "starter" in roles or "snack" in roles:
        reasons.append("можно подать как закуску")
    if "make_ahead" in tags:
        reasons.append("можно частично приготовить заранее")
    if guests and "festive" in tags:
        reasons.append("подходит для праздничного формата")
    if "romantic" in tags:
        reasons.append("подходит для романтического ужина")
    if "finger_food" in tags:
        reasons.append("удобно есть компанией")
    if not reasons:
        reasons.append("похоже на уместный вариант под запрос")
    return reasons[:6]


def _build_penalties(row: dict[str, Any]) -> list[str]:
    pen: list[str] = []
    if row.get("servings") is None:
        pen.append("нет точных данных по порциям в базе")
    props = row.get("properties") or {}
    if isinstance(props, dict) and not props.get("Сложность"):
        pen.append("нет данных по сложности")
    return pen


class EventRanker:
    def rank(
        self,
        *,
        rows: list[dict[str, Any]],
        event_profile: EventProfile,
        constraints: QueryConstraints,
        top_k: int,
    ) -> list[dict[str, Any]]:
        _ = top_k
        out: list[dict[str, Any]] = []
        for row in rows:
            r = dict(row)
            tags = infer_recipe_tags(r)
            roles = infer_recipe_roles(r)
            rs = _role_score(roles, event_profile.meal_roles)
            ts = _tag_score(tags, event_profile.vibe)
            ss = _servings_score(r, event_profile.guests_count)
            ps = _practicality_score(tags, event_profile.vibe)
            ds = _difficulty_score(r, event_profile.event_type)
            ins = _ingredient_bonus_score(r, event_profile.event_type)
            ns = _nutrition_score(r, constraints)
            event_score = (
                W_ROLE * rs
                + W_TAG * ts
                + W_SERV * ss
                + W_PRAC * ps
                + W_DIFF * ds
                + W_ING * ins
                + W_NUT * ns
            )
            r["event_score"] = round(event_score, 4)
            r["event_reasons"] = _build_reasons(tags, roles, event_profile.guests_count)
            r["event_penalties"] = _build_penalties(r)
            r["event_roles"] = roles
            r["event_tags"] = sorted(tags)
            out.append(r)
        out.sort(key=lambda x: (-float(x.get("event_score") or 0.0), int(x.get("id") or 0)))
        return out
