// SPDX-License-Identifier: AGPL-3.0-or-later
// 중앙 채팅/스텝 패널 — 세션 상세(steps) 표시 + 자연어 요청 → AI 코드 생성.
// AI 생성은 /ws/generate 진행상황 스트리밍 (handoff §44). 완료 시 step 목록/코드 뷰어 갱신.
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Bot,
  ChevronsDown,
  Circle,
  Cog,
  Camera,
  Flag,
  ImageIcon,
  Library,
  Loader2,
  MousePointerClick,
  Play,
  Plus,
  RefreshCw,
  SendHorizonal,
  Square,
  Trash2,
  User,
  X,
} from "lucide-react";
import {
  fetchSession,
  fetchBlocks,
  deleteStep,
  moveStep,
  insertStep,
  regenerateStep,
  scanSecrets,
  type GenerateResult,
  type Step,
} from "@/api/client";
import { generateStream } from "@/api/ws";
import { useUiStore } from "@/store/uiStore";
import { usePickStore } from "@/store/pickStore";
import { useCaptureStore } from "@/store/captureStore";
import { useRecordStore } from "@/store/recordStore";
import { toast } from "@/store/toastStore";
import { useExecution } from "@/hooks/useExecution";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EngineSwitcher } from "@/components/EngineSwitcher";
import { SecretAutocomplete } from "@/components/SecretAutocomplete";

interface StepCardProps {
  step: Step;
  running: boolean;
  busy: boolean;
  regenerating: boolean;
  isFirst: boolean;
  isLast: boolean;
  onRun: (stepId: number) => void;
  onRunFrom: (stepId: number) => void;
  onRegenerate: (stepId: number) => void;
  onMove: (stepId: number, dir: "up" | "down") => void;
  onInsert: (stepId: number) => void;
  onDelete: (stepId: number) => void;
}

/** step 카드 액션 아이콘 (div onClick 안에 중첩, stopPropagation). */
function CardAction({
  title,
  onClick,
  disabled,
  danger,
  children,
}: {
  title: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Button
      size="icon"
      variant="ghost"
      className={`h-6 w-6 text-discord-muted ${danger ? "hover:text-red-400" : "hover:text-white"}`}
      title={title}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      {children}
    </Button>
  );
}

/** Library/Initial 파생 블록 카드 (§47 #11) — 선택 시 CodeViewer 에 read-only 표시. */
function BlockCard({ kind, active, onSelect }: { kind: "library" | "initial"; active: boolean; onSelect: () => void }) {
  const { t } = useTranslation();
  const Icon = kind === "library" ? Library : Cog;
  return (
    <div
      onClick={onSelect}
      className={`flex w-full cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-left transition-colors ${
        active
          ? "border-primary/60 bg-discord-card"
          : "border-transparent bg-discord-card/40 hover:bg-discord-card"
      }`}
    >
      <Icon className="h-4 w-4 shrink-0 text-discord-muted" />
      <div className="min-w-0">
        <div className="text-sm font-medium text-discord-text">{t(`blocks.${kind}`)}</div>
        <div className="truncate text-xs text-discord-muted">{t(`blocks.${kind}Desc`)}</div>
      </div>
    </div>
  );
}

