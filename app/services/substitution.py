from __future__ import annotations

from dataclasses import dataclass

from app.schemas.recipe import RecipeDetail, SubstitutionOption
from app.services.ingredient_catalog import IngredientCatalog


@dataclass
class SubstitutionResult:
    found_in_recipe: bool
    options: list[SubstitutionOption]
    warnings: list[str]


class SubstitutionService:
    def __init__(self, ingredient_catalog: IngredientCatalog) -> None:
        self._ingredient_catalog = ingredient_catalog

    def suggest(self, recipe: RecipeDetail, target_ingredient: str) -> SubstitutionResult:
        canonical = self._ingredient_catalog.canonicalize(target_ingredient)
        found_in_recipe = False
        for ingredient in recipe.ingredients:
            ingredient_name = self._ingredient_catalog.canonicalize(ingredient.name)
            if canonical == ingredient_name or canonical in ingredient.name.lower():
                found_in_recipe = True
                break

        raw_options = self._ingredient_catalog.substitutions.get(canonical, [])
        options = [SubstitutionOption.model_validate(option) for option in raw_options]

        warnings = [
            "Это адаптация рецепта, а не исходная инструкция из базы. Калорийность и вкус могут измениться."
        ]
        if not options:
            warnings.append("Для этого ингредиента пока нет готового rule-based словаря замен.")

        return SubstitutionResult(
            found_in_recipe=found_in_recipe,
            options=options,
            warnings=warnings,
        )
