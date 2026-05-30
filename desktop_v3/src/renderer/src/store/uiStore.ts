// SPDX-License-Identifier: AGPL-3.0-or-later
// Zustand UI 상태 — 선택된 세션 + 선택된 step (Monaco 표시 대상).
import { create } from "zustand";

// 코드 뷰어 대상: step(번호) 또는 파생 블록(Library/Initial). 셋은 상호 배타.
export type SelectedBlock = "library" | "initial" | null;

interface UiState {
  selectedSessionId: string | null;
  selectedStepId: number | null;
  selectedBlock: SelectedBlock;
  paletteOpen: boolean; // 커맨드 팔레트 (Ctrl+K, §51)
  settingsOpen: boolean; // 설정 다이얼로그 (사이드바 기어 + 팔레트 공용)
  selectSession: (id: string | null) => void;
  selectStep: (id: number | null) => void;
  selectBlock: (b: SelectedBlock) => void;
  setPaletteOpen: (v: boolean) => void;
  togglePalette: () => void;
  setSettingsOpen: (v: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  selectedSessionId: null,
  selectedStepId: null,
  selectedBlock: null,
  paletteOpen: false,
  settingsOpen: false,
  selectSession: (id) => set({ selectedSessionId: id, selectedStepId: null, selectedBlock: null }),
  selectStep: (id) => set({ selectedStepId: id, selectedBlock: null }),
  selectBlock: (b) => set({ selectedBlock: b, selectedStepId: null }),
  setPaletteOpen: (v) => set({ paletteOpen: v }),
  togglePalette: () => set((st) => ({ paletteOpen: !st.paletteOpen })),
  setSettingsOpen: (v) => set({ settingsOpen: v }),
}));
