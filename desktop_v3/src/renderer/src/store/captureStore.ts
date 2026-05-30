// SPDX-License-Identifier: AGPL-3.0-or-later
// 첨부 이미지(스크린 영역 캡처) 상태 (handoff §60, 백로그 #13).
// startCapture(): main 이 드래그 오버레이를 띄워(메인 minimize) 물리 픽셀 사각형을 받음 →
// /capture/region 으로 grab·저장 → 저장 경로를 pending images 에 추가. 다음 AI 생성 요청에
// images 로 전달돼 core generate_step(images=[...]) 이 step.captures + 멀티모달 프롬프트로 사용.
import { create } from "zustand";
import { captureRegion } from "@/api/client";
import { toast } from "@/store/toastStore";
import i18n from "@/i18n";

export interface PendingImage {
  path: string; // 저장된 PNG 절대경로 (generate images 로 전달)
  width: number;
  height: number;
}

interface CaptureState {
  capturing: boolean;
  images: PendingImage[];
  startCapture: (sessionId: string) => Promise<void>;
  removeImage: (path: string) => void;
  clear: () => void;
}

export const useCaptureStore = create<CaptureState>((set, get) => ({
  capturing: false,
  images: [],
  startCapture: async (sessionId) => {
    if (get().capturing) return;
    set({ capturing: true });
    try {
      // 드래그 오버레이 → 물리 픽셀 사각형(취소 시 null).
      const rect = await window.ohdo.captureRegion();
      if (!rect) return; // 사용자 취소 — 조용히 종료
      const result = await captureRegion(sessionId, rect);
      set((st) => ({
        images: [...st.images, { path: result.path, width: result.width, height: result.height }],
      }));
      toast.success(i18n.t("capture.saved", { w: result.width, h: result.height }));
    } catch (e) {
      toast.error(i18n.t("capture.failed", { message: (e as Error).message }));
    } finally {
      set({ capturing: false });
    }
  },
  removeImage: (path) => set((st) => ({ images: st.images.filter((im) => im.path !== path) })),
  clear: () => set({ images: [] }),
}));
