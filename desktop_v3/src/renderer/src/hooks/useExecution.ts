// SPDX-License-Identifier: AGPL-3.0-or-later
// 실행 오케스트레이션 훅 — WS 실행 시작/중단 + 로그 스토어 + 완료 시 세션 invalidate.
import { useCallback, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { runExecution, type ExecHandle, type RunMode } from "@/api/ws";
import { useExecStore } from "@/store/execStore";
import { toast } from "@/store/toastStore";

export function useExecution(sessionId: string) {
  const qc = useQueryClient();
  const handleRef = useRef<ExecHandle | null>(null);
  const { running, setRunning, appendLog, clearLogs } = useExecStore();

  const run = useCallback(
    async (mode: RunMode, stepId: number | null) => {
      if (useExecStore.getState().running) return;
      clearLogs();
      setRunning(true);
      appendLog("log", `▶ 실행 시작 (${mode}${stepId != null ? ` step ${stepId}` : ""})`);
      try {
        handleRef.current = await runExecution(sessionId, mode, stepId, {
          onLog: (m) => appendLog("log", m),
          onStepDone: (sid, r) =>
            appendLog(
              "step_done",
              `✓ STEP ${sid} ${r.success ? "성공" : "실패"}${r.error ? ` — ${r.error}` : ""}`,
            ),
          onError: (m) => {
            appendLog("error", `⚠ ${m}`);
            toast.error(`실행 오류: ${m}`);
            setRunning(false);
            qc.invalidateQueries({ queryKey: ["session", sessionId] });
          },
          onDone: () => {
            if (useExecStore.getState().running) {
              appendLog("done", "■ 실행 종료");
              toast.success("실행 완료");
            }
            setRunning(false);
            qc.invalidateQueries({ queryKey: ["session", sessionId] });
            qc.invalidateQueries({ queryKey: ["sessions"] });
          },
        });
      } catch (e) {
        appendLog("error", `⚠ ${(e as Error).message}`);
        setRunning(false);
      }
    },
    [sessionId, appendLog, clearLogs, setRunning, qc],
  );

  const stop = useCallback(() => {
    handleRef.current?.stop();
    appendLog("log", "■ 중단 요청…");
    setRunning(false);
  }, [appendLog, setRunning]);

  return { running, run, stop };
}
