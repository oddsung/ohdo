// SPDX-License-Identifier: AGPL-3.0-or-later
// IDE 셸 (§78): 상단 커스텀 타이틀바(로고+메뉴+세션탭+유틸, WCO) 아래 Discord-like
// 컬럼 — 세션 사이드바 + 채팅/스텝 + Monaco 코드 뷰어 + 콘솔. 구 좌측 ServerRail(§59)의
// 유틸은 타이틀바로 이전. 전역: 단축키(useShortcuts) + PickOverlay + Toaster.
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";
import { fetchSession, fetchBlocks } from "./api/client";
import { buttonVariants } from "./components/ui/button";
import { useUiStore } from "./store/uiStore";
import { usePickStore } from "./store/pickStore";
import { useExecStore } from "./store/execStore";
import "./store/themeStore"; // 모듈 로드 시 테마 적용 (FOUC 방지)
import { useShortcuts } from "./hooks/useShortcuts";
import { useExecution } from "./hooks/useExecution";
import { SessionSidebar } from "./components/SessionSidebar";
import { ChatPanel } from "./components/ChatPanel";
import { CodeViewer } from "./components/CodeViewer";
import { LogConsole } from "./components/LogConsole";
import { PickOverlay } from "./components/PickOverlay";
import { CommandPalette } from "./components/CommandPalette";
import { OnboardingWizard, shouldShowOnboarding } from "./components/OnboardingWizard";
import { RecordingReviewDialog } from "./components/RecordingReviewDialog";
import { TitleBar } from "./components/TitleBar";
import { Toaster } from "./components/Toaster";
import { UpdateNotice } from "./components/UpdateNotice";
import { NewSessionDialog } from "./components/NewSessionDialog";

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
  // §73: step 은 누적 generated_code(이전 step 전부 + import) 대신 **그 step 의 코드만**
  // (step_code = 실행 델타, v2 의 블록 단위 표시와 동등). step_code 가 비면 generated_code 폴백.
  let stepId: number | null = step?.step_id ?? null;
  let code = step?.step_code || step?.generated_code || "";
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

function EmptyState({ onCreate }: { onCreate: () => void }) {
  const { t } = useTranslation();
  return (
    <main className="flex h-full flex-1 items-center justify-center">
      <div className="flex flex-col items-center text-center text-discord-muted">
        <p className="text-lg">{t("app.welcome")}</p>
        <p className="mt-2 text-sm">{t("app.pickOrCreate")}</p>
        <p className="mt-1 text-xs">{t("app.hint")}</p>
        {/* 빈 상태에서도 곧장 시작할 수 있는 1차 행동 — 이름 입력 다이얼로그(§89)를 연다. */}
        <button
          type="button"
          data-testid="empty-create-session"
          onClick={onCreate}
          className={buttonVariants({ className: "mt-5" })}
        >
          <Plus className="h-4 w-4" />
          {t("app.createSession")}
        </button>
      </div>
    </main>
  );
}

export default function App() {
  const selectedSessionId = useUiStore((st) => st.selectedSessionId);
  const togglePalette = useUiStore((st) => st.togglePalette);
  const onboardingOpen = useUiStore((st) => st.onboardingOpen);
  const setOnboardingOpen = useUiStore((st) => st.setOnboardingOpen);
  const cancelPick = usePickStore((st) => st.cancelPick);

  // 첫 실행이면 온보딩 위저드 자동 오픈 (localStorage 플래그로 1회만).
  useEffect(() => {
    if (shouldShowOnboarding()) setOnboardingOpen(true);
  }, [setOnboardingOpen]);

  // 전역 단축키용 실행 훅 — 세션 미선택 시 빈 문자열(핸들러에서 가드).
  const { run, stop } = useExecution(selectedSessionId ?? "");

  // 새 세션은 이름 입력 다이얼로그(§89)를 거친다 — 생성 로직은 NewSessionDialog 내부.
  const newSessionOpen = useUiStore((st) => st.newSessionOpen);
  const setNewSessionOpen = useUiStore((st) => st.setNewSessionOpen);

  useShortcuts({
    onRunToggle: () => {
      if (!selectedSessionId) return;
      if (useExecStore.getState().running) stop();
      else run("all", null);
    },
    onNewSession: () => setNewSessionOpen(true),
    onEscape: () => cancelPick(),
    onCommandPalette: () => togglePalette(),
  });

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden">
      <TitleBar onNewSession={() => setNewSessionOpen(true)} />
      <div className="flex min-h-0 flex-1">
        <SessionSidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          {selectedSessionId ? (
            <div className="flex min-h-0 flex-1">
              <ChatPanel sessionId={selectedSessionId} />
              <CodePane sessionId={selectedSessionId} />
            </div>
          ) : (
            <EmptyState onCreate={() => setNewSessionOpen(true)} />
          )}
        </div>
      </div>
      {newSessionOpen && <NewSessionDialog />}
      <PickOverlay />
      <CommandPalette />
      {onboardingOpen && <OnboardingWizard onClose={() => setOnboardingOpen(false)} />}
      <RecordingReviewDialog />
      <Toaster />
      <UpdateNotice />
    </div>
  );
}
