// SPDX-License-Identifier: AGPL-3.0-or-later
// 녹화 review 다이얼로그 (handoff §63, 백로그 #22) — stop=즉시commit 을 "검토 후 commit"으로.
// stop_preview 가 돌려준 변환 step 을 사용자가 검토/편집(코드·설명)/삭제/순서변경 후 확정한다.
// v2 RecordingReviewDialog 의 v3 등가. core 무관(commitReview → /recording/commit 위임).
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ArrowDown, ArrowUp, Loader2, Trash2, X } from "lucide-react";
import type { Step } from "@/api/client";
import { useRecordStore } from "@/store/recordStore";
import { Button } from "@/components/ui/button";

export function RecordingReviewDialog() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const open = useRecordStore((s) => s.reviewOpen);
  const initial = useRecordStore((s) => s.previewSteps);
  const sessionId = useRecordStore((s) => s.reviewSessionId);
  const busy = useRecordStore((s) => s.busy);
  const commitReview = useRecordStore((s) => s.commitReview);
  const discardReview = useRecordStore((s) => s.discardReview);

  // 편집용 로컬 사본 — reviewOpen 이 켜질 때 previewSteps 로 초기화.
  const [steps, setSteps] = useState<Step[]>([]);
  const [seeded, setSeeded] = useState(false);
  if (open && !seeded) {
    setSteps(initial.map((s) => ({ ...s })));
    setSeeded(true);
  }
  if (!open && seeded) setSeeded(false);
  if (!open) return null;

  const patch = (i: number, field: "user_request" | "generated_code", value: string) =>
    setSteps((arr) => arr.map((s, idx) => (idx === i ? { ...s, [field]: value } : s)));
  const remove = (i: number) => setSteps((arr) => arr.filter((_, idx) => idx !== i));
  const move = (i: number, dir: -1 | 1) =>
    setSteps((arr) => {
      const j = i + dir;
      if (j < 0 || j >= arr.length) return arr;
      const next = [...arr];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  const confirm = () => {
    void commitReview(steps, () => {
      if (sessionId) {
        qc.invalidateQueries({ queryKey: ["session", sessionId] });
        qc.invalidateQueries({ queryKey: ["sessions"] });
      }
    });
  };

  return (
    <div className="fixed inset-0 z-[55] flex items-center justify-center bg-black/60 animate-in fade-in duration-150">
      <div className="flex max-h-[88vh] w-[min(720px,94vw)] flex-col overflow-hidden rounded-xl border border-zinc-700 bg-zinc-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("review.title", { count: steps.length })}
          </h2>
          <Button size="icon" variant="ghost" className="h-7 w-7" title={t("common.close")} onClick={discardReview}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3">
          <p className="mb-3 text-xs text-zinc-500">{t("review.hint")}</p>
          {steps.length === 0 ? (
            <p className="py-8 text-center text-sm text-zinc-500">{t("review.allRemoved")}</p>
          ) : (
            <ul className="space-y-3">
              {steps.map((s, i) => (
                <li key={i} className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-zinc-400">STEP {i + 1}</span>
                    <div className="flex items-center gap-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-6 w-6 text-zinc-500 hover:text-zinc-100"
                        title={t("chat.moveUp")}
                        disabled={i === 0}
                        onClick={() => move(i, -1)}
                      >
                        <ArrowUp className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-6 w-6 text-zinc-500 hover:text-zinc-100"
                        title={t("chat.moveDown")}
                        disabled={i === steps.length - 1}
                        onClick={() => move(i, 1)}
                      >
                        <ArrowDown className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-6 w-6 text-zinc-500 hover:text-red-400"
                        title={t("chat.deleteStep")}
                        onClick={() => remove(i)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                  <input
                    value={s.user_request ?? ""}
                    onChange={(e) => patch(i, "user_request", e.target.value)}
                    placeholder={t("review.descPlaceholder")}
                    className="mb-1.5 w-full rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none"
                  />
                  <textarea
                    value={s.generated_code ?? ""}
                    onChange={(e) => patch(i, "generated_code", e.target.value)}
                    spellCheck={false}
                    rows={Math.min(12, Math.max(3, (s.generated_code ?? "").split("\n").length))}
                    className="w-full resize-y rounded bg-black/40 px-2 py-1.5 font-mono text-[11px] leading-relaxed text-zinc-200 focus:outline-none"
                  />
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-zinc-800 px-4 py-3">
          <Button variant="ghost" size="sm" className="text-zinc-400" onClick={discardReview} disabled={busy}>
            {t("review.discard")}
          </Button>
          <Button size="sm" onClick={confirm} disabled={busy || steps.length === 0}>
            {busy ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : null}
            {t("review.commit", { count: steps.length })}
          </Button>
        </div>
      </div>
    </div>
  );
}
