from __future__ import annotations

from app.schemas.recipe import NutritionInfo
from app.services.recipe_repository import RecipeRepository


class NutritionService:
    def __init__(self, recipe_repository: RecipeRepository) -> None:
        self._recipe_repository = recipe_repository

    def get_nutrition(self, recipe_id: int) -> NutritionInfo | None:
        row = self._recipe_repository.get_recipe_row_by_id(recipe_id)
        if not row:
            return None
        detail = self._recipe_repository.row_to_recipe_detail(row)
        return detail.nutrition

    def format_answer(self, title: str, nutrition: NutritionInfo, nutrient: str | None) -> str:
        if nutrient == "protein":
            return f'В рецепте "{title}" указано {nutrition.protein_g} г белка на 100 г.'
        if nutrient == "fat":
            return f'В рецепте "{title}" указано {nutrition.fat_g} г жиров на 100 г.'
        if nutrient == "carbs":
            return f'В рецепте "{title}" указано {nutrition.carbs_g} г углеводов на 100 г.'
        return (
            f'В рецепте "{title}" указано: калории {nutrition.calories_kcal} кКал, '
            f'белки {nutrition.protein_g} г, жиры {nutrition.fat_g} г, '
            f'углеводы {nutrition.carbs_g} г на 100 г.'
        )
