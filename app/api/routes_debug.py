from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_services
from app.core.db import DatabaseUnavailableError
from app.orchestrator.query_constraints import extract_query_constraints
from app.schemas.search import SearchDebugItem, SearchDebugRequest, SearchDebugResponse
from app.services.container import AppServices

router = APIRouter(prefix="/v1/search", tags=["debug"])


@router.post("/debug", response_model=SearchDebugResponse)
def search_debug(
    request: SearchDebugRequest,
    services: AppServices = Depends(get_services),
) -> SearchDebugResponse:
    query = request.query.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query must not be empty.",
        )

    constraints = extract_query_constraints(query).merge(request.filters)

    try:
        execution = services.search_service.search(
            query,
            constraints=constraints,
            top_k=request.top_k,
        )
    except DatabaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database is unavailable: {exc}",
        ) from exc

    def convert(rows: list[dict]) -> list[SearchDebugItem]:
        def row_score(row: dict) -> float | None:
            raw = row.get("final_score")
            if raw is None:
                raw = row.get("keyword_score")
            if raw is None:
                return None
            return float(raw)

        return [
            SearchDebugItem(
                recipe_id=int(row["id"]),
                title=str(row.get("title") or "(без названия)"),
                recipe_url=str(row.get("recipe_url") or ""),
                similarity=float(row["similarity"]) if row.get("similarity") is not None else None,
                score=row_score(row),
                matched_by=list(row.get("matched_by", [])),
            )
            for row in rows
        ]

    return SearchDebugResponse(
        normalized_query=execution.normalized_query,
        constraints=constraints,
        vector_results=convert(execution.vector_results),
        keyword_results=convert(execution.keyword_results),
        final_results=convert(execution.final_results),
    )
