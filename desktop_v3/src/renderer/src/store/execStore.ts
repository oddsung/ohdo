// SPDX-License-Identifier: AGPL-3.0-or-later
// 실행 상태 — live 로그 + 실행 중 여부 (handoff §40 #1).
import { create } from "zustand";

export interface LogLine {
  id: number;
  kind: "log" | "step_done" | "done" | "error";
  text: string;
}

interface ExecState {
  running: boolean;
  logs: LogLine[];
  consoleOpen: boolean;
  _seq: number;
  setRunning: (v: boolean) => void;
  appendLog: (kind: LogLine["kind"], text: string) => void;
  clearLogs: () => void;
  toggleConsole: (open?: boolean) => void;
}

export const useExecStore = create<ExecState>((set) => ({
  running: false,
  logs: [],
  consoleOpen: true,
  _seq: 0,
  setRunning: (v) => set({ running: v }),
  appendLog: (kind, text) =>
    set((st) => ({
      _seq: st._seq + 1,
      logs: [...st.logs, { id: st._seq + 1, kind, text }].slice(-500),
      consoleOpen: true,
    })),
  clearLogs: () => set({ logs: [] }),
  toggleConsole: (open) => set((st) => ({ consoleOpen: open ?? !st.consoleOpen })),
}));
