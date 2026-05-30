// SPDX-License-Identifier: AGPL-3.0-or-later
// 작업 녹화 상태 (handoff §41 + §63 review) — start/marker/cancel + 이벤트 수 polling.
// 종료(stop)는 §63 부터 **즉시 commit 하지 않고** review 다이얼로그로: stop_preview 로
// 변환된 step 을 받아 사용자가 검토/편집/삭제 후 commit. Windows LL 후크 캡처는 Python
// 브리지(api_server)가 수행 — 여기선 호출 + 상태만.
import { create } from "zustand";
import {
  recordingStart,
  recordingStatus,
  recordingMarker,
  recordingStopPreview,
  recordingCommit,
  recordingCancel,
  type Step,
} from "@/api/client";
import { toast } from "@/store/toastStore";
import i18n from "@/i18n";

interface RecordState {
  recording: boolean;
  eventCount: number;
  busy: boolean;
  // ── review (§63) ──
  reviewOpen: boolean;
  reviewSessionId: string | null;
  previewSteps: Step[];
  start: (sessionId: string) => Promise<void>;
  marker: () => Promise<void>;
  stopReview: (sessionId: string) => Promise<void>;
  commitReview: (steps: Step[], onDone?: () => void) => Promise<void>;
  discardReview: () => void;
  cancel: () => Promise<void>;
  _poll: ReturnType<typeof setInterval> | null;
}

export const useRecordStore = create<RecordState>((set, get) => ({
  recording: false,
  eventCount: 0,
  busy: false,
  reviewOpen: false,
  reviewSessionId: null,
  previewSteps: [],
  _poll: null,

  start: async (sessionId) => {
    set({ busy: true });
    try {
      await recordingStart(sessionId);
      await window.ohdo.minimizeForRecord().catch(() => {});
      set({ recording: true, eventCount: 0 });
      const poll = setInterval(async () => {
        try {
          const st = await recordingStatus();
          set({ eventCount: st.event_count });
        } catch {
          /* ignore */
        }
      }, 1000);
      set({ _poll: poll });
    } catch (e) {
      set({ recording: false });
      toast.error(i18n.t("record.startFailed", { message: (e as Error).message }));
    } finally {
      set({ busy: false });
    }
  },

  marker: async () => {
    try {
      await recordingMarker();
      toast.success(i18n.t("record.markerAdded"));
    } catch (e) {
      toast.error(i18n.t("record.markerFailed", { message: (e as Error).message }));
    }
  },

  // 종료 → 변환된 step 을 commit 없이 받아 review 다이얼로그 오픈 (§63).
  stopReview: async (sessionId) => {
    const poll = get()._poll;
    if (poll) clearInterval(poll);
    set({ busy: true });
    try {
      const r = await recordingStopPreview(sessionId);
      // 메인 윈도우 복원 — 사용자가 review 다이얼로그를 조작해야 함.
      await window.ohdo.restoreFromRecord().catch(() => {});
      if (r.steps.length === 0) {
        set({ recording: false, eventCount: 0, _poll: null, previewSteps: [], reviewOpen: false });
        toast.info(i18n.t("review.empty"));
        return;
      }
      set({
        recording: false,
        eventCount: 0,
        _poll: null,
        previewSteps: r.steps,
        reviewSessionId: sessionId,
        reviewOpen: true,
      });
    } catch (e) {
      set({ recording: false, _poll: null });
      await window.ohdo.restoreFromRecord().catch(() => {});
      toast.error(i18n.t("record.saveFailed", { message: (e as Error).message }));
    } finally {
      set({ busy: false });
    }
  },

  // review 확정 → 편집된 step 커밋 (§63).
  commitReview: async (steps, onDone) => {
    const sessionId = get().reviewSessionId;
    if (!sessionId) return;
    set({ busy: true });
    try {
      const r = await recordingCommit(sessionId, steps);
      set({ reviewOpen: false, reviewSessionId: null, previewSteps: [] });
      toast.success(i18n.t("record.complete", { count: r.step_count }));
      onDone?.();
    } catch (e) {
      toast.error(i18n.t("record.saveFailed", { message: (e as Error).message }));
    } finally {
      set({ busy: false });
    }
  },

  // review 취소 → 커밋 없이 버림 (녹화는 이미 stop_preview 로 종료됨).
  discardReview: () => {
    set({ reviewOpen: false, reviewSessionId: null, previewSteps: [] });
    toast.info(i18n.t("review.discarded"));
  },

  cancel: async () => {
    set({ busy: true });
    try {
      await recordingCancel();
      const poll = get()._poll;
      if (poll) clearInterval(poll);
      await window.ohdo.restoreFromRecord().catch(() => {});
      set({ recording: false, eventCount: 0, _poll: null });
      toast.success(i18n.t("record.canceled"));
    } catch (e) {
      toast.error(i18n.t("record.cancelFailed", { message: (e as Error).message }));
    } finally {
      set({ busy: false });
    }
  },
}));
