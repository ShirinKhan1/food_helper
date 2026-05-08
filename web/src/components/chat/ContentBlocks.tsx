import type { NutritionInfoPayload, SubstitutionOptionPayload, SourceInfoPayload } from "@/lib/api/chat";

export function NutritionBlock({ nutrition }: { nutrition: NutritionInfoPayload }) {
  const parts = [
    nutrition.calories_kcal != null ? `${Math.round(nutrition.calories_kcal)} ккал` : null,
    nutrition.protein_g != null ? `Б ${Math.round(nutrition.protein_g)} г` : null,
    nutrition.fat_g != null ? `Ж ${Math.round(nutrition.fat_g)} г` : null,
    nutrition.carbs_g != null ? `У ${Math.round(nutrition.carbs_g)} г` : null,
  ].filter(Boolean);
  if (!parts.length) return null;
  return (
    <div className="mt-3 rounded-lg border border-emerald-200/80 bg-emerald-50/70 p-3 text-sm dark:border-emerald-900/50 dark:bg-emerald-950/40">
      <p className="font-medium text-emerald-950 dark:text-emerald-100">КБЖУ</p>
      <p className="mt-1 text-neutral-800 dark:text-neutral-200">{parts.join(" · ")}</p>
      {nutrition.serving_size ? (
        <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-300">Порция: {nutrition.serving_size}</p>
      ) : null}
    </div>
  );
}

export function SubstitutionsBlock({ items }: { items: SubstitutionOptionPayload[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-3 rounded-lg border border-violet-200/80 bg-violet-50/70 p-3 text-sm dark:border-violet-900/50 dark:bg-violet-950/40">
      <p className="font-medium text-violet-950 dark:text-violet-100">Замены ингредиентов</p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-neutral-800 dark:text-neutral-200">
        {items.map((s) => (
          <li key={s.name}>
            <span className="font-medium">{s.name}</span>
            {s.ratio ? <span className="text-neutral-600"> — {s.ratio}</span> : null}
            {s.note ? <span className="text-neutral-600"> ({s.note})</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SourcesBlock({ sources }: { sources: SourceInfoPayload[] }) {
  if (!sources.length) return null;
  return (
    <div className="mt-3 text-xs text-neutral-600 dark:text-neutral-300">
      <p className="font-medium text-neutral-800 dark:text-neutral-100">Источники</p>
      <ul className="mt-1 space-y-1">
        {sources.map((s, i) => (
          <li key={`${s.url ?? s.title ?? i}`}>
            {s.url ? (
              <a href={s.url} className="text-emerald-700 underline dark:text-emerald-400" target="_blank" rel="noreferrer">
                {s.title || s.url}
              </a>
            ) : (
              <span>{s.title}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
