// SPDX-License-Identifier: AGPL-3.0-or-later
// Zustand UI 상태 — 선택된 세션 + 선택된 step (Monaco 표시 대상).
import { create } from "zustand";

// 코드 뷰어 대상: step(번호) 또는 파생 블록(Library/Initial). 셋은 상호 배타.
export type SelectedBlock = "library" | "initial" | null;

interface UiState {
  selectedSessionId: string | null;
  selectedStepId: number | null;
  selectedBlock: SelectedBlock;
  openTabs: string[]; // 열린 세션 탭 (§57, 멀티탭) — 순서 유지
  paletteOpen: boolean; // 커맨드 팔레트 (Ctrl+K, §51)
  settingsOpen: boolean; // 설정 다이얼로그 (사이드바 기어 + 팔레트 공용)
  envOpen: boolean; // 환경 점검 다이얼로그 (§53, 사이드바 + 팔레트 공용)
  onboardingOpen: boolean; // 온보딩 위저드 (§58, 사이드바 + 팔레트 + 첫 실행 자동)
  secretsOpen: boolean; // 시크릿 볼트 다이얼로그 (§61, 레일 + 팔레트)
  newSessionOpen: boolean; // 새 세션 이름 입력 다이얼로그 (§89 — 사이드바/메뉴/팔레트/빈화면 공용)
  selectSession: (id: string | null) => void;
  selectStep: (id: number | null) => void;
  selectBlock: (b: SelectedBlock) => void;
  closeTab: (id: string) => void;
  setPaletteOpen: (v: boolean) => void;
  togglePalette: () => void;
  setSettingsOpen: (v: boolean) => void;
  setEnvOpen: (v: boolean) => void;
  setOnboardingOpen: (v: boolean) => void;
  setSecretsOpen: (v: boolean) => void;
  setNewSessionOpen: (v: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  selectedSessionId: null,
  selectedStepId: null,
  selectedBlock: null,
  openTabs: [],
  paletteOpen: false,
  settingsOpen: false,
  envOpen: false,
  onboardingOpen: false,
  secretsOpen: false,
  newSessionOpen: false,
  // 세션 선택 시 탭에 없으면 추가(끝에) + 활성화. null 이면 활성만 해제(탭 유지).
  selectSession: (id) =>
    set((st) => {
      if (id == null) {
        return { selectedSessionId: null, selectedStepId: null, selectedBlock: null };
      }
      const openTabs = st.openTabs.includes(id) ? st.openTabs : [...st.openTabs, id];
      return { selectedSessionId: id, selectedStepId: null, selectedBlock: null, openTabs };
    }),
  selectStep: (id) => set({ selectedStepId: id, selectedBlock: null }),
  selectBlock: (b) => set({ selectedBlock: b, selectedStepId: null }),
  // 탭 닫기 — 활성 탭이면 인접 탭으로 전환(없으면 null). 비활성 탭이면 활성 유지.
  closeTab: (id) =>
    set((st) => {
      const idx = st.openTabs.indexOf(id);
      if (idx === -1) return st;
      const openTabs = st.openTabs.filter((t) => t !== id);
      if (st.selectedSessionId !== id) return { openTabs };
      const next = openTabs[Math.min(idx, openTabs.length - 1)] ?? null;
      return { openTabs, selectedSessionId: next, selectedStepId: null, selectedBlock: null };
    }),
  setPaletteOpen: (v) => set({ paletteOpen: v }),
  togglePalette: () => set((st) => ({ paletteOpen: !st.paletteOpen })),
  setSettingsOpen: (v) => set({ settingsOpen: v }),
  setEnvOpen: (v) => set({ envOpen: v }),
  setOnboardingOpen: (v) => set({ onboardingOpen: v }),
  setSecretsOpen: (v) => set({ secretsOpen: v }),
  setNewSessionOpen: (v) => set({ newSessionOpen: v }),
}));
