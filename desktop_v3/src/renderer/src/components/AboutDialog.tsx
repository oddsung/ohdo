// SPDX-License-Identifier: AGPL-3.0-or-later
// About 다이얼로그 (handoff §90) — 앱/브리지/런타임 버전 표시 + 수동 업데이트 확인.
// 업데이트가 있으면 다운로드가 시작되고, 완료되면 하단 UpdateNotice 배너가 뜬다(§82).
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ExternalLink, Loader2, RefreshCw } from "lucide-react";
import { fetchHealth } from "@/api/client";
import { buttonVariants } from "@/components/ui/button";

type AppInfo = {
  version: string;
  electron: string;
  chrome: string;
  node: string;
  platform: string;
  packaged: boolean;
};

type CheckState =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "latest" }
  | { kind: "available"; version: string }
  | { kind: "dev" }
  | { kind: "error"; message: string };

export function AboutDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [check, setCheck] = useState<CheckState>({ kind: "idle" });
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: fetchHealth });

  useEffect(() => {
    void window.ohdo
      .getAppInfo()
      .then(setInfo)
      .catch(() => setInfo(null));
  }, []);

  const runCheck = async () => {
    setCheck({ kind: "checking" });
    try {
      const r = await window.ohdo.checkForUpdates();
      if (r.status === "available" && r.version) setCheck({ kind: "available", version: r.version });
      else if (r.status === "latest") setCheck({ kind: "latest" });
      else if (r.status === "dev") setCheck({ kind: "dev" });
      else setCheck({ kind: "error", message: r.message ?? "unknown" });
    } catch (e) {
      setCheck({ kind: "error", message: (e as Error).message });
    }
  };

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="w-[26rem] rounded-lg border border-black/30 bg-discord-sidebar p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-discord-accent text-base font-bold text-white">
            oh
          </span>
          <div>
            <p className="text-base font-semibold text-discord-text">ohdo</p>
            <p className="text-xs text-discord-muted">{t("about.tagline")}</p>
          </div>
        </div>

        <dl className="mt-4 space-y-1.5 text-sm">
          <div className="flex justify-between">
            <dt className="text-discord-muted">{t("about.appVersion")}</dt>
            <dd data-testid="about-version" className="font-mono text-discord-text">
              v{info?.version ?? "…"}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-discord-muted">{t("about.bridgeVersion")}</dt>
            <dd className="font-mono text-discord-text">
              {health?.version ? `v${health.version}` : t("bridge.offline")}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-discord-muted">{t("about.runtime")}</dt>
            <dd className="font-mono text-xs text-discord-muted">
              Electron {info?.electron ?? "…"} · {info?.platform ?? ""}
            </dd>
          </div>
        </dl>

        {/* 업데이트 확인 결과 */}
        <div className="mt-4 min-h-[1.25rem] text-xs">
          {check.kind === "latest" && (
            <p className="text-discord-green">{t("about.latest")}</p>
          )}
          {check.kind === "available" && (
            <p className="text-primary">{t("about.available", { version: check.version })}</p>
          )}
          {check.kind === "dev" && <p className="text-discord-muted">{t("about.devMode")}</p>}
          {check.kind === "error" && (
            <p className="text-red-400">{t("about.checkError", { message: check.message })}</p>
          )}
        </div>

        <div className="mt-3 flex items-center justify-between">
          <button
            type="button"
            onClick={() => void window.ohdo.openRepo()}
            className="flex items-center gap-1 text-xs text-discord-muted hover:text-white"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            {t("about.github")} · AGPL-3.0
          </button>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded px-3 py-1.5 text-xs text-discord-muted hover:text-white"
            >
              {t("common.close")}
            </button>
            <button
              type="button"
              data-testid="about-check-updates"
              disabled={check.kind === "checking"}
              onClick={() => void runCheck()}
              className={buttonVariants({ className: "h-8 px-3 text-xs" })}
            >
              {check.kind === "checking" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              {t("about.checkUpdates")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
