import os
import json
import time
from decimal import Decimal, InvalidOperation

import psycopg2
from psycopg2.extras import Json, execute_values


def _env(name: str, default: str | None = None) -> str:
    val = os.getenv(name, default)
    if val is None:
        raise RuntimeError(f"Missing env var: {name}")
    return val


def _to_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    # В файле значения типа "117,64" -> делаем Decimal("117.64")
    try:
        return Decimal(value.replace(" ", "").replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def _extract_macros(rec: dict):
    n = rec.get("nutrition") or {}
    calories = _to_decimal((n.get("Калории") or {}).get("value"))
    protein = _to_decimal((n.get("Белки") or {}).get("value"))
    fat = _to_decimal((n.get("Жиры") or {}).get("value"))
    carbs = _to_decimal((n.get("Углеводы") or {}).get("value"))
    return calories, protein, fat, carbs


def connect_with_retries(dsn: str, retries: int = 40, delay_s: float = 1.0):
    last_err = None
    for _ in range(retries):
        try:
            conn = psycopg2.connect(dsn)
            conn.autocommit = False
            return conn
        except Exception as e:
            last_err = e
            time.sleep(delay_s)
    raise RuntimeError(f"Could not connect to Postgres: {last_err}")


def main():
    host = _env("DB_HOST", "db")
    port = _env("DB_PORT", "5432")
    name = _env("DB_NAME", "food_helper")
    user = _env("DB_USER", "food")
    password = _env("DB_PASSWORD", "foodpass")
    jsonl_path = _env("JSONL_PATH", "/data/recipes.jsonl")
    batch_size = int(_env("BATCH_SIZE", "500"))

    dsn = f"host={host} port={port} dbname={name} user={user} password={password}"
    conn = connect_with_retries(dsn)

    insert_sql = """
    INSERT INTO recipes (
      recipe_url, source, title, description, servings,
      category, subcategory, subcategory_url, afterword,
      calories_kcal, protein_g, fat_g, carbs_g,
      nutrition, properties, ingredients, steps, raw
    )
    VALUES %s
    ON CONFLICT (recipe_url) DO UPDATE SET
      source = EXCLUDED.source,
      title = EXCLUDED.title,
      description = EXCLUDED.description,
      servings = EXCLUDED.servings,
      category = EXCLUDED.category,
      subcategory = EXCLUDED.subcategory,
      subcategory_url = EXCLUDED.subcategory_url,
      afterword = EXCLUDED.afterword,
      calories_kcal = EXCLUDED.calories_kcal,
      protein_g = EXCLUDED.protein_g,
      fat_g = EXCLUDED.fat_g,
      carbs_g = EXCLUDED.carbs_g,
      nutrition = EXCLUDED.nutrition,
      properties = EXCLUDED.properties,
      ingredients = EXCLUDED.ingredients,
      steps = EXCLUDED.steps,
      raw = EXCLUDED.raw
    ;
    """

    total = 0
    buf = []

    with conn, conn.cursor() as cur:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                rec = json.loads(line)

                recipe_url = rec.get("recipe_url") or rec.get("source")
                if not recipe_url:
                    continue

                calories, protein, fat, carbs = _extract_macros(rec)

                buf.append((
                    recipe_url,
                    rec.get("source"),
                    rec.get("title"),
                    rec.get("description"),
                    rec.get("servings"),
                    rec.get("category"),
                    rec.get("subcategory"),
                    rec.get("subcategory_url"),
                    rec.get("afterword"),
                    calories,
                    protein,
                    fat,
                    carbs,
                    Json(rec.get("nutrition")),
                    Json(rec.get("properties")),
                    Json(rec.get("ingredients")),
                    Json(rec.get("steps")),
                    Json(rec),
                ))

                if len(buf) >= batch_size:
                    execute_values(cur, insert_sql, buf, page_size=batch_size)
                    total += len(buf)
                    buf.clear()

            if buf:
                execute_values(cur, insert_sql, buf, page_size=len(buf))
                total += len(buf)

    print(f"Loaded/updated rows: {total}")


if __name__ == "__main__":
    main()
