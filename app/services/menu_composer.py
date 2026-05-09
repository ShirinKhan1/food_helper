from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.schemas.event import EventMenuGroup, EventProfile
from app.schemas.recipe import RecipeCard
from app.services.event_profiles import ROLE_TITLES_RU


class MenuComposer:
    def compose(
        self,
        *,
        ranked_rows: list[dict[str, Any]],
        event_profile: EventProfile,
        top_k: int,
        row_to_card: Callable[..., RecipeCard],
    ) -> list[EventMenuGroup]:
        roles = list(event_profile.meal_roles) or ["main"]
        used: set[int] = set()
        groups: list[EventMenuGroup] = []

        for role in roles:
            candidates = [
                r
                for r in ranked_rows
                if int(r.get("id") or 0) not in used and role in (r.get("event_roles") or [])
            ]
            candidates.sort(key=lambda r: (-float(r.get("event_score") or 0.0), int(r.get("id") or 0)))
            picked = candidates[:2]
            if not picked:
                continue
            title = ROLE_TITLES_RU.get(role, role.replace("_", " ").title())
            cards: list[RecipeCard] = []
            for idx, row in enumerate(picked, start=1):
                cards.append(row_to_card(row, rank=idx))
                used.add(int(row.get("id") or 0))
            groups.append(EventMenuGroup(role=role, title=title, recipes=cards))

        if groups:
            return groups

        fallback = sorted(
            ranked_rows,
            key=lambda r: (-float(r.get("event_score") or 0.0), int(r.get("id") or 0)),
        )[: max(1, min(top_k, 5))]
        if not fallback:
            return []
        cards = [row_to_card(row, rank=idx) for idx, row in enumerate(fallback, start=1)]
        return [EventMenuGroup(role="main", title="Рекомендации", recipes=cards)]
