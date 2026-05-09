from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.schemas.search import QueryConstraints
from app.services.ingredient_catalog import IngredientCatalog
from app.services.keyword_search import KeywordSearchService
from app.services.vector_search import VectorSearchService

_MINUTES_RE = re.compile(r"(\d{1,3})")
_DIFFICULTY_RE = re.compile(r"(\d)\s*из\s*5")


@dataclass
class HybridSearchExecution:
    normalized_query: str
    vector_results: list[dict[str, Any]]
    keyword_results: list[dict[str, Any]]
    final_results: list[dict[str, Any]]


def _normalize_scores(values: dict[int, float]) -> dict[int, float]:
    if not values:
        return {}
    max_score = max(values.values())
    if max_score <= 0:
        return {key: 0.0 for key in values}
    return {key: score / max_score for key, score in values.items()}


def _parse_minutes(value: str | None) -> int | None:
    if not value:
        return None
    match = _MINUTES_RE.search(value)
    return int(match.group(1)) if match else None


def _parse_difficulty(value: str | None) -> int | None:
    if not value:
        return None
    match = _DIFFICULTY_RE.search(value)
    return int(match.group(1)) if match else None


class HybridSearchService:
    def __init__(
        self,
        *,
        vector_search: VectorSearchService,
        keyword_search: KeywordSearchService,
        ingredient_catalog: IngredientCatalog,
    ) -> None:
        self._vector_search = vector_search
        self._keyword_search = keyword_search
        self._ingredient_catalog = ingredient_catalog

    def run(
        self,
        *,
        normalized_query: str,
        query_embedding: list[float],
        constraints: QueryConstraints,
        top_k: int,
        exclude_recipe_ids: frozenset[int] | set[int] | None = None,
    ) -> HybridSearchExecution:
        excl: frozenset[int] = frozenset(exclude_recipe_ids or ())
        pool_k = max(top_k * 3, top_k) + min(len(excl), 120)
        pool_k = min(pool_k, 300)
        vector_rows = self._vector_search.search(query_embedding, top_k=pool_k)
        keyword_rows = self._keyword_search.search(normalized_query, top_k=pool_k)

        vector_scores = {
            int(row["id"]): float(row.get("similarity") or 0.0) for row in vector_rows
        }
        keyword_scores = {
            int(row["id"]): float(row.get("keyword_score") or 0.0) for row in keyword_rows
        }
        vector_norm = _normalize_scores(vector_scores)
        keyword_norm = _normalize_scores(keyword_scores)

        merged: dict[int, dict[str, Any]] = {}
        for row in [*vector_rows, *keyword_rows]:
            rid = int(row["id"])
            merged.setdefault(rid, dict(row))

        ranked: list[dict[str, Any]] = []
        for rid, row in merged.items():
            if rid in excl:
                continue
            if not self._passes_filters(row, constraints):
                continue
            rules_score = self._rules_score(row, normalized_query, constraints)
            row["final_score"] = (
                0.65 * vector_norm.get(rid, 0.0)
                + 0.25 * keyword_norm.get(rid, 0.0)
                + 0.10 * rules_score
            )
            matched_by: list[str] = []
            if rid in vector_scores:
                matched_by.append("vector")
            if rid in keyword_scores:
                matched_by.append("keyword")
            if rules_score > 0:
                matched_by.append("rules")
            row["matched_by"] = matched_by
            ranked.append(row)

        ranked.sort(key=lambda row: (-float(row.get("final_score") or 0.0), int(row["id"])))
        return HybridSearchExecution(
            normalized_query=normalized_query,
            vector_results=vector_rows,
            keyword_results=keyword_rows,
            final_results=ranked[:top_k],
        )

    def filter_similar(
        self,
        rows: list[dict[str, Any]],
        *,
        normalized_query: str,
        constraints: QueryConstraints,
        top_k: int,
        exclude_recipe_ids: frozenset[int] | set[int] | None = None,
    ) -> HybridSearchExecution:
        excl: frozenset[int] = frozenset(exclude_recipe_ids or ())
        filtered: list[dict[str, Any]] = []
        for row in rows:
            rid = int(row["id"])
            if rid in excl:
                continue
            if not self._passes_filters(row, constraints):
                continue
            row = dict(row)
            row["final_score"] = 0.9 * float(row.get("similarity") or 0.0) + 0.1 * self._rules_score(
                row,
                normalized_query,
                constraints,
            )
            row["matched_by"] = ["vector"]
            filtered.append(row)
        filtered.sort(key=lambda row: (-float(row.get("final_score") or 0.0), int(row["id"])))
        final_rows = filtered[:top_k]
        return HybridSearchExecution(
            normalized_query=normalized_query,
            vector_results=rows,
            keyword_results=[],
            final_results=final_rows,
        )

    def _passes_filters(self, row: dict[str, Any], constraints: QueryConstraints) -> bool:
        exclusions = [*constraints.exclude_ingredients, *constraints.allergy_exclusions]
        if exclusions and self._ingredient_catalog.matches_any(row, exclusions):
            return False

        calories = row.get("calories_kcal")
        if constraints.max_calories_kcal is not None and calories is not None:
            if float(calories) > constraints.max_calories_kcal:
                return False

        fat = row.get("fat_g")
        if constraints.max_fat_g is not None and fat is not None:
            if float(fat) > constraints.max_fat_g:
                return False

        protein = row.get("protein_g")
        if constraints.min_protein_g is not None and protein is not None:
            if float(protein) < constraints.min_protein_g:
                return False

        props = row.get("properties") or {}
        if isinstance(props, dict):
            if constraints.max_cooking_time_minutes is not None:
                minutes = _parse_minutes(
                    props.get("Время на кухне") or props.get("Будет готово через")
                )
                if minutes is not None and minutes > constraints.max_cooking_time_minutes:
                    return False

            if constraints.max_difficulty is not None:
                difficulty = _parse_difficulty(props.get("Сложность"))
                if difficulty is not None and difficulty > constraints.max_difficulty:
                    return False

        return True

    def _rules_score(
        self,
        row: dict[str, Any],
        normalized_query: str,
        constraints: QueryConstraints,
    ) -> float:
        score = 0.0
        text = " ".join(
            [
                str(row.get("title") or "").lower(),
                str(row.get("description") or "").lower(),
                str(row.get("category") or "").lower(),
                str(row.get("subcategory") or "").lower(),
            ]
        )

        for token in normalized_query.split():
            if token and token in text:
                score += 0.2

        for ingredient in constraints.include_ingredients:
            if self._ingredient_catalog.matches_any(row, [ingredient]):
                score += 0.3

        if constraints.meal_type == "breakfast" and "завтрак" in text:
            score += 0.5
        if constraints.meal_type == "dinner" and "ужин" in text:
            score += 0.5
        if constraints.meal_type == "lunch" and "обед" in text:
            score += 0.5
        if constraints.meal_type == "snack" and "перекус" in text:
            score += 0.5

        return min(score, 1.0)
