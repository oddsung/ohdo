// SPDX-License-Identifier: AGPL-3.0-or-later
// live 실행 로그 콘솔 — WS 스트리밍 출력 (handoff §40 #1).
import { useEffect, useRef } from "react";
import { ChevronDown, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useExecStore } from "@/store/execStore";
import { Button } from "@/components/ui/button";

export function LogConsole() {
  const { t } = useTranslation();
  const { logs, consoleOpen, toggleConsole, clearLogs, running } = useExecStore();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  if (!consoleOpen) {
    return (
      <button
        onClick={() => toggleConsole(true)}
        className="flex h-8 w-full items-center gap-2 border-t border-black/30 bg-discord-rail px-3 text-xs text-discord-muted hover:text-white"
      >
        <span
          className={`h-2 w-2 rounded-full ${running ? "animate-pulse bg-discord-green" : "bg-discord-muted"}`}
        />
        {t("console.label")} {logs.length > 0 ? `(${logs.length})` : ""} ▲
      </button>
    );
  }

  return (
    <div className="flex h-44 flex-col border-t border-black/30 bg-[#1a1b1e] animate-in slide-in-from-bottom-2 duration-200">
      <header className="flex h-8 items-center justify-between border-b border-black/30 px-3">
        <div className="flex items-center gap-2 text-xs text-zinc-400">
          <span
            className={`h-2 w-2 rounded-full ${running ? "animate-pulse bg-emerald-500" : "bg-zinc-500"}`}
          />
          {t("console.label")} {running ? t("console.running") : ""}
        </div>
        <div className="flex items-center gap-1 text-zinc-400">
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6"
            title={t("common.clear")}
            onClick={clearLogs}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6"
            title={t("console.collapse")}
            onClick={() => toggleConsole(false)}
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </Button>
        </div>
      </header>
      <div className="flex-1 overflow-y-auto px-3 py-2 font-mono text-xs leading-relaxed">
        {logs.length === 0 && <p className="text-zinc-500">{t("console.emptyHint")}</p>}
        {logs.map((l) => (
          <div
            key={l.id}
            className={
              l.kind === "error"
                ? "text-red-400"
                : l.kind === "step_done"
                  ? "text-emerald-400"
                  : l.kind === "done"
                    ? "text-zinc-500"
                    : "text-zinc-200"
            }
          >
            {l.text}
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
