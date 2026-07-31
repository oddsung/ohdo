// SPDX-License-Identifier: AGPL-3.0-or-later
// 커스텀 타이틀바 — VS Code/Cursor/OpenCode 스타일 IDE 셸 (titleBarStyle:hidden + WCO).
//
// 구성(좌→우): oh 로고(홈) · 햄버거 메뉴(전역 유틸/설정 진입점, OpenCode 메뉴 구조 참고)
// · 새 세션 퀵버튼 · 세션 탭(TabBar 임베드) · 우측 퀵유틸(설정/테마) · [OS 캡션 버튼 영역].
// 이전 좌측 ServerRail(§59)의 유틸 그룹을 이 상단 바로 이전했다(사용자 결정, §78).
// 바탕은 -webkit-app-region: drag 로 창 드래그, 상호작용 요소는 no-drag.
// 우측 paddingRight 는 env(titlebar-area-width) 로 네이티브 캡션 버튼 밑 겹침을 예약한다.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Activity,
  HelpCircle,
  KeyRound,
  Languages,
  Menu,
  Moon,
  Plus,
  Settings,
  SquarePen,
  Sun,
} from "lucide-react";
import { useUiStore } from "@/store/uiStore";
import { useThemeStore } from "@/store/themeStore";
import { currentLang, setLang } from "@/i18n";
import { TabBar } from "./TabBar";

function IconButton({
  title,
  onClick,
  children,
}: {
  title: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className="app-region-no-drag flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-discord-muted transition-colors hover:bg-discord-card hover:text-discord-text"
    >
      {children}
    </button>
  );
}

function MenuItem({
  label,
  onSelect,
  icon,
}: {
  label: string;
  onSelect: () => void;
  icon: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onSelect}
      className="flex w-full items-center gap-2.5 rounded px-2.5 py-1.5 text-left text-sm text-discord-text transition-colors hover:bg-discord-card"
    >
      <span className="text-discord-muted">{icon}</span>
      {label}
    </button>
  );
}

export function TitleBar({
  onNewSession,
  creating,
}: {
  onNewSession: () => void;
  creating: boolean;
}) {
  const { t, i18n } = useTranslation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const selectSession = useUiStore((st) => st.selectSession);
  const setSettingsOpen = useUiStore((st) => st.setSettingsOpen);
  const setEnvOpen = useUiStore((st) => st.setEnvOpen);
  const setOnboardingOpen = useUiStore((st) => st.setOnboardingOpen);
  const setSecretsOpen = useUiStore((st) => st.setSecretsOpen);
  const theme = useThemeStore((st) => st.theme);
  const toggleTheme = useThemeStore((st) => st.toggle);
  const lang = (i18n.language || currentLang()).startsWith("ko") ? "ko" : "en";

  // 메뉴 열림 동안 바깥 클릭/Esc 로 닫기.
  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const pick = (fn: () => void) => () => {
    setMenuOpen(false);
    fn();
  };

  return (
    <div
      className="app-region-drag relative z-40 flex h-9 w-full shrink-0 items-center gap-1 border-b border-black/30 bg-discord-rail pl-1.5"
      style={{
        // WCO 네이티브 캡션 버튼(최소화/최대화/닫기) 영역만큼 우측 여백 예약.
        paddingRight: "calc(100vw - env(titlebar-area-width, 100vw) + 6px)",
      }}
    >
      {/* 로고 = 홈(세션 선택 해제 → EmptyState). */}
      <button
        type="button"
        title={t("sidebar.home")}
        onClick={() => selectSession(null)}
        className="app-region-no-drag flex h-6 w-8 shrink-0 items-center justify-center rounded-md bg-discord-accent text-xs font-bold text-white hover:opacity-90"
      >
        oh
      </button>

      {/* 햄버거 메뉴 — 전역 유틸/설정 진입점 (구 ServerRail 유틸 그룹). */}
      <div ref={menuRef} className="app-region-no-drag relative shrink-0">
        <button
          type="button"
          title={t("menu.open")}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((v) => !v)}
          className={`flex h-7 w-7 items-center justify-center rounded-md transition-colors hover:bg-discord-card hover:text-discord-text ${
            menuOpen ? "bg-discord-card text-discord-text" : "text-discord-muted"
          }`}
        >
          <Menu className="h-4 w-4" />
        </button>
        {menuOpen && (
          <div
            role="menu"
            className="absolute left-0 top-8 z-50 w-56 rounded-lg border border-black/30 bg-discord-sidebar p-1.5 shadow-xl"
          >
            <MenuItem
              label={t("app.createSession")}
              icon={<Plus className="h-4 w-4" />}
              onSelect={pick(onNewSession)}
            />
            <div className="my-1 h-px bg-discord-muted/20" />
            <MenuItem
              label={t("env.title")}
              icon={<Activity className="h-4 w-4" />}
              onSelect={pick(() => setEnvOpen(true))}
            />
            <MenuItem
              label={t("secrets.title")}
              icon={<KeyRound className="h-4 w-4" />}
              onSelect={pick(() => setSecretsOpen(true))}
            />
            <MenuItem
              label={t("settings.title")}
              icon={<Settings className="h-4 w-4" />}
              onSelect={pick(() => setSettingsOpen(true))}
            />
            <div className="my-1 h-px bg-discord-muted/20" />
            <MenuItem
              label={lang === "ko" ? t("sidebar.toEnglish") : t("sidebar.toKorean")}
              icon={<Languages className="h-4 w-4" />}
              onSelect={pick(() => setLang(lang === "ko" ? "en" : "ko"))}
            />
            <MenuItem
              label={theme === "dark" ? t("sidebar.toLightTheme") : t("sidebar.toDarkTheme")}
              icon={
                theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />
              }
              onSelect={pick(toggleTheme)}
            />
            <div className="my-1 h-px bg-discord-muted/20" />
            <MenuItem
              label={t("sidebar.help")}
              icon={<HelpCircle className="h-4 w-4" />}
              onSelect={pick(() => setOnboardingOpen(true))}
            />
          </div>
        )}
      </div>

      {/* 새 세션 퀵버튼 (OpenCode 타이틀바의 새 세션 버튼 대응). */}
      <IconButton title={t("app.createSession")} onClick={onNewSession}>
        <SquarePen className={`h-4 w-4 ${creating ? "animate-pulse" : ""}`} />
      </IconButton>

      <div className="mx-0.5 h-4 w-px shrink-0 bg-discord-muted/20" />

      {/* 세션 탭 — 남는 영역은 드래그 유지(TabBar 자체만 no-drag). */}
      <div className="flex h-full min-w-0 flex-1 items-end overflow-hidden">
        <TabBar />
      </div>

      {/* 우측 퀵유틸 — 자주 쓰는 설정/테마만 노출(나머지는 메뉴/팔레트). */}
      <IconButton title={t("settings.title")} onClick={() => setSettingsOpen(true)}>
        <Settings className="h-4 w-4" />
      </IconButton>
      <IconButton
        title={theme === "dark" ? t("sidebar.toLightTheme") : t("sidebar.toDarkTheme")}
        onClick={toggleTheme}
      >
        {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </IconButton>
    </div>
  );
}
