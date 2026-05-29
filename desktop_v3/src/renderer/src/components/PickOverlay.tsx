// SPDX-License-Identifier: AGPL-3.0-or-later
// element picker 카운트다운 오버레이 (handoff §40 #3).
// pointer-events-none — 카운트다운 동안 사용자가 대상 앱 위에 커서를 올릴 수 있도록
// 클릭/마우스를 통과시킨다.
import { useTranslation } from "react-i18next";
import { usePickStore } from "@/store/pickStore";

export function PickOverlay() {
  const { t } = useTranslation();
  const { picking, countdown } = usePickStore();
  if (!picking) return null;
  return (
    <div className="pointer-events-none fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/30 animate-in fade-in duration-200">
      <div className="text-7xl font-bold text-white drop-shadow-lg">{countdown}</div>
      <p className="mt-4 rounded-md bg-black/60 px-4 py-2 text-sm text-white">
        {t("pick.overlayHint")}
      </p>
    </div>
  );
}
