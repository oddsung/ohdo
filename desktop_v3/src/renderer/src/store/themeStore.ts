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
