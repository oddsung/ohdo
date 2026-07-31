// SPDX-License-Identifier: AGPL-3.0-or-later
// 멀티 세션 탭 바 (handoff §57/백로그 #17) — 열린 세션들을 탭으로 전환/닫기.
// openTabs(uiStore) 를 렌더, 활성 탭 강조. 세션 제목은 sessions 쿼리에서 조회.
// §78: 커스텀 타이틀바(TitleBar) 안에 임베드 — 자체 배경/보더 없이 rail 바탕 위에
// 탭만 그린다(w-fit → 남는 타이틀바 영역은 드래그 유지, 탭 스트립만 no-drag).
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { fetchSessions } from "@/api/client";
import { useUiStore } from "@/store/uiStore";

export function TabBar() {
  const { t } = useTranslation();
  const { data: sessions } = useQuery({ queryKey: ["sessions"], queryFn: fetchSessions });
  const openTabs = useUiStore((s) => s.openTabs);
  const active = useUiStore((s) => s.selectedSessionId);
  const select = useUiStore((s) => s.selectSession);
  const closeTab = useUiStore((s) => s.closeTab);

  if (openTabs.length === 0) return null;

  const titleOf = (id: string) =>
    sessions?.find((s) => s.session_id === id)?.title || t("chat.untitled");

  return (
    <div className="app-region-no-drag flex h-full w-fit max-w-full items-stretch gap-0.5 overflow-x-auto px-1 pt-1">
      {openTabs.map((id) => {
        const isActive = id === active;
        return (
          <div
            key={id}
            role="button"
            tabIndex={0}
            onClick={() => select(id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") select(id);
            }}
            className={`group flex max-w-[180px] cursor-pointer items-center gap-1.5 rounded-t-md px-3 text-xs transition-colors ${
              isActive
                ? "bg-discord-sidebar text-discord-text"
                : "text-discord-muted hover:bg-discord-sidebar/50"
            }`}
            title={titleOf(id)}
          >
            <span className="truncate">{titleOf(id)}</span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                closeTab(id);
              }}
              title={t("tab.close")}
              className={`shrink-0 rounded p-0.5 hover:bg-white/10 hover:text-white ${
                isActive ? "opacity-70" : "opacity-0 group-hover:opacity-100"
              }`}
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
