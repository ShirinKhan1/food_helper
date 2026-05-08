import type { RecipeCardPayload } from "@/lib/api/chat";
import { Button } from "@/components/ui/Button";

type Props = {
  recipe: RecipeCardPayload;
  onDetails: (recipeId: number) => void;
};

export function RecipeCard({ recipe, onDetails }: Props) {
  const k =
    recipe.calories_kcal != null
      ? `${Math.round(recipe.calories_kcal)} ккал`
      : null;
  const macros =
    recipe.protein_g != null && recipe.fat_g != null && recipe.carbs_g != null
      ? `Б ${Math.round(recipe.protein_g)} г · Ж ${Math.round(recipe.fat_g)} г · У ${Math.round(recipe.carbs_g)} г`
      : null;
  const meta = [recipe.servings != null ? `Порции: ${recipe.servings}` : null, recipe.cooking_time, recipe.difficulty]
    .filter(Boolean)
    .join(" · ");

  return (
    <article className="rounded-xl border border-black/10 bg-white/80 p-3 text-sm shadow-sm dark:border-white/10 dark:bg-neutral-900/80">
      <h3 className="font-semibold text-neutral-900 dark:text-neutral-50">{recipe.title}</h3>
      {recipe.description ? (
        <p className="mt-1 line-clamp-3 text-neutral-600 dark:text-neutral-300">{recipe.description}</p>
      ) : null}
      {k || macros ? (
        <p className="mt-2 text-xs text-neutral-700 dark:text-neutral-200">
          {k}
          {k && macros ? " · " : ""}
          {macros}
        </p>
      ) : null}
      {meta ? <p className="mt-1 text-xs text-neutral-500">{meta}</p> : null}
      {recipe.allergens?.length ? (
        <p className="mt-1 text-xs text-amber-800 dark:text-amber-200">Аллергены: {recipe.allergens.join(", ")}</p>
      ) : null}
      <div className="mt-2">
        <Button variant="ghost" className="!px-0 text-emerald-700 dark:text-emerald-400" onClick={() => onDetails(recipe.recipe_id)}>
          Подробнее
        </Button>
      </div>
    </article>
  );
}
