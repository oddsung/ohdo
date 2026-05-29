// SPDX-License-Identifier: AGPL-3.0-or-later
// 경량 토스트 시스템 (handoff §40 #4) — 외부 의존 없이 zustand 로.
import { create } from "zustand";

export type ToastKind = "success" | "error" | "info";

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastState {
  toasts: Toast[];
  _seq: number;
  push: (kind: ToastKind, message: string, ttlMs?: number) => void;
  dismiss: (id: number) => void;
}

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],
  _seq: 0,
  push: (kind, message, ttlMs = 3500) => {
    const id = get()._seq + 1;
    set((st) => ({ _seq: id, toasts: [...st.toasts, { id, kind, message }] }));
    window.setTimeout(() => get().dismiss(id), ttlMs);
  },
  dismiss: (id) => set((st) => ({ toasts: st.toasts.filter((t) => t.id !== id) })),
}));

/** 컴포넌트 밖(스토어/훅)에서 호출용 헬퍼. */
export const toast = {
  success: (m: string) => useToastStore.getState().push("success", m),
  error: (m: string) => useToastStore.getState().push("error", m),
  info: (m: string) => useToastStore.getState().push("info", m),
};
