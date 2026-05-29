// SPDX-License-Identifier: AGPL-3.0-or-later
// i18n 초기화 (handoff §45 Phase D). react-i18next + 인라인 ko/en 카탈로그.
//
// desktop_v3 UI 문자열은 PySide6 (core/locale/{en,ko}.json, ui_v2.* 키) 와 키 체계가
// 달라 재사용률이 낮으므로 desktop_v3 전용 카탈로그를 신규 작성한다 (사용자 결정 §45).
// 언어 결정 우선순위: localStorage("ohdo.lang") → navigator.language → "en".
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { en } from "./locales/en";
import { ko } from "./locales/ko";

export const LANG_STORAGE_KEY = "ohdo.lang";
export type Lang = "ko" | "en";

function detectInitialLang(): Lang {
  const saved = localStorage.getItem(LANG_STORAGE_KEY);
  if (saved === "ko" || saved === "en") return saved;
  const nav = (navigator.language || "").toLowerCase();
  return nav.startsWith("ko") ? "ko" : "en";
}

i18n.use(initReactI18next).init({
  resources: {
    ko: { translation: ko },
    en: { translation: en },
  },
  lng: detectInitialLang(),
  fallbackLng: "en",
  interpolation: { escapeValue: false }, // React 가 XSS 이스케이프 담당
  returnNull: false,
});

/** 언어 변경 + localStorage 영속. */
export function setLang(lang: Lang): void {
  localStorage.setItem(LANG_STORAGE_KEY, lang);
  i18n.changeLanguage(lang);
}

export function currentLang(): Lang {
  return (i18n.language as Lang) === "ko" ? "ko" : "en";
}

export default i18n;
