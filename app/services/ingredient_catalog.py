from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _data_path(filename: str) -> Path:
    return Path(__file__).resolve().parents[2] / "data" / filename


def _load_json(filename: str) -> dict:
    return json.loads(_data_path(filename).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _morph_analyzer():
    from pymorphy3 import MorphAnalyzer

    return MorphAnalyzer()


def _normalize_text(value: str) -> str:
    parts = []
    morph = _morph_analyzer()
    for part in value.lower().replace("ё", "е").split():
        parts.append(morph.parse(part.strip(".,;:!?()[]{}"))[0].normal_form)
    return " ".join(part for part in parts if part)


def normalize_ru_text_to_lemmas(value: str) -> str:
    """Lemmatize Russian text to a space-separated normal form (shared with recipe matching)."""
    return _normalize_text(value)


@dataclass
class IngredientCatalog:
    aliases: dict[str, str]
    groups: dict[str, list[str]]
    substitutions: dict[str, list[dict[str, str]]]

    @classmethod
    def load(cls) -> "IngredientCatalog":
        aliases = {k.lower(): v.lower() for k, v in _load_json("ingredient_aliases.json").items()}
        groups = {
            key.lower(): [item.lower() for item in value]
            for key, value in _load_json("ingredient_groups.json").items()
        }
        substitutions = {
            key.lower(): value for key, value in _load_json("substitution_rules.json").items()
        }
        return cls(aliases=aliases, groups=groups, substitutions=substitutions)

    def canonicalize(self, value: str) -> str:
        text = " ".join(value.lower().split()).strip()
        return self.aliases.get(text, text)

    def expand_term(self, value: str) -> set[str]:
        canonical = self.canonicalize(value)
        expanded = {canonical}
        for group_name, items in self.groups.items():
            if canonical == group_name or canonical in items:
                expanded.add(group_name)
                expanded.update(items)
        for alias, target in self.aliases.items():
            if target == canonical:
                expanded.add(alias)
        return expanded

    def ingredient_names(self, recipe_row: dict) -> list[str]:
        ingredients = recipe_row.get("ingredients") or []
        names: list[str] = []
        if isinstance(ingredients, list):
            for item in ingredients:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip().lower()
                if name:
                    names.append(name)
        return names

    def characteristic_values(self, recipe_row: dict) -> list[str]:
        props = recipe_row.get("properties") or {}
        if not isinstance(props, dict):
            return []

        values: list[str] = []
        allergens = props.get("Аллергены") or props.get("аллергены") or props.get("allergens") or []
        if isinstance(allergens, list):
            values.extend(str(item).strip().lower() for item in allergens if str(item).strip())
        elif isinstance(allergens, str):
            values.extend(part.strip().lower() for part in allergens.split(",") if part.strip())
        return values

    def matches_any(self, recipe_row: dict, terms: list[str]) -> bool:
        if not terms:
            return False

        ingredient_names = self.ingredient_names(recipe_row)
        characteristic_values = self.characteristic_values(recipe_row)
        normalized_characteristics = [_normalize_text(value) for value in characteristic_values]
        haystack = " ".join(
            [
                str(recipe_row.get("title") or "").lower(),
                str(recipe_row.get("description") or "").lower(),
                str(recipe_row.get("ingredients") or "").lower(),
                str(recipe_row.get("raw") or "").lower(),
            ]
        )

        for term in terms:
            expanded = self.expand_term(term)
            for candidate in expanded:
                if ingredient_names and any(candidate in ingredient for ingredient in ingredient_names):
                    return True
                normalized_candidate = _normalize_text(candidate)
                if normalized_candidate and any(
                    normalized_candidate in characteristic
                    for characteristic in normalized_characteristics
                ):
                    return True
                if not ingredient_names and candidate in haystack:
                    return True
        return False
