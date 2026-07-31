// SPDX-License-Identifier: AGPL-3.0-or-later
// 실행 오케스트레이션 훅 — WS 실행 시작/중단 + 로그 스토어 + 완료 시 세션 invalidate.
import { useCallback, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { runExecution, type ExecHandle, type RunMode } from "@/api/ws";
import { useExecStore } from "@/store/execStore";
import { toast } from "@/store/toastStore";
import i18n from "@/i18n";

export function useExecution(sessionId: string) {
  const qc = useQueryClient();
  const handleRef = useRef<ExecHandle | null>(null);
  const { running, setRunning, appendLog, clearLogs } = useExecStore();

  const run = useCallback(
    async (mode: RunMode, stepId: number | null) => {
      if (useExecStore.getState().running) return;
      clearLogs();
      setRunning(true);
      appendLog(
        "log",
        i18n.t("console.runStart", { mode, step: stepId != null ? ` step ${stepId}` : "" }),
      );
      // 실행 FX (§79) — 화면 테두리/HUD/커서 링/클릭 리플 오버레이 시작 + 진행 보고.
      // total: 전체 실행이면 세션 step 수(캐시), 단일이면 1. 실패해도 실행엔 영향 없음.
      const cached = qc.getQueryData<{ steps?: unknown[] }>(["session", sessionId]);
      const fxTotal = mode === "all" ? (cached?.steps?.length ?? 0) : 1;
      let fxDone = 0;
      const fxProgress = () =>
        void window.ohdo
          .runFxProgress({
            current: fxDone,
            total: fxTotal,
            label: i18n.t("runfx.hud", { done: fxDone, total: fxTotal || "?" }),
          })
          .catch(() => {});
      void window.ohdo.runFxStart().catch(() => {});
      fxProgress();
      try {
        handleRef.current = await runExecution(sessionId, mode, stepId, {
          onLog: (m) => appendLog("log", m),
          onStepDone: (sid, r) => {
            fxDone += 1;
            fxProgress();
            appendLog(
              "step_done",
              i18n.t("console.stepResult", {
                id: sid,
                status: r.success ? i18n.t("console.success") : i18n.t("console.fail"),
                error: r.error ? ` — ${r.error}` : "",
              }),
            );
          },
          onError: (m) => {
            appendLog("error", `⚠ ${m}`);
            toast.error(i18n.t("console.runError", { message: m }));
            setRunning(false);
            void window.ohdo.runFxStop({ success: false }).catch(() => {});
            qc.invalidateQueries({ queryKey: ["session", sessionId] });
            // 실행된 코드가 띄운 대상 앱이 포커스를 가져갔으므로 ohdo 창을 앞으로 (§49).
            void window.ohdo.focusMainWindow().catch(() => {});
          },
          onDone: () => {
            if (useExecStore.getState().running) {
              appendLog("done", i18n.t("console.runEnd"));
              toast.success(i18n.t("console.runComplete"));
            }
            setRunning(false);
            void window.ohdo.runFxStop({ success: true }).catch(() => {});
            qc.invalidateQueries({ queryKey: ["session", sessionId] });
            qc.invalidateQueries({ queryKey: ["sessions"] });
            // 실행된 코드가 띄운 대상 앱이 포커스를 가져갔으므로 ohdo 창을 앞으로 (§49).
            void window.ohdo.focusMainWindow().catch(() => {});
          },
        });
      } catch (e) {
        appendLog("error", `⚠ ${(e as Error).message}`);
        setRunning(false);
        void window.ohdo.runFxStop({ success: false }).catch(() => {});
      }
    },
    [sessionId, appendLog, clearLogs, setRunning, qc],
  );

  const stop = useCallback(() => {
    handleRef.current?.stop();
    appendLog("log", i18n.t("console.stopReq"));
    setRunning(false);
    // 수동 중지 — 성공/실패 플래시 없이 오버레이 정리.
    void window.ohdo.runFxStop({ success: null }).catch(() => {});
  }, [appendLog, setRunning]);

  return { running, run, stop };
}
