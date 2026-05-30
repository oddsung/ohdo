// SPDX-License-Identifier: AGPL-3.0-or-later
// WebSocket 클라이언트 — /ws/execute (실행 live 로그) + /ws/generate (AI 생성 진행상황).
// 브라우저 WebSocket 은 헤더 설정이 어려워 토큰을 쿼리 파라미터로 전달한다.
import type { GenerateResult, PendingElement, SessionDetail, Step } from "@/api/client";
import i18n from "@/i18n";

export type RunMode = "all" | "from" | "single";

export interface ExecHandlers {
  onLog: (message: string) => void;
  onStepDone: (stepId: number, result: Record<string, unknown>) => void;
  onDone: () => void;
  onError: (message: string) => void;
}

export interface ExecHandle {
  /** 실행 중단 요청 (서버에 stop 전송 + 소켓 종료). */
  stop: () => void;
}

/** /ws/execute 에 연결해 실행을 시작하고, 메시지를 핸들러로 라우팅한다. */
export async function runExecution(
  sessionId: string,
  mode: RunMode,
  stepId: number | null,
  handlers: ExecHandlers,
): Promise<ExecHandle> {
  const info = await window.ohdo.getApiInfo();
  if (!info) throw new Error(i18n.t("bridge.disconnected"));

  const wsBase = info.baseUrl.replace(/^http/, "ws");
  const params = new URLSearchParams({ token: info.token, session_id: sessionId, mode });
  if (stepId != null) params.set("step_id", String(stepId));

  const ws = new WebSocket(`${wsBase}/ws/execute?${params.toString()}`);
  let finished = false;
  const finish = () => {
    if (!finished) {
      finished = true;
      handlers.onDone();
    }
  };

  ws.onmessage = (ev) => {
    let msg: { type: string; message?: string; step_id?: number; result?: Record<string, unknown> };
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    switch (msg.type) {
      case "log":
        handlers.onLog(msg.message ?? "");
        break;
      case "step_done":
        handlers.onStepDone(msg.step_id ?? -1, msg.result ?? {});
        break;
      case "done":
        finish();
        ws.close();
        break;
      case "error":
        handlers.onError(msg.message ?? i18n.t("console.runError", { message: "" }));
        finished = true;
        ws.close();
        break;
    }
  };

  ws.onerror = () => handlers.onError(i18n.t("ws.connError"));
  ws.onclose = () => finish();

  return {
    stop: () => {
      try {
        if (ws.readyState === WebSocket.OPEN) ws.send("stop");
        ws.close();
      } catch {
        /* already closed */
      }
    },
  };
}

// ── AI 생성 진행상황 스트리밍 (handoff §44, /ws/generate) ──────────

export interface GenerateStreamHandlers {
  /** 진행상황 메시지 ("프롬프트 구성 중…" 등). */
  onProgress: (message: string) => void;
  /** 생성 완료 — GenerateResult(success/step/session/error). */
  onDone: (result: GenerateResult) => void;
  /** 연결/프로토콜 수준 오류. */
  onError: (message: string) => void;
}

/** /ws/generate 에 연결해 자연어 요청을 보내고 진행상황을 스트리밍한다. */
export async function generateStream(
  sessionId: string,
  userRequest: string,
  pending: PendingElement | null,
  handlers: GenerateStreamHandlers,
  images?: string[] | null, // 첨부 이미지 경로 (handoff §60 #13)
): Promise<void> {
  const info = await window.ohdo.getApiInfo();
  if (!info) throw new Error(i18n.t("bridge.disconnected"));

  const wsBase = info.baseUrl.replace(/^http/, "ws");
  const params = new URLSearchParams({ token: info.token, session_id: sessionId });
  const ws = new WebSocket(`${wsBase}/ws/generate?${params.toString()}`);
  let settled = false;

  ws.onopen = () => {
    ws.send(
      JSON.stringify({
        user_request: userRequest,
        element_context: pending?.label ?? null,
        is_browser_element: pending?.isBrowser ?? false,
        images: images && images.length ? images : null,
      }),
    );
  };

  ws.onmessage = (ev) => {
    let msg: {
      type: string;
      message?: string;
      success?: boolean;
      step?: Step;
      session?: SessionDetail;
      description?: string;
      error?: string;
      partial?: boolean;
    };
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (msg.type === "progress") {
      handlers.onProgress(msg.message ?? "");
    } else if (msg.type === "done") {
      settled = true;
      handlers.onDone({
        success: !!msg.success,
        step: msg.step,
        session: msg.session,
        description: msg.description,
        error: msg.error,
        partial: msg.partial,
      });
      ws.close();
    } else if (msg.type === "error") {
      settled = true;
      handlers.onError(msg.error ?? msg.message ?? i18n.t("ws.genError"));
      ws.close();
    }
  };

  ws.onerror = () => {
    if (!settled) handlers.onError(i18n.t("ws.connError"));
  };
  ws.onclose = () => {
    if (!settled) handlers.onError(i18n.t("ws.closedEarly"));
  };
}
