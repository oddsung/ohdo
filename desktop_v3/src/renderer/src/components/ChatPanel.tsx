// SPDX-License-Identifier: AGPL-3.0-or-later
// 중앙 채팅/스텝 패널 — 세션 상세(steps) 표시 + 자연어 요청 → AI 코드 생성.
// 동기 요청 + 로딩 (handoff §38 결정). 생성 완료 시 step 목록/코드 뷰어 갱신.
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Circle,
  Flag,
  Loader2,
  MousePointerClick,
  Play,
  SendHorizonal,
  Square,
  X,
} from "lucide-react";
import { fetchSession, generateStep, type Step } from "@/api/client";
import { useUiStore } from "@/store/uiStore";
import { usePickStore } from "@/store/pickStore";
import { useRecordStore } from "@/store/recordStore";
import { toast } from "@/store/toastStore";
import { useExecution } from "@/hooks/useExecution";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";

function StepCard({
  step,
  onRun,
  running,
}: {
  step: Step;
  onRun: (stepId: number) => void;
  running: boolean;
}) {
  const selectStep = useUiStore((st) => st.selectStep);
  const selectedStepId = useUiStore((st) => st.selectedStepId);
  const active = selectedStepId === step.step_id;
  const statusColor =
    step.status === "completed"
      ? "text-discord-green"
      : step.status === "failed"
        ? "text-red-400"
        : "text-discord-muted";
  return (
    <div
      onClick={() => selectStep(step.step_id)}
      className={`group w-full cursor-pointer rounded-md border p-3 text-left transition-colors ${
        active
          ? "border-primary/60 bg-discord-card"
          : "border-transparent bg-discord-card/50 hover:bg-discord-card"
      }`}
    >
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-semibold text-discord-muted">STEP {step.step_id}</span>
        <div className="flex items-center gap-2">
          <span className={`text-xs ${statusColor}`}>{step.status}</span>
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6 text-discord-muted opacity-0 transition-opacity hover:text-discord-green group-hover:opacity-100"
            title="이 step 실행"
            disabled={running}
            onClick={(e) => {
              e.stopPropagation();
              onRun(step.step_id);
            }}
          >
            <Play className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
      {step.user_request && (
        <p className="text-sm text-discord-text">
          <span className="text-discord-muted">👤 </span>
          {step.user_request}
        </p>
      )}
      {step.ai_description && (
        <p className="mt-1 line-clamp-3 text-xs text-discord-muted">🤖 {step.ai_description}</p>
      )}
      {step.validation_warnings?.length > 0 && (
        <p className="mt-1 text-xs text-amber-400">⚠ 경고 {step.validation_warnings.length}건</p>
      )}
    </div>
  );
}

