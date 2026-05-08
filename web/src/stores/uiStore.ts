import { create } from "zustand";

type UiState = {
  recipeModalId: number | null;
  setRecipeModalId: (id: number | null) => void;
};

export const useUiStore = create<UiState>((set) => ({
  recipeModalId: null,
  setRecipeModalId: (id) => set({ recipeModalId: id }),
}));
