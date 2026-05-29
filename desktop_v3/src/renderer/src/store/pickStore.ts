// SPDX-License-Identifier: AGPL-3.0-or-later
// element picker 상태 (handoff §48, 절충안) — 클릭 시 캡처. 카운트다운/하이라이트 없음.
// startPick() 가 /pick/click 을 호출하면 사용자가 대상을 클릭할 때까지 백엔드가 블록한다.
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
    try {
      const result = await pickElementOnClick();
      if (result.success) {
        set({
          pending: { label: result.label ?? "", isBrowser: !!result.is_browser_element },
          picking: false,
        });
      } else if (result.cancelled) {
        set({ picking: false }); // 사용자 취소 — 조용히 종료
      } else {
        set({ picking: false, error: result.error ?? i18n.t("pick.captureFailed") });
      }
    } catch (e) {
      set({ picking: false, error: (e as Error).message });
    }
  },
  cancelPick: () => {
    if (!get().picking) return;
    void cancelPick().catch(() => {});
    set({ picking: false });
  },
  clearPending: () => set({ pending: null }),
}));
