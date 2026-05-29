// SPDX-License-Identifier: AGPL-3.0-or-later
// element picker 상태 (handoff §49) — 투명 오버레이 + 실시간 하이라이트 + 클릭 캡처.
// startPick(): main 이 투명 오버레이 창을 띄우고(메인 윈도우 minimize) → /pick/click 이
// 사용자 클릭까지 블록 → 그동안 오버레이가 /pick/hover 를 폴링해 붉은 박스를 그린다.
// 클릭/Esc 는 전역 LL 후크(Python pick_pump)가 잡는다.
import { create } from "zustand";
import { pickElementOnClick, cancelPick, type PendingElement } from "@/api/client";
import i18n from "@/i18n";

interface PickState {
  picking: boolean;
  pending: PendingElement | null;
  error: string | null;
  startPick: () => void;
  cancelPick: () => void;
  clearPending: () => void;
}

export const usePickStore = create<PickState>((set, get) => ({
  picking: false,
  pending: null,
  error: null,
  startPick: async () => {
    if (get().picking) return;
    set({ picking: true, error: null });
    // 투명 오버레이 창 띄움(+메인 minimize). 실패해도 캡처 자체는 진행.
    await window.ohdo.startPickOverlay().catch(() => {});
    try {
      const result = await pickElementOnClick();
      if (result.success) {
        set({
          pending: { label: result.label ?? "", isBrowser: !!result.is_browser_element },
          picking: false,
        });
      } else if (result.cancelled) {
        set({ picking: false }); // 사용자 취소(Esc/타임아웃) — 조용히 종료
      } else {
        set({ picking: false, error: result.error ?? i18n.t("pick.captureFailed") });
      }
    } catch (e) {
      set({ picking: false, error: (e as Error).message });
    } finally {
      // 오버레이 닫고 메인 윈도우 복원.
      await window.ohdo.stopPickOverlay().catch(() => {});
    }
  },
  cancelPick: () => {
    if (!get().picking) return;
    void cancelPick().catch(() => {});
    void window.ohdo.stopPickOverlay().catch(() => {});
    set({ picking: false });
  },
  clearPending: () => set({ pending: null }),
}));
