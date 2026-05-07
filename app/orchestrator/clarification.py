from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.schemas.parser import ParsedQueryConstraints, ParsedUserRequest

if TYPE_CHECKING:
    from app.services.conversation_state import ConversationSnapshot


class PendingClarification(BaseModel):
    original_message: str
    partial_parsed_request: dict
    question: str
    expected_fields: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    created_at: str
    reason: str = ""


@dataclass
class ClarificationResolveResult:
    resolved: bool = False
    parsed: ParsedUserRequest | None = None
    should_repeat_question: bool = False
    abandon_pending: bool = False


_NEW_QUERY_RE = re.compile(
    r"(найди|подбери|покажи\s+рецепт|что\s+(?:можно\s+)?приготовить|рецепт\s+)",
    re.IGNORECASE,
)


class ClarificationManager:
    def build_pending(self, *, original_message: str, parsed: ParsedUserRequest) -> PendingClarification:
        clar = parsed.clarification
        if clar is None:
            raise ValueError("parsed.clarification required")
        return PendingClarification(
            original_message=original_message,
            partial_parsed_request=parsed.model_dump(mode="json"),
            question=clar.question,
            expected_fields=list(clar.expected_fields),
            options=list(clar.options),
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            reason=clar.reason,
        )

    def try_resolve(
        self,
        *,
        pending: PendingClarification,
        message: str,
        snapshot: "ConversationSnapshot",
    ) -> ClarificationResolveResult:
        text = message.strip()
        lowered = text.lower()

        if self._looks_like_new_query(text, lowered):
            return ClarificationResolveResult(abandon_pending=True)

        partial = ParsedUserRequest.model_validate(pending.partial_parsed_request)

        if pending.reason in {"ambiguous_light_goal", "ambiguous_light"}:
            merged = self._merge_light_disambiguation(partial, lowered, pending.options)
            if merged is not None:
                return ClarificationResolveResult(resolved=True, parsed=merged)
            if len(text) < 2:
                return ClarificationResolveResult(should_repeat_question=True)
            return ClarificationResolveResult(should_repeat_question=True)

        if pending.reason in {"include_exclude_conflict"}:
            if "без" in lowered and len(text) > 5:
                return ClarificationResolveResult(abandon_pending=True)
            return ClarificationResolveResult(should_repeat_question=True)

        if pending.reason in {"missing_recipe_context", "missing_selected_recipe"}:
            if snapshot.last_recipe_results or snapshot.selected_recipe_id is not None:
                return ClarificationResolveResult(abandon_pending=True)
            if len(text) < 2:
                return ClarificationResolveResult(should_repeat_question=True)
            return ClarificationResolveResult(abandon_pending=True)

        if len(text) < 2:
            return ClarificationResolveResult(should_repeat_question=True)

        return ClarificationResolveResult(abandon_pending=True)

    def _looks_like_new_query(self, text: str, lowered: str) -> bool:
        if len(text.split()) > 14:
            return True
        return bool(_NEW_QUERY_RE.search(lowered))

    def _merge_light_disambiguation(
        self,
        partial: ParsedUserRequest,
        lowered: str,
        options: list[str],
    ) -> ParsedUserRequest | None:
        c = partial.constraints.model_dump()

        def matches_calories() -> bool:
            if "калори" in lowered or "ккал" in lowered:
                return True
            for o in options:
                ol = o.strip().lower()
                if "калори" not in ol:
                    continue
                if lowered == ol or ol in lowered or lowered in ol:
                    return True
            return False

        def matches_prep() -> bool:
            if "приготов" in lowered or "готовить" in lowered or "прост" in lowered:
                return True
            for o in options:
                ol = o.strip().lower()
                if "приготов" not in ol and "готов" not in ol:
                    continue
                if lowered == ol or ol in lowered or lowered in ol:
                    return True
            return False

        if matches_calories():
            c["diet_goal"] = "light_calories"
            if c.get("max_calories_kcal") is None:
                c["max_calories_kcal"] = 350.0
            return self._finalize_partial(partial, c)

        if matches_prep():
            c["diet_goal"] = "easy"
            c["max_cooking_time_minutes"] = 30
            c["max_difficulty"] = 2
            return self._finalize_partial(partial, c)

        if "и то и другое" in lowered or "оба" in lowered:
            c["diet_goal"] = "light_mixed"
            c["max_calories_kcal"] = min(c.get("max_calories_kcal") or 400, 400)
            c["max_cooking_time_minutes"] = 30
            c["max_difficulty"] = 2
            return self._finalize_partial(partial, c)

        return None

    def _finalize_partial(self, partial: ParsedUserRequest, constraints_data: dict) -> ParsedUserRequest:
        new_c = ParsedQueryConstraints.model_validate(constraints_data)
        return partial.model_copy(
            update={
                "constraints": new_c,
                "requires_clarification": False,
                "clarification": None,
                "confidence": 1.0,
            }
        )
