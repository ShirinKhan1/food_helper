from __future__ import annotations

from decimal import Decimal
from typing import Any

from psycopg2.extras import RealDictCursor

from app.core.db import Database
from app.schemas.recipe import NutritionInfo, RecipeCard, RecipeDetail, RecipeIngredient, RecipeStep


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _properties(row: dict[str, Any]) -> dict[str, Any]:
    props = row.get("properties")
    return props if isinstance(props, dict) else {}


def _allergens_from_properties(props: dict[str, Any]) -> list[str]:
    allergens = props.get("Аллергены") or props.get("аллергены") or []
    if isinstance(allergens, list):
        return [str(item).strip() for item in allergens if str(item).strip()]
    if isinstance(allergens, str):
        return [part.strip() for part in allergens.split(",") if part.strip()]
    return []


def _cooking_time(props: dict[str, Any]) -> str | None:
    value = props.get("Время на кухне") or props.get("Будет готово через")
    return str(value) if value else None


def _difficulty(props: dict[str, Any]) -> str | None:
    value = props.get("Сложность")
    return str(value) if value else None


def _parse_ingredients(row: dict[str, Any]) -> list[RecipeIngredient]:
    ingredients = row.get("ingredients")
    if not isinstance(ingredients, list):
        return []

    parsed: list[RecipeIngredient] = []
    for item in ingredients:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        quantity = item.get("quantity") or item.get("amount") or item.get("value")
        parsed.append(
            RecipeIngredient(
                name=name,
                quantity=str(quantity).strip() if quantity else None,
                block=str(item.get("block")).strip() if item.get("block") else None,
            )
        )
    return parsed


def _parse_steps(row: dict[str, Any]) -> list[RecipeStep]:
    steps = row.get("steps")
    if not isinstance(steps, list):
        return []

    parsed: list[RecipeStep] = []
    for idx, item in enumerate(steps, start=1):
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("description") or "").strip()
            if not text:
                continue
            title = item.get("title")
            position = _to_int(item.get("position")) or idx
            parsed.append(
                RecipeStep(
                    position=position,
                    title=str(title).strip() if title else None,
                    text=text,
                )
            )
        elif isinstance(item, str) and item.strip():
            parsed.append(RecipeStep(position=idx, title=None, text=item.strip()))
    return parsed


class RecipeRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get_recipe_row_by_id(self, recipe_id: int) -> dict[str, Any] | None:
        with self._db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                      id, recipe_url, source, title, description, servings,
                      category, subcategory, subcategory_url, afterword,
                      calories_kcal, protein_g, fat_g, carbs_g,
                      nutrition, properties, ingredients, steps, raw,
                      created_at
                    FROM recipes
                    WHERE id = %s
                    """,
                    (recipe_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def get_recipe_rows_by_ids(self, recipe_ids: list[int]) -> list[dict[str, Any]]:
        if not recipe_ids:
            return []
        with self._db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                      id, recipe_url, source, title, description, servings,
                      category, subcategory, subcategory_url, afterword,
                      calories_kcal, protein_g, fat_g, carbs_g,
                      nutrition, properties, ingredients, steps, raw,
                      created_at
                    FROM recipes
                    WHERE id = ANY(%s)
                    """,
                    (recipe_ids,),
                )
                rows = [dict(row) for row in cur.fetchall()]
        by_id = {int(row["id"]): row for row in rows}
        return [by_id[recipe_id] for recipe_id in recipe_ids if recipe_id in by_id]

    def search_recipe_rows_by_text(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        clean_query = " ".join(query.split()).strip()
        if not clean_query:
            return []

        with self._db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    WITH q AS (
                      SELECT websearch_to_tsquery('russian', %s) AS tsq
                    )
                    SELECT
                      id, recipe_url, source, title, description, servings,
                      category, subcategory, subcategory_url, afterword,
                      calories_kcal, protein_g, fat_g, carbs_g,
                      nutrition, properties, ingredients, steps, raw,
                      created_at,
                      ts_rank_cd(
                        setweight(to_tsvector('russian', coalesce(title, '')), 'A') ||
                        setweight(to_tsvector('russian', coalesce(description, '')), 'B') ||
                        setweight(to_tsvector('russian', coalesce(ingredients::text, '')), 'B') ||
                        setweight(to_tsvector('russian', coalesce(raw::text, '')), 'C'),
                        q.tsq
                      ) AS keyword_score
                    FROM recipes, q
                    WHERE
                      (
                        setweight(to_tsvector('russian', coalesce(title, '')), 'A') ||
                        setweight(to_tsvector('russian', coalesce(description, '')), 'B') ||
                        setweight(to_tsvector('russian', coalesce(ingredients::text, '')), 'B') ||
                        setweight(to_tsvector('russian', coalesce(raw::text, '')), 'C')
                      ) @@ q.tsq
                    ORDER BY keyword_score DESC, id ASC
                    LIMIT %s
                    """,
                    (clean_query, limit),
                )
                return [dict(row) for row in cur.fetchall()]

    def row_to_recipe_card(self, row: dict[str, Any], *, rank: int) -> RecipeCard:
        props = _properties(row)
        return RecipeCard(
            rank=rank,
            recipe_id=int(row["id"]),
            title=str(row.get("title") or "(без названия)"),
            description=str(row.get("description")).strip() if row.get("description") else None,
            calories_kcal=_to_float(row.get("calories_kcal")),
            protein_g=_to_float(row.get("protein_g")),
            fat_g=_to_float(row.get("fat_g")),
            carbs_g=_to_float(row.get("carbs_g")),
            servings=_to_int(row.get("servings")),
            cooking_time=_cooking_time(props),
            difficulty=_difficulty(props),
            allergens=_allergens_from_properties(props),
            recipe_url=str(row.get("recipe_url") or ""),
            similarity=_to_float(row.get("similarity")),
        )

    def row_to_recipe_detail(self, row: dict[str, Any]) -> RecipeDetail:
        props = _properties(row)
        return RecipeDetail(
            recipe_id=int(row["id"]),
            title=str(row.get("title") or "(без названия)"),
            description=str(row.get("description")).strip() if row.get("description") else None,
            ingredients=_parse_ingredients(row),
            steps=_parse_steps(row),
            nutrition=NutritionInfo(
                calories_kcal=_to_float(row.get("calories_kcal")),
                protein_g=_to_float(row.get("protein_g")),
                fat_g=_to_float(row.get("fat_g")),
                carbs_g=_to_float(row.get("carbs_g")),
                serving_size="100 г",
            ),
            properties={
                "cooking_time": _cooking_time(props),
                "difficulty": _difficulty(props),
                "allergens": _allergens_from_properties(props),
            },
            servings=_to_int(row.get("servings")),
            recipe_url=str(row.get("recipe_url") or ""),
        )
