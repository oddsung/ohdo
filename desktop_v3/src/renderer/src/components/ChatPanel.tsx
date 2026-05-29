// SPDX-License-Identifier: AGPL-3.0-or-later
// 중앙 채팅/스텝 패널 — 세션 상세(steps) 표시 + 자연어 요청 → AI 코드 생성.
// AI 생성은 /ws/generate 진행상황 스트리밍 (handoff §44). 완료 시 step 목록/코드 뷰어 갱신.
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
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
import { fetchSession, type GenerateResult, type Step } from "@/api/client";
import { generateStream } from "@/api/ws";
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
  const { t } = useTranslation();
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
            title={t("chat.runThisStep")}
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
        <p className="mt-1 text-xs text-amber-400">
          {t("chat.stepWarn", { count: step.validation_warnings.length })}
        </p>
      )}
    </div>
  );
}

export function ChatPanel({ sessionId }: { sessionId: string }) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const selectStep = useUiStore((st) => st.selectStep);
  const { running, run, stop } = useExecution(sessionId);
  const [input, setInput] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [progress, setProgress] = useState("");
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
    // 진행상황 스트리밍 (handoff §44, /ws/generate). generateStream 을 Promise 로 감싸
    // onProgress 는 setProgress 로 라이브 표시, onDone/onError 로 resolve/reject.
    // pending element 는 호출 시점에 store 에서 읽어 stale closure 회피.
    mutationFn: (req: string) =>
      new Promise<GenerateResult>((resolve, reject) => {
        setProgress("");
        generateStream(sessionId, req, usePickStore.getState().pending, {
          onProgress: (m) => setProgress(m),
          onDone: (result) => resolve(result),
          onError: (msg) => reject(new Error(msg)),
        }).catch(reject);
      }),
    onSettled: () => setProgress(""),
    onSuccess: (result) => {
      if (!result.success) {
        setErrorMsg(result.error ?? t("chat.genFailed"));
        toast.error(t("chat.genFailed"));
        return;
      }
      setErrorMsg(null);
      setInput("");
      toast.success(t("chat.stepCreated", { id: result.step?.step_id }));
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
                {t("chat.recording", { count: eventCount })}
              </span>
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7"
                title={t("chat.addMarkerTitle")}
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
                title={t("chat.recordStopTitle")}
              >
                {recBusy ? (
                  <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Square className="mr-1 h-3.5 w-3.5" />
                )}
                {t("chat.recordStop")}
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7 text-discord-muted"
                title={t("chat.recordCancelTitle")}
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
              title={t("chat.recordStartTitle")}
              disabled={running}
              onClick={() => startRec(sessionId)}
            >
              <Circle className="mr-1 h-3.5 w-3.5" /> {t("chat.record")}
            </Button>
          )}

          {/* 실행 컨트롤 — step 있을 때만, 녹화 중엔 숨김. */}
          {!recording &&
            session &&
            session.steps.length > 0 &&
            (running ? (
              <Button size="sm" variant="destructive" className="h-7" onClick={stop}>
                <Square className="mr-1 h-3.5 w-3.5" /> {t("chat.stop")}
              </Button>
            ) : (
              <Button
                size="sm"
                variant="secondary"
                className="h-7"
                onClick={() => run("all", null)}
                title={t("chat.runAll")}
              >
                <Play className="mr-1 h-3.5 w-3.5" /> {t("chat.runAll")}
              </Button>
            ))}
        </div>
      </header>

      <ScrollArea className="flex-1">
        <div ref={scrollRef} className="space-y-2 p-3">
          {isLoading && <p className="text-sm text-discord-muted">{t("chat.loadingSession")}</p>}
          {session && session.steps.length === 0 && (
            <p className="px-1 py-6 text-center text-sm text-discord-muted">{t("chat.emptyHint")}</p>
          )}
          {session?.steps.map((s) => (
            <StepCard key={s.step_id} step={s} running={running} onRun={(id) => run("single", id)} />
          ))}
          {busy && (
            <div className="flex items-center gap-2 rounded-md bg-discord-card/50 p-3 text-sm text-discord-muted">
              <Loader2 className="h-4 w-4 animate-spin" />
              {progress || t("chat.generatingDefault")}
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
          {t("chat.pickPrefix", { message: pickError })}
        </div>
      )}

      {pending && (
        <div className="flex items-center gap-2 border-t border-black/20 px-3 pt-2">
          <span className="flex max-w-full items-center gap-1 rounded-full bg-primary/20 px-2 py-1 text-xs text-discord-text">
            <MousePointerClick className="h-3 w-3 shrink-0 text-primary" />
            <span className="truncate">
              {t("chat.attached", { label: pending.label.split("\n")[0].slice(0, 60) })}
            </span>
            <button
              onClick={clearPending}
              className="ml-1 shrink-0 hover:text-white"
              title={t("chat.removeAttach")}
            >
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
            title={t("chat.pickElementTitle")}
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
            placeholder={t("chat.placeholder")}
            disabled={busy}
            rows={2}
          />
          <Button
            onClick={submit}
            disabled={busy || !input.trim()}
            size="icon"
            className="h-[60px] w-12"
          >
            {busy ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <SendHorizonal className="h-5 w-5" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
