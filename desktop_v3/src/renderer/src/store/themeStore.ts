// SPDX-License-Identifier: AGPL-3.0-or-later
// 테마 토글 (handoff §40 #4) — dark/light, localStorage 영속.
import { create } from "zustand";

export type Theme = "dark" | "light";

const STORAGE_KEY = "ohdo.theme";

function readInitial(): Theme {
  const saved = localStorage.getItem(STORAGE_KEY);
  return saved === "light" ? "light" : "dark";
}

function apply(theme: Theme): void {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.classList.toggle("light", theme === "light");
  syncTitleBarOverlay();
}

/** CSS 변수(--d-rail/--d-text)를 읽어 WCO 캡션 버튼 영역 색을 main 에 동기화 (§78).
 *  변수는 "r g b" 채널 문자열 — hex 로 변환해 전달. 실패해도 UI 는 정상(오버레이 색만 유지). */
function syncTitleBarOverlay(): void {
  try {
    const css = getComputedStyle(document.documentElement);
    const toHex = (channels: string): string | null => {
      const m = channels.trim().match(/^(\d+)\s+(\d+)\s+(\d+)$/);
      if (!m) return null;
      return (
        "#" + [m[1], m[2], m[3]].map((v) => Number(v).toString(16).padStart(2, "0")).join("")
      );
    };
    const color = toHex(css.getPropertyValue("--d-rail"));
    const symbolColor = toHex(css.getPropertyValue("--d-text"));
    if (color && symbolColor) {
      window.ohdo?.setTitleBarTheme?.({ color, symbolColor });
    }
  } catch {
    /* preload 미노출(오버레이 창 등) — 무시 */
  }
}

interface ThemeState {
  theme: Theme;
  toggle: () => void;
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: readInitial(),
  toggle: () => {
    const next: Theme = get().theme === "dark" ? "light" : "dark";
    localStorage.setItem(STORAGE_KEY, next);
    apply(next);
    set({ theme: next });
  },
}));

// 모듈 로드 시 즉시 적용 (FOUC 최소화).
apply(readInitial());
// 스타일시트 적용 전이면 CSS 변수가 비어 동기화가 스킵될 수 있어 한 번 더 (§78).
setTimeout(syncTitleBarOverlay, 300);