function StepCard({
  step,
  running,
  busy,
  regenerating,
  isFirst,
  isLast,
  onRun,
  onRunFrom,
  onRegenerate,
  onMove,
  onInsert,
  onDelete,
}: StepCardProps) {
  const { t } = useTranslation();
  const selectStep = useUiStore((st) => st.selectStep);
  const selectedStepId = useUiStore((st) => st.selectedStepId);
  const active = selectedStepId === step.step_id;
  const warnings = step.validation_warnings ?? [];
  const pkgs = step.required_packages ?? [];
  const blocked = running || busy || regenerating;
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
      <div className="mb-1 flex items-center justify-between gap-1">
        <span className="text-xs font-semibold text-discord-muted">STEP {step.step_id}</span>
        <div className="flex items-center gap-1">
          <span className={`mr-1 text-xs ${statusColor}`}>{step.status}</span>
          {(busy || regenerating) && (
            <Loader2 className="h-3 w-3 animate-spin text-discord-muted" />
          )}
          <div className="flex items-center opacity-0 transition-opacity group-hover:opacity-100">
            <CardAction title={t("chat.runThisStep")} onClick={() => onRun(step.step_id)} disabled={blocked}>
              <Play className="h-3.5 w-3.5" />
            </CardAction>
            <CardAction title={t("chat.runFromHere")} onClick={() => onRunFrom(step.step_id)} disabled={blocked}>
              <ChevronsDown className="h-3.5 w-3.5" />
            </CardAction>
            <CardAction title={t("chat.regenerate")} onClick={() => onRegenerate(step.step_id)} disabled={blocked}>
              <RefreshCw className="h-3.5 w-3.5" />
            </CardAction>
            <CardAction title={t("chat.moveUp")} onClick={() => onMove(step.step_id, "up")} disabled={blocked || isFirst}>
              <ArrowUp className="h-3.5 w-3.5" />
            </CardAction>
            <CardAction title={t("chat.moveDown")} onClick={() => onMove(step.step_id, "down")} disabled={blocked || isLast}>
              <ArrowDown className="h-3.5 w-3.5" />
            </CardAction>
            <CardAction title={t("chat.insertAfter")} onClick={() => onInsert(step.step_id)} disabled={blocked}>
              <Plus className="h-3.5 w-3.5" />
            </CardAction>
            <CardAction title={t("chat.deleteStep")} onClick={() => onDelete(step.step_id)} disabled={blocked} danger>
              <Trash2 className="h-3.5 w-3.5" />
            </CardAction>
          </div>
        </div>
      </div>
      {step.user_request && (
        <p className="flex items-start gap-1.5 text-sm text-discord-text">
          <User className="mt-0.5 h-3.5 w-3.5 shrink-0 text-discord-muted" />
          <span>{step.user_request}</span>
        </p>
      )}
      {/* AI 설명은 기본 숨김 (사용자 요청) — step 을 선택했을 때만 표시. */}
      {active && step.ai_description && (
        <p className="mt-1 flex items-start gap-1.5 text-xs text-discord-muted">
          <Bot className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span className="line-clamp-3">{step.ai_description}</span>
        </p>
      )}
      {warnings.length > 0 && (
        <p className="mt-1 flex items-center gap-1 text-xs text-amber-400">
          <AlertTriangle className="h-3 w-3" />
          {t("chat.stepWarn", { count: warnings.length })}
        </p>
      )}
      {active && pkgs.length > 0 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          <span className="text-[10px] uppercase tracking-wide text-discord-muted">
            {t("chat.packages")}
          </span>
          {pkgs.map((p) => (
            <span
              key={p}
              className="rounded bg-black/30 px-1.5 py-0.5 font-mono text-[10px] text-discord-text"
            >
              {p}
            </span>
          ))}
        </div>
      )}
      {active && warnings.length > 0 && (
        <div className="mt-1.5 rounded border border-amber-500/30 bg-amber-500/5 p-1.5">
          <div className="mb-0.5 text-[11px] font-medium text-amber-400">
            {t("chat.warningsTitle", { count: warnings.length })}
          </div>
          <ul className="space-y-0.5">
            {warnings.map((w, i) => (
              <li key={i} className="flex gap-1 text-[11px] text-amber-300/90">
                <span className="font-mono text-amber-500/70">[{w.kind}]</span>
                <span className="flex-1">{w.message}</span>
                {w.line > 0 && (
                  <span className="text-amber-500/50">{t("chat.warningLine", { line: w.line })}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function ChatPanel({ sessionId }: { sessionId: string }) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const selectStep = useUiStore((st) => st.selectStep);
  const selectBlock = useUiStore((st) => st.selectBlock);
  const selectedBlock = useUiStore((st) => st.selectedBlock);
  const { running, run, stop } = useExecution(sessionId);
  const [input, setInput] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [progress, setProgress] = useState("");
  const [busyStepId, setBusyStepId] = useState<number | null>(null);
  const [regenStepId, setRegenStepId] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { data: session, isLoading } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => fetchSession(sessionId),
  });
  // 블록 카드 노출 여부 판단용 (비어있는 블록은 카드 숨김). CodePane 과 동일 키로 dedup.
  const { data: blocks } = useQuery({
    queryKey: ["blocks", sessionId, session?.updated_at],
    queryFn: () => fetchBlocks(sessionId),
    enabled: !!session,
  });

  const { picking, pending, error: pickError, startPick, clearPending } = usePickStore();
  const {
    capturing,
    images: pendingImages,
    startCapture,
    removeImage,
    clear: clearImages,
  } = useCaptureStore();
  const {
    recording,
    eventCount,
    busy: recBusy,
    start: startRec,
    marker: addMarker,
    stopReview: stopRec,
    cancel: cancelRec,
  } = useRecordStore();

  const genMut = useMutation({
    // 진행상황 스트리밍 (handoff §44, /ws/generate). generateStream 을 Promise 로 감싸
    // onProgress 는 setProgress 로 라이브 표시, onDone/onError 로 resolve/reject.
    // pending element 는 호출 시점에 store 에서 읽어 stale closure 회피.
    mutationFn: (req: string) =>
      new Promise<GenerateResult>((resolve, reject) => {
        setProgress("");
        generateStream(
          sessionId,
          req,
          usePickStore.getState().pending,
          {
            onProgress: (m) => setProgress(m),
            onDone: (result) => resolve(result),
            onError: (msg) => reject(new Error(msg)),
          },
          useCaptureStore.getState().images.map((im) => im.path),
        ).catch(reject);
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

  // ── step 변경 액션 (§47 (A)유형) — 공용 래퍼로 busy/에러/invalidate 처리 ──
  const runStepAction = async (
    stepId: number,
    fn: () => Promise<unknown>,
    okMsg: string,
  ) => {
    if (running || busyStepId !== null) return;
    setBusyStepId(stepId);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["session", sessionId] });
      toast.success(okMsg);
    } catch (e) {
      toast.error(t("chat.actionFailed", { message: (e as Error).message }));
    } finally {
      setBusyStepId(null);
    }
  };
  const onDeleteStep = (stepId: number) => {
    if (!window.confirm(t("chat.confirmDeleteStep", { id: stepId }))) return;
    void runStepAction(stepId, () => deleteStep(sessionId, stepId), t("chat.stepDeleted", { id: stepId }));
  };
  const onMoveStep = (stepId: number, dir: "up" | "down") =>
    void runStepAction(stepId, () => moveStep(sessionId, stepId, dir), t("chat.stepMoved"));
  const onInsertStep = (stepId: number) =>
    void runStepAction(
      stepId,
      async () => {
        const r = await insertStep(sessionId, stepId);
        selectStep(r.new_step_id);
      },
      t("chat.stepInserted", { id: stepId }),
    );
  const onRegenerateStep = async (stepId: number) => {
    if (running || busyStepId !== null || regenStepId !== null) return;
    setRegenStepId(stepId);
    try {
      const res = await regenerateStep(sessionId, stepId);
      if (!res.success) {
        toast.error(res.error || t("chat.regenFailed"));
        return;
      }
      await qc.invalidateQueries({ queryKey: ["session", sessionId] });
      selectStep(stepId);
      toast.success(t("chat.stepRegenerated", { id: stepId }));
    } catch (e) {
      toast.error(t("chat.actionFailed", { message: (e as Error).message }));
    } finally {
      setRegenStepId(null);
    }
  };

  // 새 step 생성 시 맨 아래로 스크롤.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [session?.steps.length]);

  const busy = genMut.isPending;
  const send = (req: string) => {
    genMut.mutate(req);
    if (pending) clearPending(); // 한 요청에 한 번만 첨부
    if (pendingImages.length) clearImages(); // 첨부 이미지도 한 요청에 한 번만
  };
  // 전송 — 평문 시크릿 감지(#21b) 후 발견되면 마스킹 권고 confirm. 이미 placeholder
  // ({{secret:...}})로 바꾼 부분은 detect 가 잡지 않으므로 자동완성 사용 시 경고 없음.
  const submit = async () => {
    const req = input.trim();
    if (!req || busy) return;
    try {
      const { matches } = await scanSecrets(req);
      if (matches.length > 0) {
        const kinds = [...new Set(matches.map((m) => m.kind))].join(", ");
        const proceed = window.confirm(t("secrets.plaintextWarn", { count: matches.length, kinds }));
        if (!proceed) return; // 사용자가 취소 → @자동완성으로 시크릿 등록 권장
      }
    } catch {
      /* 감지 실패는 무시하고 전송(감지는 보조 안전장치) */
    }
    send(req);
  };

  return (
    <div className="flex h-full flex-1 flex-col">
      <header className="flex h-12 items-center justify-between border-b border-black/20 px-4 shadow-sm">
        <span className="truncate font-semibold">{session ? session.title : "…"}</span>
        <div className="flex items-center gap-1">
          {/* AI 엔진 퀵스위치 — 녹화 중엔 헤더 혼잡 줄이려 숨김. */}
          {!recording && <EngineSwitcher />}
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
                onClick={() => stopRec(sessionId)}
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
          {session && session.steps.length > 0 && blocks?.library_code?.trim() && (
            <BlockCard
              kind="library"
              active={selectedBlock === "library"}
              onSelect={() => selectBlock("library")}
            />
          )}
          {session && session.steps.length > 0 && blocks?.initial_code?.trim() && (
            <BlockCard
              kind="initial"
              active={selectedBlock === "initial"}
              onSelect={() => selectBlock("initial")}
            />
          )}
          {session?.steps.map((s, i) => (
            <StepCard
              key={s.step_id}
              step={s}
              running={running}
              busy={busyStepId === s.step_id}
              regenerating={regenStepId === s.step_id}
              isFirst={i === 0}
              isLast={i === (session?.steps.length ?? 0) - 1}
              onRun={(id) => run("single", id)}
              onRunFrom={(id) => run("from", id)}
              onRegenerate={onRegenerateStep}
              onMove={onMoveStep}
              onInsert={onInsertStep}
              onDelete={onDeleteStep}
            />
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

      {pendingImages.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-black/20 px-3 pt-2">
          {pendingImages.map((im) => (
            <span
              key={im.path}
              className="flex items-center gap-1 rounded-full bg-blue-500/20 px-2 py-1 text-xs text-discord-text"
              title={im.path}
            >
              <ImageIcon className="h-3 w-3 shrink-0 text-blue-400" />
              <span className="truncate">{im.width}×{im.height}</span>
              <button
                onClick={() => removeImage(im.path)}
                className="ml-1 shrink-0 hover:text-white"
                title={t("chat.removeAttach")}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
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
            onClick={() => startPick()}
          >
            <MousePointerClick className="h-5 w-5" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-[60px] w-10 shrink-0 text-discord-muted hover:text-blue-400"
            title={t("chat.captureTitle")}
            disabled={busy || capturing}
            onClick={() => startCapture(sessionId)}
          >
            {capturing ? <Loader2 className="h-5 w-5 animate-spin" /> : <Camera className="h-5 w-5" />}
          </Button>
          <SecretAutocomplete
            value={input}
            onChange={setInput}
            onSubmit={submit}
            disabled={busy}
            placeholder={t("chat.placeholder")}
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
