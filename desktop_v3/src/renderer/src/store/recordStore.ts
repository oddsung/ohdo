// SPDX-License-Identifier: AGPL-3.0-or-later
// 작업 녹화 상태 (handoff §41 #3). recorder 는 서버(브리지)에서 글로벌 입력 훅으로
// 이벤트를 누적하므로, 프런트는 status 를 polling 해서 event_count 만 표시한다.
import { create } from "zustand";
import {
  recordingCancel,
  recordingMarker,
  recordingStart,
  recordingStatus,
  recordingStopCommit,
} from "@/api/client";
import { toast } from "@/store/toastStore";

interface RecordState {
  recording: boolean;
  eventCount: number;
  busy: boolean; // start/stop 처리 중
  _poll: number | null;
  start: (sessionId: string) => Promise<void>;
  marker: () => Promise<void>;
  stopCommit: (sessionId: string, onCommitted?: () => void) => Promise<void>;
  cancel: () => Promise<void>;
}

export const useRecordStore = create<RecordState>((set, get) => ({
  recording: false,
  eventCount: 0,
  busy: false,
  _poll: null,

  start: async (sessionId) => {
    if (get().recording || get().busy) return;
    set({ busy: true });
    try {
      await recordingStart(sessionId);
      set({ recording: true, eventCount: 0 });
      toast.success("녹화 시작 — 대상 앱에서 작업하세요");
      const poll = window.setInterval(async () => {
        try {
          const st = await recordingStatus();
          set({ eventCount: st.event_count, recording: st.is_recording });
          if (!st.is_recording) {
            const id = get()._poll;
            if (id) window.clearInterval(id);
            set({ _poll: null });
          }
        } catch {
          /* 일시 오류 무시 */
        }
      }, 1000);
      set({ _poll: poll });
    } catch (e) {
      toast.error(`녹화 시작 실패: ${(e as Error).message}`);
    } finally {
      set({ busy: false });
    }
  },

  marker: async () => {
    try {
      await recordingMarker();
      toast.info("구분점 추가됨");
    } catch (e) {
      toast.error(`구분점 실패: ${(e as Error).message}`);
    }
  },

  stopCommit: async (sessionId, onCommitted) => {
    if (!get().recording || get().busy) return;
    set({ busy: true });
    const id = get()._poll;
    if (id) window.clearInterval(id);
    set({ _poll: null });
    try {
      const res = await recordingStopCommit(sessionId);
      set({ recording: false, eventCount: 0 });
      toast.success(`녹화 완료 — step ${res.step_count}개 추가`);
      onCommitted?.();
    } catch (e) {
      set({ recording: false });
      toast.error(`녹화 저장 실패: ${(e as Error).message}`);
    } finally {
      set({ busy: false });
    }
  },

  cancel: async () => {
    const id = get()._poll;
    if (id) window.clearInterval(id);
    set({ _poll: null });
    try {
      await recordingCancel();
    } catch {
      /* best-effort */
    }
    set({ recording: false, eventCount: 0, busy: false });
    toast.info("녹화 취소됨");
  },
}));
