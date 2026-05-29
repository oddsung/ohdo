// SPDX-License-Identifier: AGPL-3.0-or-later
// element picker 안내 오버레이 (handoff §48, 절충안). picking 중 "클릭하세요" 힌트.
// 하이라이트/카운트다운 없음 — 클릭은 백엔드 LL 후크가 잡는다. pointer-events-none 라
// 이 오버레이는 클릭을 가로채지 않는다(대상 앱 클릭이 그대로 후크에 전달).
import { useTranslation } from "react-i18next";
import { MousePointerClick } from "lucide-react";
import { usePickStore } from "@/store/pickStore";

export function PickOverlay() {
  const { t } = useTranslation();
  const picking = usePickStore((s) => s.picking);
  if (!picking) return null;
  return (
    <div className="pointer-events-none fixed inset-x-0 top-6 z-50 flex justify-center animate-in fade-in slide-in-from-top-2 duration-200">
      <div className="flex items-center gap-2 rounded-full border border-discord-active bg-discord-panel px-5 py-2.5 shadow-2xl">
        <MousePointerClick className="h-4 w-4 text-primary" />
        <p className="text-sm text-discord-text">{t("pick.overlayHint")}</p>
      </div>
    </div>
  );
}
