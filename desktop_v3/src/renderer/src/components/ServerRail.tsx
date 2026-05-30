// SPDX-License-Identifier: AGPL-3.0-or-later
// 좌측 서버 레일 (handoff §59) — Discord 레이아웃의 최외곽 세로 바.
// 현 단계(데스크톱 단일 프로젝트)에서는 #2 "전역 네비/유틸 바"로 회수:
//   - 상단 로고(oh) = 홈(세션 선택 해제 → EmptyState).
//   - 하단 유틸 그룹 = 도움말/환경점검/설정/언어/테마 (이전엔 사이드바 푸터에 밀집).
// 워크스페이스 기능이 들어오면 로고 아래에 워크스페이스 아이콘을 추가해 #1(프로젝트
// 전환기)로 승격할 예정 — 그래서 레일을 없애지 않고 Discord 레이아웃을 유지한다.
// 백엔드 무관(core/api_server 0줄): 기존 uiStore 플래그/themeStore/i18n 만 사용.
import { useTranslation } from "react-i18next";
import { Activity, HelpCircle, KeyRound, Languages, Moon, Settings, Sun } from "lucide-react";
import { useUiStore } from "@/store/uiStore";
import { useThemeStore } from "@/store/themeStore";
import { currentLang, setLang } from "@/i18n";

function RailButton({
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
      className="flex h-10 w-10 items-center justify-center rounded-xl text-discord-muted transition-colors hover:bg-discord-card hover:text-discord-text"
    >
      {children}
    </button>
  );
}

export function ServerRail() {
  const { t, i18n } = useTranslation();
  const selectSession = useUiStore((st) => st.selectSession);
  const setSettingsOpen = useUiStore((st) => st.setSettingsOpen);
  const setEnvOpen = useUiStore((st) => st.setEnvOpen);
  const setOnboardingOpen = useUiStore((st) => st.setOnboardingOpen);
  const setSecretsOpen = useUiStore((st) => st.setSecretsOpen);
  const theme = useThemeStore((st) => st.theme);
  const toggleTheme = useThemeStore((st) => st.toggle);
  const lang = (i18n.language || currentLang()).startsWith("ko") ? "ko" : "en";

  return (
    <div className="flex h-full w-[72px] flex-col items-center gap-2 bg-discord-rail py-3">
      {/* 로고 = 홈(세션 선택 해제). */}
      <button
        type="button"
        title={t("sidebar.home")}
        onClick={() => selectSession(null)}
        className="flex h-12 w-12 items-center justify-center rounded-2xl bg-discord-accent text-lg font-bold text-white transition-[border-radius] hover:rounded-xl"
      >
        oh
      </button>

      <div className="mt-1 h-px w-8 bg-discord-muted/20" />

      {/* 하단 전역 유틸 그룹. */}
      <div className="mt-auto flex flex-col items-center gap-1">
        <RailButton title={t("sidebar.help")} onClick={() => setOnboardingOpen(true)}>
          <HelpCircle className="h-5 w-5" />
        </RailButton>
        <RailButton title={t("env.title")} onClick={() => setEnvOpen(true)}>
          <Activity className="h-5 w-5" />
        </RailButton>
        <RailButton title={t("secrets.title")} onClick={() => setSecretsOpen(true)}>
          <KeyRound className="h-5 w-5" />
        </RailButton>
        <RailButton title={t("settings.title")} onClick={() => setSettingsOpen(true)}>
          <Settings className="h-5 w-5" />
        </RailButton>
        <RailButton
          title={lang === "ko" ? t("sidebar.toEnglish") : t("sidebar.toKorean")}
          onClick={() => setLang(lang === "ko" ? "en" : "ko")}
        >
          <Languages className="h-5 w-5" />
        </RailButton>
        <RailButton
          title={theme === "dark" ? t("sidebar.toLightTheme") : t("sidebar.toDarkTheme")}
          onClick={toggleTheme}
        >
          {theme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </RailButton>
      </div>
    </div>
  );
}
