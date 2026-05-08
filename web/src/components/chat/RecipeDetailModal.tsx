"use client";

import { useEffect, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { getRecipe } from "@/lib/api/recipes";
import type { RecipeDetailPayload } from "@/lib/api/chat";
import { ApiRequestError } from "@/lib/api/client";

type Props = {
  recipeId: number | null;
  onClose: () => void;
};

export function RecipeDetailModal({ recipeId, onClose }: Props) {
  const [data, setData] = useState<RecipeDetailPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (recipeId == null) {
      setData(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getRecipe(recipeId)
      .then((r) => {
        if (!cancelled) setData(r);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof ApiRequestError ? e.message : "Не удалось загрузить рецепт");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [recipeId]);

  const open = recipeId != null;

  return (
    <Modal open={open} title={data?.title ?? "Рецепт"} onClose={onClose} wide>
      {loading ? (
        <div className="flex items-center gap-2 py-8 text-sm text-neutral-600">
          <Spinner />
          Загрузка…
        </div>
      ) : error ? (
        <p className="text-sm text-red-600">{error}</p>
      ) : data ? (
        <div className="space-y-4 text-sm">
          {data.description ? <p className="text-neutral-700 dark:text-neutral-200">{data.description}</p> : null}
          <div>
            <h3 className="font-semibold">Ингредиенты</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {data.ingredients.map((ing, i) => (
                <li key={`${ing.name}-${i}`}>
                  {ing.name}
                  {ing.quantity ? ` — ${ing.quantity}` : ""}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="font-semibold">Шаги</h3>
            <ol className="mt-2 list-decimal space-y-2 pl-5">
              {data.steps.map((st) => (
                <li key={st.position}>
                  {st.title ? <span className="font-medium">{st.title}. </span> : null}
                  {st.text}
                </li>
              ))}
            </ol>
          </div>
          <NutritionInline n={data.nutrition} servings={data.servings} />
          {Object.keys(data.properties ?? {}).length ? (
            <div>
              <h3 className="font-semibold">Свойства</h3>
              <ul className="mt-1 space-y-1 text-neutral-700 dark:text-neutral-200">
                {Object.entries(data.properties).map(([k, v]) => (
                  <li key={k}>
                    {k}: {Array.isArray(v) ? v.join(", ") : String(v ?? "")}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <a
            href={data.recipe_url}
            target="_blank"
            rel="noreferrer"
            className="inline-block text-emerald-700 underline dark:text-emerald-400"
          >
            Открыть оригинал рецепта
          </a>
        </div>
      ) : null}
    </Modal>
  );
}

function NutritionInline({
  n,
  servings,
}: {
  n: RecipeDetailPayload["nutrition"];
  servings: number | null | undefined;
}) {
  const parts = [
    n.calories_kcal != null ? `${Math.round(n.calories_kcal)} ккал` : null,
    n.protein_g != null ? `Б ${Math.round(n.protein_g)} г` : null,
    n.fat_g != null ? `Ж ${Math.round(n.fat_g)} г` : null,
    n.carbs_g != null ? `У ${Math.round(n.carbs_g)} г` : null,
  ].filter(Boolean);
  if (!parts.length && servings == null) return null;
  return (
    <div>
      <h3 className="font-semibold">КБЖУ</h3>
      <p className="mt-1 text-neutral-700 dark:text-neutral-200">{parts.join(" · ")}</p>
      {servings != null ? <p className="text-xs text-neutral-500">Порции: {servings}</p> : null}
    </div>
  );
}
