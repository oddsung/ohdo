// SPDX-License-Identifier: AGPL-3.0-or-later
// 새 세션 이름 입력 다이얼로그 (handoff §89) — 자동 추천 이름을 프리필하고 사용자가
// 원하는 이름으로 고쳐 생성한다. 사이드바 "+" / 타이틀바 메뉴 / 팔레트 / 빈 화면 공용
// (uiStore.newSessionOpen). Enter=생성, Esc=취소.
import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Loader2, Plus } from "lucide-react";
import { createSession } from "@/api/client";
import { useUiStore } from "@/store/uiStore";
import { toast } from "@/store/toastStore";
import { buttonVariants } from "@/components/ui/button";

export function NewSessionDialog() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const selectSession = useUiStore((st) => st.selectSession);
  const setOpen = useUiStore((st) => st.setNewSessionOpen);
  const inputRef = useRef<HTMLInputElement>(null);

  // 추천 이름 프리필 — 열릴 때 1회 생성, 전체 선택 상태라 바로 타이핑하면 대체된다.
  const [title, setTitle] = useState(() => {
    const stamp = new Date().toISOString().slice(5, 16).replace("T", " ");
    return t("sidebar.newSessionName", { stamp });
  });

  useEffect(() => {
    requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });
  }, []);

  const createMut = useMutation({
    mutationFn: (name: string) => createSession(name),
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      selectSession(s.session_id);
      toast.success(t("session.created"));
      setOpen(false);
    },
    onError: (e) => toast.error(t("session.createFailed", { message: (e as Error).message })),
  });

  const submit = () => {
    const name = title.trim();
    if (!name || createMut.isPending) return;
    createMut.mutate(name);
  };

  return (
    <div
      className="fixed inset-0 z-[70] flex items-start justify-center bg-black/50 pt-[20vh]"
      onClick={() => setOpen(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="w-[24rem] rounded-lg border border-black/30 bg-discord-sidebar p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-sm font-semibold text-discord-text">{t("app.createSession")}</p>
        <input
          ref={inputRef}
          data-testid="new-session-name"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
            if (e.key === "Escape") setOpen(false);
          }}
          placeholder={t("session.namePlaceholder")}
          className="mt-3 w-full rounded-md border border-black/30 bg-discord-card px-3 py-2 text-sm text-discord-text outline-none focus:border-discord-accent"
        />
        <div className="mt-3 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rounded px-3 py-1.5 text-xs text-discord-muted hover:text-white"
          >
            {t("common.cancel")}
          </button>
          <button
            type="button"
            data-testid="new-session-create"
            disabled={!title.trim() || createMut.isPending}
            onClick={submit}
            className={buttonVariants({ className: "h-8 px-3 text-xs" })}
          >
            {createMut.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Plus className="h-3.5 w-3.5" />
            )}
            {t("common.create")}
          </button>
        </div>
      </div>
    </div>
  );
}
