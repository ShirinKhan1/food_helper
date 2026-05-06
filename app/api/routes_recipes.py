from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_services
from app.core.db import DatabaseUnavailableError
from app.schemas.recipe import RecipeDetail
from app.services.container import AppServices

router = APIRouter(prefix="/v1/recipes", tags=["recipes"])


@router.get("/{recipe_id}", response_model=RecipeDetail)
def get_recipe(recipe_id: int, services: AppServices = Depends(get_services)) -> RecipeDetail:
    try:
        row = services.recipe_repository.get_recipe_row_by_id(recipe_id)
    except DatabaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database is unavailable: {exc}",
        ) from exc

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipe not found.",
        )
    return services.recipe_repository.row_to_recipe_detail(row)
