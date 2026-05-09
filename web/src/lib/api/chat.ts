import { apiFetchJson } from "./client";

export type ChatRequestPayload = {
  conversation_id?: string | null;
  message: string;
  options?: { top_k?: number; include_debug?: boolean };
  edit_user_message_id?: number | null;
};

export type ChatResponsePayload = {
  conversation_id: string;
  answer: string;
  intent: string;
  route: string;
  recipes: RecipeCardPayload[];
  selected_recipe: RecipeDetailPayload | null;
  nutrition: NutritionInfoPayload | null;
  substitutions: SubstitutionOptionPayload[];
  warnings: string[];
  sources: SourceInfoPayload[];
  requires_clarification: boolean;
  clarification: ClarificationPayload | null;
  user_message_id?: number | null;
  assistant_message_id?: number | null;
};

export type ClarificationPayload = {
  question: string;
  options?: string[] | null;
};

export type RecipeCardPayload = {
  rank: number;
  recipe_id: number;
  title: string;
  description?: string | null;
  calories_kcal?: number | null;
  protein_g?: number | null;
  fat_g?: number | null;
  carbs_g?: number | null;
  servings?: number | null;
  cooking_time?: string | null;
  difficulty?: string | null;
  allergens: string[];
  recipe_url: string;
};

export type RecipeIngredientPayload = { name: string; quantity?: string | null; block?: string | null };
export type RecipeStepPayload = { position: number; title?: string | null; text: string };

export type NutritionInfoPayload = {
  calories_kcal?: number | null;
  protein_g?: number | null;
  fat_g?: number | null;
  carbs_g?: number | null;
  serving_size?: string | null;
};

export type RecipeDetailPayload = {
  recipe_id: number;
  title: string;
  description?: string | null;
  ingredients: RecipeIngredientPayload[];
  steps: RecipeStepPayload[];
  nutrition: NutritionInfoPayload;
  properties: Record<string, string | string[] | null | undefined>;
  servings?: number | null;
  recipe_url: string;
};

export type SourceInfoPayload = { type: string; recipe_id?: number | null; title?: string | null; url?: string | null };

export type SubstitutionOptionPayload = { name: string; ratio?: string | null; note?: string | null };

export async function sendChatMessage(payload: ChatRequestPayload): Promise<ChatResponsePayload> {
  return apiFetchJson("/v1/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type ChatListItemPayload = {
  conversation_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
};

export async function getChats(): Promise<{ items: ChatListItemPayload[] }> {
  return apiFetchJson("/v1/chats");
}

export type ChatMessagePayload = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export async function getChat(conversationId: string): Promise<{
  conversation_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  messages: ChatMessagePayload[];
}> {
  return apiFetchJson(`/v1/chats/${conversationId}`);
}

export async function updateChatTitle(conversationId: string, title: string): Promise<unknown> {
  return apiFetchJson(`/v1/chats/${conversationId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export async function deleteChat(conversationId: string): Promise<{ ok: boolean }> {
  return apiFetchJson(`/v1/chats/${conversationId}`, { method: "DELETE" });
}
