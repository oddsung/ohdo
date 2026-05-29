// SPDX-License-Identifier: AGPL-3.0-or-later
// 전역 키보드 단축키 (handoff §40 #4).
//   Ctrl/Cmd+R : 전체 실행 / 실행 중이면 중단
//   Ctrl/Cmd+N : 새 세션
//   Esc        : 요소 선택 카운트다운 취소 (picking 중)
// 텍스트 입력(textarea/input) 포커스 중에는 단축키를 가로채지 않는다(Esc 제외).
import { useEffect } from "react";

export interface ShortcutHandlers {
  onRunToggle?: () => void;
  onNewSession?: () => void;
  onEscape?: () => void;
}

export function useShortcuts({ onRunToggle, onNewSession, onEscape }: ShortcutHandlers): void {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const inEditable =
        !!target &&
        (target.tagName === "TEXTAREA" ||
          target.tagName === "INPUT" ||
          target.isContentEditable);

      if (e.key === "Escape") {
        onEscape?.();
        return;
      }
      if (inEditable) return;

      const mod = e.ctrlKey || e.metaKey;
      if (!mod) return;
      const key = e.key.toLowerCase();
      if (key === "r") {
        e.preventDefault();
        onRunToggle?.();
      } else if (key === "n") {
        e.preventDefault();
        onNewSession?.();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onRunToggle, onNewSession, onEscape]);
}
