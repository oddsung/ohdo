// SPDX-License-Identifier: AGPL-3.0-or-later
// 토스트 렌더러 (handoff §40 #4) — 우하단 스택.
import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useToastStore } from "@/store/toastStore";

const ICON = {
  success: <CheckCircle2 className="h-4 w-4 text-discord-green" />,
  error: <XCircle className="h-4 w-4 text-red-400" />,
  info: <Info className="h-4 w-4 text-primary" />,
};

export function Toaster() {
  // 토스트 항목 변수가 t 라서 번역 함수는 tr 로 별칭.
  const { t: tr } = useTranslation();
  const { toasts, dismiss } = useToastStore();
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className="pointer-events-auto flex items-start gap-2 rounded-md border border-border bg-discord-card px-3 py-2 text-sm text-discord-text shadow-lg animate-in slide-in-from-bottom-2 duration-200"
        >
          <span className="mt-0.5 shrink-0">{ICON[t.kind]}</span>
          <span className="flex-1 break-words">{t.message}</span>
          <button
            onClick={() => dismiss(t.id)}
            className="shrink-0 text-discord-muted hover:text-white"
            title={tr("common.close")}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