export function ChatPanel({ sessionId }: { sessionId: string }) {
  const qc = useQueryClient();
  const selectStep = useUiStore((st) => st.selectStep);
  const { running, run, stop } = useExecution(sessionId);
  const [input, setInput] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { data: session, isLoading } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => fetchSession(sessionId),
  });

  const { picking, pending, error: pickError, startPick, clearPending } = usePickStore();
  const {
    recording,
    eventCount,
    busy: recBusy,
    start: startRec,
    marker: addMarker,
    stopCommit: stopRec,
    cancel: cancelRec,
  } = useRecordStore();

  const genMut = useMutation({
    // pending element 는 호출 시점에 store 에서 읽어 stale closure 회피.
    mutationFn: (req: string) => generateStep(sessionId, req, usePickStore.getState().pending),
    onSuccess: (result) => {
      if (!result.success) {
        setErrorMsg(result.error ?? "AI 생성 실패");
        toast.error("AI 코드 생성 실패");
        return;
      }
      setErrorMsg(null);
      setInput("");
      toast.success(`STEP ${result.step?.step_id} 생성 완료`);
      qc.invalidateQueries({ queryKey: ["session", sessionId] });
      qc.invalidateQueries({ queryKey: ["sessions"] });
      if (result.step) selectStep(result.step.step_id);
    },
    onError: (e) => {
      setErrorMsg((e as Error).message);
      toast.error((e as Error).message);
    },
  });

  // 새 step 생성 시 맨 아래로 스크롤.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [session?.steps.length]);

  const busy = genMut.isPending;
  const submit = () => {
    const req = input.trim();
    if (req && !busy) {
      genMut.mutate(req);
      if (pending) clearPending(); // 한 요청에 한 번만 첨부
    }
  };

  return (
    <div className="flex h-full flex-1 flex-col">
      <header className="flex h-12 items-center justify-between border-b border-black/20 px-4 shadow-sm">
        <span className="truncate font-semibold">{session ? session.title : "…"}</span>
        <div className="flex items-center gap-1">
          {/* 녹화 컨트롤 — step 수와 무관하게 항상 노출 (녹화로 step 생성). */}
          {recording ? (
            <>
              <span className="mr-1 flex items-center gap-1 text-xs text-red-400">
                <Circle className="h-2.5 w-2.5 animate-pulse fill-red-500 text-red-500" />
                녹화중 · {eventCount}
              </span>
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7"
                title="구분점 추가 (step 경계)"
                disabled={recBusy}
                onClick={() => addMarker()}
              >
                <Flag className="h-3.5 w-3.5" />
              </Button>
              <Button
                size="sm"
                variant="secondary"
                className="h-7"
                disabled={recBusy}
                onClick={() =>
                  stopRec(sessionId, () =>
                    qc.invalidateQueries({ queryKey: ["session", sessionId] }),
                  )
                }
                title="녹화 종료 + 저장"
              >
                {recBusy ? (
                  <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Square className="mr-1 h-3.5 w-3.5" />
                )}
                종료
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7 text-discord-muted"
                title="녹화 취소 (저장 안 함)"
                disabled={recBusy}
                onClick={() => cancelRec()}
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-discord-muted hover:text-red-400"
              title="작업 녹화 시작 (다른 앱 조작을 step 으로 기록)"
              disabled={running}
              onClick={() => startRec(sessionId)}
            >
              <Circle className="mr-1 h-3.5 w-3.5" /> 녹화
            </Button>
          )}

          {/* 실행 컨트롤 — step 있을 때만, 녹화 중엔 숨김. */}
          {!recording &&
            session &&
            session.steps.length > 0 &&
            (running ? (
              <Button size="sm" variant="destructive" className="h-7" onClick={stop}>
                <Square className="mr-1 h-3.5 w-3.5" /> 중단
              </Button>
            ) : (
              <Button
                size="sm"
                variant="secondary"
                className="h-7"
                onClick={() => run("all", null)}
                title="전체 실행"
              >
                <Play className="mr-1 h-3.5 w-3.5" /> 전체 실행
              </Button>
            ))}
        </div>
      </header>

      <ScrollArea className="flex-1">
        <div ref={scrollRef} className="space-y-2 p-3">
          {isLoading && <p className="text-sm text-discord-muted">세션 로딩 중…</p>}
          {session && session.steps.length === 0 && (
            <p className="px-1 py-6 text-center text-sm text-discord-muted">
              아래에 자연어로 작업을 요청하면 AI 가 첫 step 코드를 생성합니다.
            </p>
          )}
          {session?.steps.map((s) => (
            <StepCard key={s.step_id} step={s} running={running} onRun={(id) => run("single", id)} />
          ))}
          {busy && (
            <div className="flex items-center gap-2 rounded-md bg-discord-card/50 p-3 text-sm text-discord-muted">
              <Loader2 className="h-4 w-4 animate-spin" />
              AI 가 코드를 생성하는 중… (agy CLI 는 10~30초 걸릴 수 있습니다)
            </div>
          )}
        </div>
      </ScrollArea>

      {errorMsg && (
        <div className="border-t border-red-900/40 bg-red-950/30 px-4 py-2 text-xs text-red-300">
          ⚠ {errorMsg}
        </div>
      )}

      {pickError && (
        <div className="border-t border-amber-900/40 bg-amber-950/20 px-4 py-1.5 text-xs text-amber-300">
          ⚠ 요소 선택: {pickError}
        </div>
      )}

      {pending && (
        <div className="flex items-center gap-2 border-t border-black/20 px-3 pt-2">
          <span className="flex max-w-full items-center gap-1 rounded-full bg-primary/20 px-2 py-1 text-xs text-discord-text">
            <MousePointerClick className="h-3 w-3 shrink-0 text-primary" />
            <span className="truncate">첨부된 요소: {pending.label.split("\n")[0].slice(0, 60)}</span>
            <button onClick={clearPending} className="ml-1 shrink-0 hover:text-white" title="첨부 제거">
              <X className="h-3 w-3" />
            </button>
          </span>
        </div>
      )}

      <div className="border-t border-black/20 p-3">
        <div className="flex items-end gap-2">
          <Button
            size="icon"
            variant="ghost"
            className="h-[60px] w-10 shrink-0 text-discord-muted hover:text-primary"
            title="UI 요소 선택 (3초 카운트다운 후 커서 위치 캡처)"
            disabled={busy || picking}
            onClick={() => startPick(3)}
          >
            <MousePointerClick className="h-5 w-5" />
          </Button>
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="작업을 자연어로 요청하세요 (Enter 전송, Shift+Enter 줄바꿈)"
            disabled={busy}
            rows={2}
          />
          <Button onClick={submit} disabled={busy || !input.trim()} size="icon" className="h-[60px] w-12">
            {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <SendHorizonal className="h-5 w-5" />}
          </Button>
        </div>
      </div>
    </div>
  );
}
