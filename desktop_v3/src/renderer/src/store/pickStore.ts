// SPDX-License-Identifier: AGPL-3.0-or-later
// element picker 상태 (handoff §40 #3) — 카운트다운 + 보류 중 element.
import { create } from "zustand";
import { pickElement, type PendingElement } from "@/api/client";

interface PickState {
  picking: boolean;
  countdown: number;
  pending: PendingElement | null;
  error: string | null;
  _run: number; // 진행 중 카운트다운 토큰 — cancel 시 무효화.
  startPick: (seconds?: number) => void;
  cancel: () => void;
  clearPending: () => void;
}

export const usePickStore = create<PickState>((set, get) => ({
  picking: false,
  countdown: 0,
  pending: null,
  error: null,
  _run: 0,
  startPick: (seconds = 3) => {
    if (get().picking) return;
    const run = get()._run + 1;
    set({ picking: true, countdown: seconds, error: null, _run: run });

    const tick = () => {
      if (get()._run !== run) return; // 취소됨
      const n = get().countdown - 1;
      if (n > 0) {
        set({ countdown: n });
        window.setTimeout(tick, 1000);
        return;
      }
      set({ countdown: 0 });
      pickElement()
        .then((res) => {
          if (get()._run !== run) return; // 캡처 도중 취소됨
          if (res.success && res.label) {
            set({
              pending: { label: res.label, isBrowser: !!res.is_browser_element },
              picking: false,
            });
          } else {
            set({ picking: false, error: res.error ?? "element 캡처 실패" });
          }
        })
        .catch((e: Error) => {
          if (get()._run === run) set({ picking: false, error: e.message });
        });
    };
    window.setTimeout(tick, 1000);
  },
  cancel: () => set((st) => ({ picking: false, countdown: 0, _run: st._run + 1 })),
  clearPending: () => set({ pending: null }),
}));
