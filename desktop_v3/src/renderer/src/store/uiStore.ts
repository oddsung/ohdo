// SPDX-License-Identifier: AGPL-3.0-or-later
// Zustand UI 상태 — 선택된 세션 + 선택된 step (Monaco 표시 대상).
import { create } from "zustand";

interface UiState {
  selectedSessionId: string | null;
  selectedStepId: number | null;
  selectSession: (id: string | null) => void;
  selectStep: (id: number | null) => void;
}

export const useUiStore = create<UiState>((set) => ({
  selectedSessionId: null,
  selectedStepId: null,
  selectSession: (id) => set({ selectedSessionId: id, selectedStepId: null }),
  selectStep: (id) => set({ selectedStepId: id }),
}));
