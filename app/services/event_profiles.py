from __future__ import annotations

from typing import Any, TypedDict


class EventProfileDict(TypedDict, total=False):
    keywords: list[str]
    default_roles: list[str]
    preferred_tags: list[str]
    format: str
    max_difficulty: int


EVENT_PROFILES: dict[str, EventProfileDict] = {
    "new_year": {
        "keywords": [
            "новый год",
            "новогодн",
            "праздник",
            "праздничный стол",
            "застолье",
            "31 декабр",
        ],
        "default_roles": ["starter", "salad", "main", "dessert"],
        "preferred_tags": ["festive", "shareable", "make_ahead"],
        "format": "home_party",
        "max_difficulty": 4,
    },
    "date_night": {
        "keywords": [
            "свидание",
            "свидания",
            "свиданию",
            "романтический ужин",
            "романтический вечер",
            "для девушки",
            "для парня",
            "романтич",
        ],
        "default_roles": ["main", "dessert"],
        "preferred_tags": ["romantic", "light", "beautiful", "not_messy"],
        "format": "date_night",
        "max_difficulty": 3,
    },
    "friends_gathering": {
        "keywords": [
            "друзья",
            "с друзьями",
            "посиделки",
            "вечеринк",
            "собраться",
            "компани",
            "придут вечером",
            "гости вечером",
        ],
        "default_roles": ["starter", "snack", "main"],
        "preferred_tags": ["shareable", "finger_food", "casual_party", "easy"],
        "format": "home_party",
        "max_difficulty": 3,
    },
    "birthday": {
        "keywords": [
            "день рождения",
            "праздник рождения",
            "юбилей",
            "именины",
        ],
        "default_roles": ["starter", "salad", "main", "dessert"],
        "preferred_tags": ["festive", "shareable", "beautiful"],
        "format": "home_party",
        "max_difficulty": 4,
    },
    "family_dinner": {
        "keywords": [
            "семейный ужин",
            "для семьи",
            "родители придут",
            "семейный обед",
            "семье на ужин",
        ],
        "default_roles": ["main", "side", "dessert"],
        "preferred_tags": ["home_style", "comfort", "shareable"],
        "format": "family_dinner",
        "max_difficulty": 3,
    },
    "picnic": {
        "keywords": [
            "пикник",
            "на природу",
            "на дачу",
            "в дорогу",
            "на природе",
        ],
        "default_roles": ["snack", "main", "dessert"],
        "preferred_tags": ["portable", "serve_cold", "finger_food"],
        "format": "picnic",
        "max_difficulty": 3,
    },
    "kids_party": {
        "keywords": [
            "детский праздник",
            "для детей",
            "детям",
            "детский день рождения",
            "в садик",
            "детская вечеринка",
            "школьный праздник",
        ],
        "default_roles": ["snack", "main", "dessert"],
        "preferred_tags": ["easy", "finger_food", "fun", "shareable"],
        "format": "home_party",
        "max_difficulty": 3,
    },
}

EVENT_TYPE_ORDER: tuple[str, ...] = (
    "new_year",
    "date_night",
    "friends_gathering",
    "birthday",
    "family_dinner",
    "picnic",
    "kids_party",
)

ALLOWED_EVENT_TYPES: frozenset[str] = frozenset([*EVENT_TYPE_ORDER, "generic_event"])

EVENT_SEARCH_BOOST: dict[str, str] = {
    "new_year": "праздничный стол закуска салат горячее десерт новый год",
    "date_night": "романтический ужин легкое основное десерт красивое блюдо",
    "friends_gathering": "закуски для компании вечеринка сытное блюдо finger food",
    "birthday": "праздничное меню закуска салат торт десерт день рождения",
    "family_dinner": "семейный ужин домашнее горячее гарнир десерт",
    "picnic": "перекус в дорогу холодные закуски удобно взять с собой",
    "kids_party": "простые блюда детский стол закуски сладкое",
    "generic_event": "меню блюда подбор",
}

ROLE_TITLES_RU: dict[str, str] = {
    "starter": "Закуски",
    "salad": "Салаты",
    "main": "Горячее",
    "dessert": "Десерты",
    "snack": "Закуски и перекус",
    "side": "Гарниры",
    "sauce": "Соусы",
    "soup": "Супы",
}


def profile_defaults(event_type: str) -> dict[str, Any]:
    data = EVENT_PROFILES.get(event_type) or {}
    return {
        "format": data.get("format"),
        "meal_roles": list(data.get("default_roles") or []),
        "vibe": list(data.get("preferred_tags") or []),
        "max_difficulty": data.get("max_difficulty"),
    }
