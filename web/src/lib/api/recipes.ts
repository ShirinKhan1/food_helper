import { apiFetchJson } from "./client";
import type { RecipeDetailPayload } from "./chat";

export async function getRecipe(recipeId: number): Promise<RecipeDetailPayload> {
  return apiFetchJson(`/v1/recipes/${recipeId}`);
}
