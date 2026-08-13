// SPDX-License-Identifier: AGPL-3.0-or-later
// 자동 업데이트 알림 배너 (handoff §82) — main 의 electron-updater 가 새 버전을
// 내려받으면 updater:event(status="downloaded") 를 보내고, 이 배너가 뜬다.
// "재시작" → quitAndInstall. "나중에" → 배너만 닫음 (앱 종료 시 자동 설치).
import { useEffect, useState } from "react";
import { DownloadCloud } from "lucide-react";
import { useTranslation } from "react-i18next";

export function UpdateNotice() {
  const { t } = useTranslation();
  const [version, setVersion] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    // 브라우저 단독 dev 등 preload 미주입 환경 방어.
    if (!window.ohdo?.onUpdaterEvent) return;
    return window.ohdo.onUpdaterEvent((e) => {
      if (e.status === "downloaded") {
        setVersion(e.info?.version ?? "");
        setDismissed(false);
      }
    });
  }, []);

  if (!version || dismissed) return null;

  return (
    <div className="fixed bottom-4 left-1/2 z-[70] w-[26rem] -translate-x-1/2 rounded-md border border-border bg-discord-card px-4 py-3 text-sm text-discord-text shadow-lg animate-in slide-in-from-bottom-2 duration-200">
      <div className="flex items-start gap-2">
        <DownloadCloud className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <div className="flex-1">
          <p className="font-medium">{t("updater.downloaded", { version })}</p>
          <p className="mt-0.5 text-xs text-discord-muted">{t("updater.detail")}</p>
        </div>
      </div>
      <div className="mt-2 flex justify-end gap-2">
        <button
          onClick={() => setDismissed(true)}
          className="rounded px-2 py-1 text-xs text-discord-muted hover:text-white"
        >
          {t("updater.later")}
        </button>
        <button
          onClick={() => void window.ohdo.installUpdate()}
          className="rounded bg-primary px-2 py-1 text-xs font-medium text-white hover:opacity-90"
        >
          {t("updater.restart")}
        </button>
      </div>
    </div>
  );
}
