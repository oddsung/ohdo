// SPDX-License-Identifier: AGPL-3.0-or-later
// Phase B — Discord-like 3-column 셸: 서버 레일 + 세션 사이드바 + 채팅/스텝 + Monaco 코드 뷰어.
// AI 코드 생성 루프(§37 검증 목표 "코드 생성 → 화면 표시")가 동작한다.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createSession, fetchSession } from "./api/client";
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
  const selectedStepId = useUiStore((st) => st.selectedStepId);
  const { data: session } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => fetchSession(sessionId),
  });
  const step = session?.steps.find((s) => s.step_id === selectedStepId);
  return (
    <div className="hidden w-[44%] min-w-[360px] flex-col border-l border-black/30 lg:flex">
      <div className="min-h-0 flex-1">
        <CodeViewer
          sessionId={sessionId}
          stepId={step?.step_id ?? null}
          code={step?.generated_code ?? ""}
          title={step ? `STEP ${step.step_id}` : undefined}
        />
      </div>
      <LogConsole />
    </div>
  );
}

function EmptyState() {
  return (
    <main className="flex h-full flex-1 items-center justify-center">
      <div className="text-center text-discord-muted">
        <p className="text-lg">👋 ohdo desktop_v3 (Phase B)</p>
        <p className="mt-2 text-sm">왼쪽에서 세션을 선택하거나 + 로 새로 만드세요.</p>
        <p className="mt-1 text-xs">
          세션을 열고 자연어로 작업을 요청하면 AI 가 Python 자동화 코드를 생성합니다.
        </p>
      </div>
    </main>
  );
}

export default function App() {
  const selectedSessionId = useUiStore((st) => st.selectedSessionId);

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
    </div>
  );
}
