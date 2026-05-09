from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.ingredient_catalog import normalize_ru_text_to_lemmas
from app.services.llm.context import LLMAnswerContext

FORBIDDEN_MEDICAL_GUARANTEES = (
    "точно безопасно",
    "полностью безопасно",
    "можно при любой аллергии",
    "гарантированно без аллергена",
    "медицински безопасно",
)

_EXCLUSION_NEGATOR_LEMMAS = frozenset(
    {"без", "кроме", "исключая", "нет", "исключить", "избегать", "минус"}
)
_MIN_EXCLUSION_TERM_LETTERS = 3


@dataclass(frozen=True)
class PostcheckResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    sanitized_answer: str | None = None


@dataclass(frozen=True)
class PostcheckPolicy:
    scenario: str
    strict_context: bool = True
    max_answer_chars: int = 2500
    strip_think_tags: bool = True


def validate_llm_answer(
    *,
    answer: str,
    context: LLMAnswerContext,
    policy: PostcheckPolicy,
) -> PostcheckResult:
    sanitized = answer.strip()
    if policy.strip_think_tags:
        sanitized = _strip_think_blocks(sanitized).strip()

    errors: list[str] = []
    if not sanitized:
        errors.append("empty_answer")
    if len(sanitized) > policy.max_answer_chars:
        errors.append("too_long")

    lowered = sanitized.lower()
    if any(phrase in lowered for phrase in FORBIDDEN_MEDICAL_GUARANTEES):
        errors.append("medical_guarantee")

    if _answer_violates_excluded_ingredients(sanitized, context):
        errors.append("forbidden_ingredient_mentioned")

    if context.scenario in {"recipe_list", "similar_recipes", "event_menu"}:
        allowed_titles = {recipe.title.lower() for recipe in context.recipes}
        if allowed_titles and _contains_unknown_list_title(sanitized, allowed_titles):
            errors.append("hallucinated_recipe")

    if context.scenario == "recipe_detail" and context.recipe_detail:
        title = context.recipe_detail.title.lower()
        if _mentions_quoted_title(sanitized) and title not in lowered:
            errors.append("wrong_recipe_detail")

    if context.scenario in {"nutrition", "nutrition_candidates"}:
        known_numbers = _extract_numbers_from_context(context)
        for number in _extract_numbers(sanitized):
            if policy.strict_context and known_numbers and number not in known_numbers:
                errors.append("hallucinated_nutrition")
                break

    if context.scenario in {"ingredient_substitution", "general_substitution"}:
        if policy.strict_context and context.substitutions:
            allowed = {item.name.lower() for item in context.substitutions}
            if _contains_unknown_list_title(sanitized, allowed):
                errors.append("hallucinated_substitution")

    return PostcheckResult(ok=not errors, errors=errors, sanitized_answer=sanitized)


def _answer_violates_excluded_ingredients(sanitized: str, context: LLMAnswerContext) -> bool:
    if context.scenario in {"ingredient_substitution", "general_substitution"}:
        return False
    if not context.constraints:
        return False
    raw_terms = [*context.constraints.exclude_ingredients, *context.constraints.allergy_exclusions]
    seen: set[str] = set()
    terms: list[str] = []
    for t in raw_terms:
        nt = normalize_ru_text_to_lemmas(t)
        if not nt or nt in seen:
            continue
        if sum(1 for ch in nt if ch.isalpha()) < _MIN_EXCLUSION_TERM_LETTERS:
            continue
        seen.add(nt)
        terms.append(nt)
    if not terms:
        return False

    norm_answer = normalize_ru_text_to_lemmas(sanitized)
    tokens = norm_answer.split()
    for term in terms:
        term_tokens = term.split()
        if not term_tokens or len(tokens) < len(term_tokens):
            continue
        n = len(term_tokens)
        for i in range(len(tokens) - n + 1):
            if tokens[i : i + n] != term_tokens:
                continue
            prev = tokens[i - 1] if i > 0 else None
            if prev in _EXCLUSION_NEGATOR_LEMMAS:
                continue
            return True
    return False


_t = "think"
# Model-specific reasoning wrappers removed by _THINK_BLOCK_RES below.
_THINK_BLOCK_RES = (
    re.compile(rf"<{_t}>.*?</{_t}>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<reasoning>.*?</reasoning>", re.IGNORECASE | re.DOTALL),
)


def _strip_think_blocks(text: str) -> str:
    out = text
    while True:
        prev = out
        for pattern in _THINK_BLOCK_RES:
            out = pattern.sub("", out)
        if out == prev:
            break
    return out


def _extract_numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", text))


def _extract_numbers_from_context(context: LLMAnswerContext) -> set[str]:
    numbers: set[str] = set()
    for recipe in context.recipes:
        for value in [recipe.calories_kcal, recipe.protein_g, recipe.fat_g, recipe.carbs_g]:
            if value is not None:
                numbers.add(str(value).replace(",", "."))
                numbers.add(str(int(value)) if float(value).is_integer() else str(value))
    if context.nutrition:
        for value in [
            context.nutrition.calories_kcal,
            context.nutrition.protein_g,
            context.nutrition.fat_g,
            context.nutrition.carbs_g,
        ]:
            if value is not None:
                numbers.add(str(value).replace(",", "."))
                numbers.add(str(int(value)) if float(value).is_integer() else str(value))
    return numbers


def _contains_unknown_list_title(answer: str, allowed_titles: set[str]) -> bool:
    if not allowed_titles:
        return False
    for line in answer.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if re.match(r"^(\d+[\).]|[-*])\s+", cleaned):
            candidate = re.sub(r"^(\d+[\).]|[-*])\s+", "", cleaned)
            candidate = candidate.split("—")[0].split("-")[0].split(":")[0].strip().lower()
            if candidate and candidate not in allowed_titles:
                return True
    return False


def _mentions_quoted_title(answer: str) -> bool:
    return bool(re.search(r"[\"«][^\"»]{2,}[\"»]", answer))
