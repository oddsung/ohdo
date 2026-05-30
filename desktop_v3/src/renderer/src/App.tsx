// SPDX-License-Identifier: AGPL-3.0-or-later
// Discord-like 3-column 셸: 서버 레일 + 세션 사이드바 + 채팅/스텝 + Monaco 코드 뷰어 + 콘솔.
// 전역: 단축키(useShortcuts) + 요소 선택 오버레이(PickOverlay) + 토스트(Toaster).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { createSession, fetchSession, fetchBlocks } from "./api/client";
import { useUiStore } from "./store/uiStore";
import { usePickStore } from "./store/pickStore";
import { useExecStore } from "./store/execStore";
import { toast } from "./store/toastStore";
import "./store/themeStore"; // 모듈 로드 시 테마 적용 (FOUC 방지)
import { useShortcuts } from "./hooks/useShortcuts";
import { useExecution } from "./hooks/useExecution";
import { SessionSidebar } from "./components/SessionSidebar";
import { ChatPanel } from "./components/ChatPanel";
import { CodeViewer } from "./components/CodeViewer";
import { LogConsole } from "./components/LogConsole";
import { PickOverlay } from "./components/PickOverlay";
import { Toaster } from "./components/Toaster";

function ServerRail() {
  return (
    <div className="flex h-full w-[72px] flex-col items-center gap-2 bg-discord-rail py-3">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-discord-accent text-lg font-bold text-white">
        oh
      </div>
    </div>
  );
}

function CodePane({ sessionId }: { sessionId: string }) {
  const { t } = useTranslation();
  const selectedStepId = useUiStore((st) => st.selectedStepId);
  const selectedBlock = useUiStore((st) => st.selectedBlock);
  const { data: session } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => fetchSession(sessionId),
  });
  // 블록 코드는 step 변경 시 함께 바뀌므로 updated_at 을 키에 넣어 자동 갱신.
  const { data: blocks } = useQuery({
    queryKey: ["blocks", sessionId, session?.updated_at],
    queryFn: () => fetchBlocks(sessionId),
    enabled: !!session,
  });
  const step = session?.steps.find((s) => s.step_id === selectedStepId);

  // 표시 대상 결정: 블록 선택 > step 선택. 블록은 stepId=null 로 넘겨 read-only 강제.
  let stepId: number | null = step?.step_id ?? null;
  let code = step?.generated_code ?? "";
  let title: string | undefined = step ? `STEP ${step.step_id}` : undefined;
  if (selectedBlock === "library") {
    stepId = null;
    code = blocks?.library_code ?? "";
    title = t("blocks.libraryTitle");
  } else if (selectedBlock === "initial") {
    stepId = null;
    code = blocks?.initial_code ?? "";
    title = t("blocks.initialTitle");
  }
  return (
    <div className="hidden w-[44%] min-w-[360px] flex-col border-l border-black/30 lg:flex">
      <div className="min-h-0 flex-1">
        <CodeViewer sessionId={sessionId} stepId={stepId} code={code} title={title} />
      </div>
      <LogConsole />
    </div>
  );
}

function EmptyState() {
  const { t } = useTranslation();
  return (
    <main className="flex h-full flex-1 items-center justify-center">
      <div className="text-center text-discord-muted">
        <p className="text-lg">{t("app.welcome")}</p>
        <p className="mt-2 text-sm">{t("app.pickOrCreate")}</p>
        <p className="mt-1 text-xs">{t("app.hint")}</p>
      </div>
    </main>
  );
}

export default function App() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const selectedSessionId = useUiStore((st) => st.selectedSessionId);
  const selectSession = useUiStore((st) => st.selectSession);
  const cancelPick = usePickStore((st) => st.cancelPick);

  // 전역 단축키용 실행 훅 — 세션 미선택 시 빈 문자열(핸들러에서 가드).
  const { run, stop } = useExecution(selectedSessionId ?? "");

  const newSessionMut = useMutation({
    mutationFn: () => {
      const stamp = new Date().toISOString().slice(5, 16).replace("T", " ");
      return createSession(t("sidebar.newSessionName", { stamp }));
    },
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      selectSession(s.session_id);
      toast.success(t("session.created"));
    },
    onError: (e) => toast.error(t("session.createFailed", { message: (e as Error).message })),
  });

  useShortcuts({
    onRunToggle: () => {
      if (!selectedSessionId) return;
      if (useExecStore.getState().running) stop();
      else run("all", null);
    },
    onNewSession: () => newSessionMut.mutate(),
    onEscape: () => cancelPick(),
  });

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <ServerRail />
      <SessionSidebar />
      {selectedSessionId ? (
        <>
          <ChatPanel sessionId={selectedSessionId} />
          <CodePane sessionId={selectedSessionId} />
        </>
      ) : (
        <EmptyState />
      )}
      <PickOverlay />
      <Toaster />
    </div>
  );
}
