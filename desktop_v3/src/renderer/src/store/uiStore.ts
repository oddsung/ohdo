// SPDX-License-Identifier: AGPL-3.0-or-later
// Zustand UI 상태 — 선택된 세션 + 선택된 step (Monaco 표시 대상).
import { create } from "zustand";

// 코드 뷰어 대상: step(번호) 또는 파생 블록(Library/Initial). 셋은 상호 배타.
export type SelectedBlock = "library" | "initial" | null;

interface UiState {
  selectedSessionId: string | null;
  selectedStepId: number | null;
  selectedBlock: SelectedBlock;
  selectSession: (id: string | null) => void;
  selectStep: (id: number | null) => void;
  selectBlock: (b: SelectedBlock) => void;
}

export const useUiStore = create<UiState>((set) => ({
  selectedSessionId: null,
  selectedStepId: null,
  selectedBlock: null,
  selectSession: (id) => set({ selectedSessionId: id, selectedStepId: null, selectedBlock: null }),
  selectStep: (id) => set({ selectedStepId: id, selectedBlock: null }),
  selectBlock: (b) => set({ selectedBlock: b, selectedStepId: null }),
}));
