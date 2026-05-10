"""
Generate data/food_helper_decision_planner_500.jsonl from the seed file plus synthetic rows.

Convention (aligned with IntentRouter):
  Phrases like «Найди рецепт без X» are labeled search_recipes with exclude_ingredients,
  not allergy_or_exclusion. allergy_or_exclusion is for allergy/medical/forbidden phrasing
  («аллергия», «нельзя глютен», «мне нельзя …») or «подбери … без …» style exclusions.

Deterministic: RNG seed 42.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED_PATH = ROOT / "data" / "food_helper_decision_planner_seed.jsonl"
DEFAULT_OUT_PATH = ROOT / "data" / "food_helper_decision_planner_500.jsonl"

INGREDIENTS = [
    "курица",
    "говядина",
    "индейка",
    "рыба",
    "тофу",
    "грибы",
    "кабачок",
    "тыква",
    "шпинат",
    "брокколи",
    "цветная капуста",
    "киноа",
    "булгур",
    "чечевица",
    "фасоль",
    "нут",
    "творог",
    "авокадо",
    "баклажан",
    "картофель",
]
DISHES = [
    "суп",
    "салат",
    "паста",
    "ризотто",
    "запеканка",
    "котлеты",
    "плов",
    "лапша",
    "пицца",
    "торт",
    "крем-суп",
    "гуляш",
]
TITLES = [
    "борщ",
    "солянка",
    "оливье",
    "цезарь с курицей",
    "греческий салат",
    "лазанья",
    "тирамису",
    "чизкейк",
    "омлет с овощами",
    "гречка с грибами",
]
EXCLUDE = ["молоко", "глютен", "сахар", "орех", "мёд", "свинина", "кунжут", "арахис", "яйцо"]
ALLERGENS = ["арахис", "глютен", "лактоза", "орех", "моллюск", "рыба", "соя"]
SUB_TARGETS = ["молоко", "сливки", "масло", "яйцо", "сахар", "мука", "дрожжи", "майонез"]

EVENT_SPECS: list[dict] = [
    {
        "event_type": "birthday",
        "guests_count": 10,
        "format": "party_table",
        "vibe": ["festive", "shareable", "beautiful"],
        "meal_roles": ["starter", "salad", "main", "dessert"],
        "preparation_style": None,
        "msg": "Меню на день рождения на {n} человек",
        "sq": "меню на день рождения",
    },
    {
        "event_type": "new_year",
        "guests_count": 8,
        "format": "party_table",
        "vibe": ["festive", "shareable", "make_ahead"],
        "meal_roles": ["starter", "salad", "main", "dessert"],
        "preparation_style": None,
        "msg": "Новогодний стол на {n} гостей",
        "sq": "новогоднее меню",
    },
    {
        "event_type": "picnic",
        "guests_count": 6,
        "format": "portable",
        "vibe": ["portable", "not_messy"],
        "meal_roles": ["snack", "starter"],
        "preparation_style": None,
        "msg": "Закуски на пикник на {n} человек",
        "sq": "закуски для пикника",
    },
    {
        "event_type": "bbq",
        "guests_count": 15,
        "format": "outdoor_grill",
        "vibe": ["shareable", "hearty"],
        "meal_roles": ["starter", "main", "side"],
        "preparation_style": None,
        "msg": "Барбекю в саду на {n} гостей",
        "sq": "меню для барбекю",
    },
    {
        "event_type": "brunch",
        "guests_count": 12,
        "format": "buffet",
        "vibe": ["light", "beautiful", "shareable"],
        "meal_roles": ["starter", "main", "dessert"],
        "preparation_style": None,
        "msg": "Бранч на {n} персон",
        "sq": "бранч меню",
    },
    {
        "event_type": "kids_party",
        "guests_count": 14,
        "format": "casual_party",
        "vibe": ["finger_food", "not_messy"],
        "meal_roles": ["snack", "main", "dessert"],
        "preparation_style": None,
        "msg": "Детский праздник, {n} детей",
        "sq": "детский праздник еда",
    },
    {
        "event_type": "corporate",
        "guests_count": 25,
        "format": "buffet",
        "vibe": ["make_ahead", "shareable"],
        "meal_roles": ["starter", "salad", "main"],
        "preparation_style": None,
        "msg": "Корпоративный фуршет на {n} человек",
        "sq": "корпоративное меню",
    },
    {
        "event_type": "halloween",
        "guests_count": 9,
        "format": "party_table",
        "vibe": ["festive", "finger_food"],
        "meal_roles": ["snack", "dessert"],
        "preparation_style": None,
        "msg": "Закуски на хэллоуин для {n} друзей",
        "sq": "хэллоуин закуски",
    },
    {
        "event_type": "easter",
        "guests_count": 7,
        "format": "family_table",
        "vibe": ["traditional", "shareable"],
        "meal_roles": ["starter", "main", "dessert"],
        "preparation_style": None,
        "msg": "Пасхальный обед на {n} человек",
        "sq": "пасхальное меню",
    },
    {
        "event_type": "graduation",
        "guests_count": 20,
        "format": "party_table",
        "vibe": ["festive", "shareable"],
        "meal_roles": ["starter", "salad", "main", "dessert"],
        "preparation_style": None,
        "msg": "Выпускной стол на {n} гостей",
        "sq": "меню на выпускной",
    },
    {
        "event_type": "baby_shower",
        "guests_count": 11,
        "format": "buffet",
        "vibe": ["light", "beautiful"],
        "meal_roles": ["starter", "dessert"],
        "preparation_style": None,
        "msg": "Сладкий стол на baby shower, {n} гостей",
        "sq": "baby shower меню",
    },
    {
        "event_type": "friends_gathering",
        "guests_count": None,
        "format": "casual_party",
        "vibe": ["shareable", "finger_food", "not_messy"],
        "meal_roles": ["snack", "starter", "main"],
        "preparation_style": None,
        "msg": "Закуски для вечера с друзьями",
        "sq": "закуски для друзей",
    },
]


def empty_constraints() -> dict:
    return {
        "dish": None,
        "include_ingredients": [],
        "exclude_ingredients": [],
        "allergy_exclusions": [],
        "dietary_preference": None,
        "restriction_type": None,
        "meal_type": None,
        "diet_goal": None,
        "max_calories_kcal": None,
        "min_protein_g": None,
        "max_fat_g": None,
        "max_cooking_time_minutes": None,
        "max_difficulty": None,
    }


def empty_entities() -> dict:
    return {}


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def patch_seed_for_router(rows: list[dict]) -> None:
    """«Найди рецепт без молока» → search_recipes (IntentRouter)."""
    for r in rows:
        if r.get("id") != "allergy_001":
            continue
        r["input"]["rule_parse"]["intent"] = "search_recipes"
        r["output"]["intent"] = "search_recipes"
        return


def list_context(rng: random.Random, *, n_results: int = 3, selected: int | None = None) -> tuple[list[dict], list[int], int | None]:
    base = 5000 + rng.randint(0, 9000)
    ids = [base + i for i in range(n_results)]
    titles = rng.sample(TITLES, min(n_results, len(TITLES)))
    while len(titles) < n_results:
        titles.append(rng.choice(TITLES))
    lines = "\n".join(f"{i + 1}. {t.title()}" for i, t in enumerate(titles))
    recent = [
        {"role": "user", "content": rng.choice(["Найди рецепты с курицей", "Покажи варианты с рыбой", "Хочу что-то с творогом"])},
        {"role": "assistant", "content": lines},
    ]
    sel = selected if selected is not None else (rng.choice(ids) if rng.random() < 0.35 else None)
    return recent, ids, sel


def make_output(
    *,
    intent: str,
    action: str,
    confidence: float = 0.93,
    search_query: str | None = None,
    constraints: dict | None = None,
    recipe_reference: dict | None = None,
    recipe_title_query: str | None = None,
    target_ingredient: str | None = None,
    nutrients: list[str] | None = None,
    event_profile: dict | None = None,
    requires_clarification: bool = False,
    clarification: dict | None = None,
) -> dict:
    c = empty_constraints()
    if constraints:
        c.update(constraints)
    return {
        "schema_version": "v1",
        "intent": intent,
        "action": action,
        "confidence": round(confidence, 2),
        "search_query": search_query,
        "constraints": c,
        "recipe_reference": recipe_reference,
        "recipe_title_query": recipe_title_query,
        "target_ingredient": target_ingredient,
        "nutrients": nutrients or [],
        "event_profile": event_profile,
        "requires_clarification": requires_clarification,
        "clarification": clarification,
    }


def rule_parse_block(
    *,
    intent: str,
    route: str,
    entities: dict | None = None,
    constraints: dict | None = None,
) -> dict:
    c = empty_constraints()
    if constraints:
        c.update(constraints)
    return {"intent": intent, "route": route, "entities": copy.deepcopy(entities) if entities else {}, "constraints": c}


def gen_search(rng: random.Random, idx: int) -> dict:
    ing = rng.choice(INGREDIENTS)
    dish = rng.choice(DISHES)
    templates = [
        ("Найди {dish} с {ing}", "{dish} с {ing}", {"dish": dish, "include_ingredients": [ing]}),
        ("Есть рецепты с {ing}?", "рецепты с {ing}", {"include_ingredients": [ing]}),
        ("Покажи что приготовить из {ing}", "блюда из {ing}", {"include_ingredients": [ing]}),
        ("Хочу {dish}, главное чтобы был {ing}", "{dish} с {ing}", {"dish": dish, "include_ingredients": [ing]}),
        ("Найди рецепт без {ex}", "рецепт", {"exclude_ingredients": [rng.choice(EXCLUDE)]}),
    ]
    msg_t, sq_t, extra = rng.choice(templates)
    ex = extra.get("exclude_ingredients")
    msg = msg_t.format(dish=dish, ing=ing, ex=ex[0] if ex else "")
    sq = sq_t.format(dish=dish, ing=ing, ex=ex[0] if ex else "")
    cons = empty_constraints()
    for k, v in extra.items():
        if k == "dish":
            cons["dish"] = v
        elif k in ("include_ingredients", "exclude_ingredients"):
            cons[k] = list(v)
    intent = "search_recipes"
    if rng.random() < 0.03:
        intent = "fallback"
    ents = {"include_ingredients": cons["include_ingredients"], "exclude_ingredients": cons["exclude_ingredients"]}
    out_intent = "recommend_recipes" if intent == "fallback" else intent
    out_action = "hybrid_search"
    conf = rng.uniform(0.88, 0.99)
    if intent == "fallback":
        conf = rng.uniform(0.72, 0.86)
    return {
        "id": f"gen_search_{idx:04d}",
        "input": {
            "message": msg,
            "recent_messages": [],
            "conversation_state": {"last_recipe_results": [], "selected_recipe_id": None, "last_event_profile": None},
            "rule_parse": rule_parse_block(
                intent=intent,
                route="no_retrieval" if intent == "fallback" else "hybrid_search",
                entities=ents,
                constraints=cons,
            ),
        },
        "output": make_output(
            intent=out_intent,
            action=out_action,
            confidence=conf,
            search_query=sq,
            constraints=cons,
        ),
    }


def gen_recommend(rng: random.Random, idx: int) -> dict:
    meal = rng.choice(["breakfast", "lunch", "dinner", "snack"])
    meal_ru = {"breakfast": "завтрак", "lunch": "обед", "dinner": "ужин", "snack": "перекус"}[meal]
    quick_mins = rng.choice([15, 20, 25, 30])
    variants = [
        (f"Подбери {meal_ru}", meal_ru, {}),
        (f"Лёгкий {meal_ru}, низкокалорийный", meal_ru, {"diet_goal": "low_calorie", "max_calories_kcal": float(rng.choice([300, 350, 400]))}),
        (f"После тренировки {meal_ru}", f"{meal_ru} после тренировки", {"diet_goal": "high_protein", "min_protein_g": 20.0}),
        (
            f"Быстрый {meal_ru} до {quick_mins} минут",
            f"быстрый {meal_ru}",
            {"max_cooking_time_minutes": quick_mins, "max_difficulty": 2},
        ),
    ]
    msg, sq, extra = rng.choice(variants)
    cons = empty_constraints()
    cons["meal_type"] = meal
    cons.update(extra)
    if rng.random() < 0.12:
        recent, ids, sel = list_context(rng)
        msg = rng.choice(["Продолжим: подбери ещё вариант", "А что-то другое на тот же приём пищи?"])
        cons["meal_type"] = meal
    else:
        recent, ids, sel = [], [], None
    return {
        "id": f"gen_recommend_{idx:04d}",
        "input": {
            "message": msg,
            "recent_messages": recent,
            "conversation_state": {
                "last_recipe_results": ids,
                "selected_recipe_id": sel,
                "last_event_profile": None,
            },
            "rule_parse": rule_parse_block(
                intent="recommend_recipes",
                route="hybrid_search",
                constraints=cons,
            ),
        },
        "output": make_output(
            intent="recommend_recipes",
            action="hybrid_search",
            confidence=rng.uniform(0.9, 0.99),
            search_query=sq,
            constraints=cons,
        ),
    }


def gen_allergy(rng: random.Random, idx: int) -> dict:
    choice = rng.randint(0, 2)
    if choice == 0:
        ag = rng.choice(ALLERGENS)
        msg = f"У меня аллергия на {ag}, что можно на ужин?"
        cons = empty_constraints()
        cons["meal_type"] = "dinner"
        cons["allergy_exclusions"] = [ag]
        cons["restriction_type"] = "allergy_or_forbidden"
        ents: dict = {}
        sq = f"ужин без {ag}"
    elif choice == 1:
        msg = f"Подбери завтрак без {rng.choice(EXCLUDE)} и без {rng.choice(EXCLUDE)}"
        ex = list(dict.fromkeys([rng.choice(EXCLUDE), rng.choice(EXCLUDE)]))
        cons = empty_constraints()
        cons["meal_type"] = "breakfast"
        cons["exclude_ingredients"] = ex
        ents = {"exclude_ingredients": ex}
        sq = "завтрак"
    else:
        msg = f"Мне нельзя {rng.choice(ALLERGENS)}, найди суп"
        ag = rng.choice(ALLERGENS)
        cons = empty_constraints()
        cons["dish"] = "суп"
        cons["allergy_exclusions"] = [ag]
        cons["restriction_type"] = "allergy_or_forbidden"
        ents = {}
        sq = "суп"
    return {
        "id": f"gen_allergy_{idx:04d}",
        "input": {
            "message": msg,
            "recent_messages": [],
            "conversation_state": {"last_recipe_results": [], "selected_recipe_id": None, "last_event_profile": None},
            "rule_parse": rule_parse_block(
                intent="allergy_or_exclusion",
                route="hybrid_search",
                entities=ents,
                constraints=cons,
            ),
        },
        "output": make_output(
            intent="allergy_or_exclusion",
            action="hybrid_search",
            confidence=rng.uniform(0.94, 0.99),
            search_query=sq,
            constraints=cons,
        ),
    }


def gen_details(rng: random.Random, idx: int) -> dict:
    if rng.random() < 0.55:
        recent, ids, sel = list_context(rng)
        rank = rng.choice([1, 2, 3])
        ordinals = {1: "первый", 2: "второй", 3: "третий"}
        msg = rng.choice(
            [
                f"Покажи {ordinals[rank]} рецепт",
                f"Как готовить {ordinals[rank]}?",
                f"Ингредиенты {ordinals[rank]} варианта",
            ]
        )
        ref = {"type": "rank", "value": rank}
        ents = {"recipe_reference": ref}
        st = {"last_recipe_results": ids, "selected_recipe_id": sel, "last_event_profile": None}
    else:
        title = rng.choice(TITLES)
        msg = rng.choice(
            [
                f"Какие ингредиенты нужны для {title}?",
                f"Покажи рецепт {title}",
                f"Расскажи подробнее про {title}",
            ]
        )
        recent = []
        ents = {"recipe_title_query": title}
        ref = {"type": "title", "value": title}
        st = {"last_recipe_results": [], "selected_recipe_id": None, "last_event_profile": None}
    cons = empty_constraints()
    return {
        "id": f"gen_details_{idx:04d}",
        "input": {
            "message": msg,
            "recent_messages": recent,
            "conversation_state": st,
            "rule_parse": rule_parse_block(
                intent="recipe_details",
                route="conversation_recipe_fetch",
                entities=ents,
                constraints=cons,
            ),
        },
        "output": make_output(
            intent="recipe_details",
            action="recipe_details",
            confidence=rng.uniform(0.91, 0.98),
            constraints=cons,
            recipe_reference=ref,
            recipe_title_query=ents.get("recipe_title_query"),
        ),
    }


def gen_nutrition(rng: random.Random, idx: int) -> dict:
    nutr_key = rng.choice(["calories", "protein", "fat", "carbs", "bju"])
    ru = {"calories": "калорий", "protein": "белка", "fat": "жиров", "carbs": "углеводов", "bju": "БЖУ"}[nutr_key]
    cons = empty_constraints()
    if rng.random() < 0.5:
        recent, ids, sel = list_context(rng)
        rank = rng.choice([1, 2, 3])
        msg = f"Сколько {ru} в {['первом', 'втором', 'третьем'][rank - 1]} рецепте?"
        ref = {"type": "rank", "value": rank}
        ents = {"recipe_reference": ref, "nutrient": nutr_key if nutr_key != "bju" else "bju", "nutrients": [nutr_key]}
        nlist = ["bju"] if nutr_key == "bju" else [nutr_key]
    else:
        recent = []
        title = rng.choice(TITLES)
        msg = f"Сколько {ru} в {title}?"
        ref = {"type": "title", "value": title}
        ents = {"recipe_title_query": title, "nutrient": nutr_key, "nutrients": [nutr_key]}
        nlist = ["bju"] if nutr_key == "bju" else [nutr_key]
        ids, sel = [], None
    return {
        "id": f"gen_nutrition_{idx:04d}",
        "input": {
            "message": msg,
            "recent_messages": recent,
            "conversation_state": {"last_recipe_results": ids, "selected_recipe_id": sel, "last_event_profile": None},
            "rule_parse": rule_parse_block(
                intent="nutrition_question",
                route="sql",
                entities=ents,
                constraints=cons,
            ),
        },
        "output": make_output(
            intent="nutrition_question",
            action="nutrition_lookup",
            confidence=rng.uniform(0.9, 0.99),
            search_query=ents.get("recipe_title_query"),
            constraints=cons,
            recipe_reference=ref,
            recipe_title_query=ents.get("recipe_title_query"),
            nutrients=nlist,
        ),
    }


def gen_sub_ing(rng: random.Random, idx: int) -> dict:
    tgt = rng.choice(SUB_TARGETS)
    if rng.random() < 0.45:
        recent, ids, sel = list_context(rng)
        rank = rng.choice([1, 2, 3])
        msg = rng.choice(
            [
                f"Чем заменить {tgt} в {rank}-м рецепте?",
                f"На что поменять {tgt} во втором?",
            ]
        )
        if "втором" in msg:
            rank = 2
        ref = {"type": "rank", "value": rank}
        ents = {"recipe_reference": ref, "target_ingredient": tgt}
        st = {"last_recipe_results": ids, "selected_recipe_id": sel, "last_event_profile": None}
    else:
        title = rng.choice(TITLES)
        msg = f"Замени {tgt} в рецепте {title}"
        ref = {"type": "title", "value": title}
        ents = {"recipe_title_query": title, "target_ingredient": tgt}
        recent = []
        st = {"last_recipe_results": [], "selected_recipe_id": None, "last_event_profile": None}
    cons = empty_constraints()
    return {
        "id": f"gen_sub_ing_{idx:04d}",
        "input": {
            "message": msg,
            "recent_messages": recent,
            "conversation_state": st,
            "rule_parse": rule_parse_block(
                intent="ingredient_substitution",
                route="substitution",
                entities=ents,
                constraints=cons,
            ),
        },
        "output": make_output(
            intent="ingredient_substitution",
            action="recipe_substitution",
            confidence=rng.uniform(0.91, 0.99),
            search_query=ents.get("recipe_title_query"),
            constraints=cons,
            recipe_reference=ref,
            recipe_title_query=ents.get("recipe_title_query"),
            target_ingredient=tgt,
        ),
    }


def gen_sub_gen(rng: random.Random, idx: int) -> dict:
    tgt = rng.choice(SUB_TARGETS)
    msg = rng.choice(
        [
            f"Чем заменить {tgt}?",
            f"Нужна замена {tgt} в выпечке",
            f"Вместо {tgt} что можно?",
        ]
    )
    cons = empty_constraints()
    if "выпечк" in msg:
        cons["dish"] = "выпечка"
    return {
        "id": f"gen_sub_gen_{idx:04d}",
        "input": {
            "message": msg,
            "recent_messages": [],
            "conversation_state": {"last_recipe_results": [], "selected_recipe_id": None, "last_event_profile": None},
            "rule_parse": rule_parse_block(
                intent="general_substitution",
                route="substitution_catalog",
                entities={"target_ingredient": tgt},
                constraints=cons,
            ),
        },
        "output": make_output(
            intent="general_substitution",
            action="general_substitution",
            confidence=rng.uniform(0.9, 0.97),
            constraints=cons,
            target_ingredient=tgt,
        ),
    }


def gen_similar(rng: random.Random, idx: int) -> dict:
    ex = rng.choice([[], ["молоко"], ["сыр"], ["орех"]])
    ids: list[int] = []
    sel: int | None = None
    recent: list[dict] = []
    if rng.random() < 0.55:
        recent, ids, sel = list_context(rng)
        rank = 1
        msg = rng.choice(["Покажи похожие на первый", "Есть аналоги второго?", "Подбери похожее на третий"])
        if "втор" in msg:
            rank = 2
        if "трет" in msg:
            rank = 3
        ref = {"type": "rank", "value": rank}
        ents = {"recipe_reference": ref}
        if ex:
            ents["exclude_ingredients"] = ex
    else:
        title = rng.choice(TITLES)
        msg = f"Альтернатива блюду {title}"
        ref = {"type": "title", "value": title}
        ents = {"recipe_title_query": title}
    cons = empty_constraints()
    if ex:
        cons["exclude_ingredients"] = list(ex)
    return {
        "id": f"gen_similar_{idx:04d}",
        "input": {
            "message": msg,
            "recent_messages": recent,
            "conversation_state": {
                "last_recipe_results": ids,
                "selected_recipe_id": sel,
                "last_event_profile": None,
            },
            "rule_parse": rule_parse_block(
                intent="similar_recipes",
                route="vector_search",
                entities=ents,
                constraints=cons,
            ),
        },
        "output": make_output(
            intent="similar_recipes",
            action="similar_recipes",
            confidence=rng.uniform(0.86, 0.98),
            search_query=ents.get("recipe_title_query"),
            constraints=cons,
            recipe_reference=ref,
            recipe_title_query=ents.get("recipe_title_query"),
        ),
    }


def gen_event(rng: random.Random, idx: int) -> dict:
    spec = rng.choice(EVENT_SPECS)
    n = spec["guests_count"]
    msg = spec["msg"].format(n=n if n is not None else rng.randint(4, 20))
    if rng.random() < 0.35 and n:
        msg += rng.choice([", без рыбы", ", вегетарианское", ""])
    prof = {
        "event_type": spec["event_type"],
        "guests_count": n,
        "format": spec["format"],
        "vibe": list(spec["vibe"]),
        "meal_roles": list(spec["meal_roles"]),
        "preparation_style": spec["preparation_style"],
    }
    cons = empty_constraints()
    if "без рыбы" in msg:
        cons["exclude_ingredients"] = ["рыба"]
    if "вегетариан" in msg:
        cons["dietary_preference"] = "vegetarian"
    ents = {"event_profile": prof}
    return {
        "id": f"gen_event_{idx:04d}",
        "input": {
            "message": msg,
            "recent_messages": [],
            "conversation_state": {"last_recipe_results": [], "selected_recipe_id": None, "last_event_profile": None},
            "rule_parse": rule_parse_block(
                intent="event_recommendation",
                route="event_menu_recommendation",
                entities=ents,
                constraints=cons,
            ),
        },
        "output": make_output(
            intent="event_recommendation",
            action="event_menu_recommendation",
            confidence=rng.uniform(0.87, 0.99),
            search_query=spec["sq"],
            constraints=cons,
            event_profile=prof,
        ),
    }


def gen_recall(rng: random.Random, idx: int) -> dict:
    recent, ids, sel = list_context(rng)
    msg = rng.choice(
        [
            "Что мы искали до этого?",
            "О чём мы говорили?",
            "Напомни контекст",
        ]
    )
    cons = empty_constraints()
    return {
        "id": f"gen_recall_{idx:04d}",
        "input": {
            "message": msg,
            "recent_messages": recent,
            "conversation_state": {"last_recipe_results": ids, "selected_recipe_id": sel, "last_event_profile": None},
            "rule_parse": rule_parse_block(intent="conversation_recall", route="conversation_history", constraints=cons),
        },
        "output": make_output(
            intent="conversation_recall",
            action="conversation_recall",
            confidence=rng.uniform(0.97, 0.995),
            constraints=cons,
        ),
    }


def gen_fallback(rng: random.Random, idx: int) -> dict:
    msg = rng.choice(
        [
            "Привет!",
            "Как настроение?",
            "Расскажи анекдот",
            "Курс доллара какой?",
            "Напиши код на Python",
        ]
    )
    cons = empty_constraints()
    return {
        "id": f"gen_fallback_{idx:04d}",
        "input": {
            "message": msg,
            "recent_messages": [],
            "conversation_state": {"last_recipe_results": [], "selected_recipe_id": None, "last_event_profile": None},
            "rule_parse": rule_parse_block(intent="fallback", route="no_retrieval", constraints=cons),
        },
        "output": make_output(
            intent="fallback",
            action="fallback",
            confidence=rng.uniform(0.85, 0.99),
            constraints=cons,
        ),
    }


def gen_clarify(rng: random.Random, idx: int) -> dict:
    kind = rng.choice(["light", "healthy", "event_guests", "fat_ambiguous"])
    cons = empty_constraints()
    if kind == "light":
        msg = rng.choice(["Подбери лёгкий обед", "Хочу лёгкий перекус"])
        cons["meal_type"] = rng.choice(["lunch", "snack"])
        intent = "recommend_recipes"
        clar = {
            "reason": "ambiguous_light_goal",
            "question": "Под «лёгким» вы имеете в виду низкокалорийное или быстрое в приготовлении?",
            "expected_fields": ["diet_goal"],
            "options": ["низкокалорийное", "быстрое", "и то и другое"],
        }
        sq = "лёгкий приём пищи"
    elif kind == "healthy":
        msg = "Хочу что-нибудь полезное на ужин"
        cons["meal_type"] = "dinner"
        intent = "recommend_recipes"
        clar = {
            "reason": "ambiguous_healthy_goal",
            "question": "Что важнее: меньше калорий, больше белка или больше овощей?",
            "expected_fields": ["diet_goal"],
            "options": ["меньше калорий", "больше белка", "больше овощей"],
        }
        sq = "полезный ужин"
    elif kind == "event_guests":
        msg = "Собери меню на праздник"
        intent = "event_recommendation"
        clar = {
            "reason": "ambiguous_event",
            "question": "На какой праздник и на сколько гостей?",
            "expected_fields": ["event_profile"],
            "options": ["день рождения", "новый год", "корпоратив"],
        }
        sq = "праздничное меню"
    else:
        msg = "Нужно сытно, но без жира"
        intent = "recommend_recipes"
        clar = {
            "reason": "ambiguous_satiety_fat",
            "question": "Ограничиваем только жиры или ещё и калории?",
            "expected_fields": ["diet_goal", "max_calories_kcal"],
            "options": ["только жиры", "жиры и калории", "не знаю"],
        }
        sq = "сытно низкожирное"
    return {
        "id": f"gen_clarify_{idx:04d}",
        "input": {
            "message": msg,
            "recent_messages": [],
            "conversation_state": {"last_recipe_results": [], "selected_recipe_id": None, "last_event_profile": None},
            "rule_parse": rule_parse_block(
                intent=intent,
                route="hybrid_search" if intent == "recommend_recipes" else "event_menu_recommendation",
                constraints=cons,
            ),
        },
        "output": make_output(
            intent=intent,
            action="clarification",
            confidence=rng.uniform(0.68, 0.84),
            search_query=sq,
            constraints=empty_constraints() if kind != "light" else {**empty_constraints(), "meal_type": cons["meal_type"]},
            requires_clarification=True,
            clarification=clar,
        ),
    }


def gen_clarify_resolve(rng: random.Random, idx: int) -> dict:
    """Follow-up after assistant asked to disambiguate «лёгкий»."""
    opt = rng.choice(["низкокалорийное", "быстрое", "и то и другое"])
    recent = [
        {"role": "user", "content": "Подбери лёгкий завтрак"},
        {
            "role": "assistant",
            "content": "Под «лёгким» вы имеете в виду низкокалорийный или простой в приготовлении?",
        },
    ]
    cons = empty_constraints()
    cons["meal_type"] = "breakfast"
    if opt == "низкокалорийное":
        cons["diet_goal"] = "light_calories"
        cons["max_calories_kcal"] = 320.0
    elif opt == "быстрое":
        cons["diet_goal"] = "easy"
        cons["max_cooking_time_minutes"] = 20
        cons["max_difficulty"] = 2
    else:
        cons["diet_goal"] = "light_mixed"
        cons["max_calories_kcal"] = 380.0
        cons["max_cooking_time_minutes"] = 25
        cons["max_difficulty"] = 2
    return {
        "id": f"gen_resolve_{idx:04d}",
        "input": {
            "message": opt,
            "recent_messages": recent,
            "conversation_state": {"last_recipe_results": [], "selected_recipe_id": None, "last_event_profile": None},
            "rule_parse": rule_parse_block(intent="fallback", route="no_retrieval", constraints=empty_constraints()),
        },
        "output": make_output(
            intent="recommend_recipes",
            action="hybrid_search",
            confidence=0.99,
            search_query="лёгкий завтрак",
            constraints=cons,
        ),
    }


def gen_mismatch_rule_output(rng: random.Random, idx: int) -> dict:
    """~10% of synthetic: rule_parse fallback, output refined (plan drift examples)."""
    ing = rng.choice(INGREDIENTS)
    msg = f"Что-то сытное с {ing}"
    cons = empty_constraints()
    cons["include_ingredients"] = [ing]
    cons["diet_goal"] = "satisfying"
    cons["max_fat_g"] = 15.0
    return {
        "id": f"gen_drift_{idx:04d}",
        "input": {
            "message": msg,
            "recent_messages": [],
            "conversation_state": {"last_recipe_results": [], "selected_recipe_id": None, "last_event_profile": None},
            "rule_parse": rule_parse_block(intent="fallback", route="no_retrieval", constraints=empty_constraints()),
        },
        "output": make_output(
            intent="recommend_recipes",
            action="hybrid_search",
            confidence=rng.uniform(0.82, 0.9),
            search_query=f"сытное блюдо с {ing}",
            constraints=cons,
        ),
    }


def build_synthetic(rng: random.Random, n: int) -> list[dict]:
    """Build exactly n rows with quota-like distribution (output intents)."""
    weights: list[tuple[str, object]] = (
        [("search", gen_search)] * 90
        + [("recommend", gen_recommend)] * 72
        + [("allergy", gen_allergy)] * 36
        + [("details", gen_details)] * 34
        + [("nutrition", gen_nutrition)] * 32
        + [("sub_ing", gen_sub_ing)] * 20
        + [("sub_gen", gen_sub_gen)] * 17
        + [("similar", gen_similar)] * 33
        + [("event", gen_event)] * 36
        + [("recall", gen_recall)] * 11
        + [("fallback", gen_fallback)] * 16
        + [("clarify", gen_clarify)] * 26
        + [("resolve", gen_clarify_resolve)] * 18
    )
    if len(weights) != n:
        raise ValueError(f"internal: weight sum {len(weights)} != n {n}")
    rng.shuffle(weights)
    out: list[dict] = []
    drift_budget = max(1, int(round(n * 0.1)))
    drift_used = 0
    for idx, (name, fn) in enumerate(weights, start=1):
        if drift_used < drift_budget and rng.random() < 0.1:
            row = gen_mismatch_rule_output(rng, idx)
            drift_used += 1
        else:
            row = fn(rng, idx)
        out.append(row)
    rng.shuffle(out)
    return out


def compare_router_sample(rows: list[dict], n: int, rng: random.Random) -> None:
    from app.orchestrator.intent_router import IntentRouter

    router = IntentRouter()
    picked = [r for r in rows if not r["input"].get("recent_messages")]
    rng.shuffle(picked)
    picked = picked[:n]
    mism = 0
    for r in picked:
        msg = r["input"]["message"]
        d = router.decide(msg)
        gold_intent = r["output"]["intent"]
        if r["output"].get("requires_clarification"):
            continue
        if gold_intent == "ingredient_substitution" and d.intent == "general_substitution":
            mism += 1
            continue
        if d.intent != gold_intent:
            mism += 1
            print(f"mismatch msg={msg!r} gold={gold_intent} router={d.intent}")
    print(f"Router sample: checked {len(picked)}, mismatches {mism}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-path", type=Path, default=DEFAULT_SEED_PATH)
    ap.add_argument("--out-path", type=Path, default=DEFAULT_OUT_PATH)
    ap.add_argument("--rng-seed", type=int, default=42)
    ap.add_argument("--compare-router", type=int, default=0, help="Sample N single-turn rows vs IntentRouter")
    args = ap.parse_args()

    rng = random.Random(args.rng_seed)
    seed_rows = load_jsonl(args.seed_path)
    patch_seed_for_router(seed_rows)

    n_syn = 500 - len(seed_rows)
    if n_syn < 0:
        raise SystemExit("Seed has more than 500 rows")
    synthetic = build_synthetic(rng, n_syn)
    all_rows = seed_rows + synthetic

    ids = [r["id"] for r in all_rows]
    if len(ids) != len(set(ids)):
        seen: set[str] = set()
        for r in all_rows:
            if r["id"] in seen:
                r["id"] = r["id"] + "_dupfix_" + str(rng.randint(1000, 9999))
            seen.add(r["id"])

    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    with args.out_path.open("w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Wrote {len(all_rows)} rows to {args.out_path}")
    ci = Counter(r["output"]["intent"] for r in all_rows)
    ca = Counter(r["output"]["action"] for r in all_rows)
    print("intent counts:", dict(sorted(ci.items())))
    print("action counts:", dict(sorted(ca.items())))

    if args.compare_router:
        import sys

        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        compare_router_sample(all_rows, args.compare_router, rng)


if __name__ == "__main__":
    main()
