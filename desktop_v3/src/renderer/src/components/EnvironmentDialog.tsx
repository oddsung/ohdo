// SPDX-License-Identifier: AGPL-3.0-or-later
// 환경 점검 다이얼로그 (handoff §53/백로그 #18) — Python/패키지/CLI AI 설치 상태.
// GET /environment (core EnvironmentScanner.full_scan). 스캔이 수초 걸려 on-demand + 로딩 표시.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Check, Loader2, RefreshCw, X } from "lucide-react";
import { fetchEnvironment, type EnvironmentInfo, type PackageStatus } from "@/api/client";
import { Button } from "@/components/ui/button";

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] ${
        ok ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"
      }`}
    >
      {ok ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
      {label}
    </span>
  );
}

function PackageRow({ p }: { p: PackageStatus }) {
  return (
    <li className="flex items-center justify-between gap-2 py-0.5 text-xs">
      <span className="font-mono text-zinc-300">{p.package}</span>
      {p.installed ? (
        <span className="text-emerald-400/90">{p.version ?? "ok"}</span>
      ) : (
        <span className="text-red-400/90">{p.error ?? "missing"}</span>
      )}
    </li>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">{title}</h3>
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2">{children}</div>
    </section>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3 py-0.5 text-xs">
      <span className="text-zinc-500">{k}</span>
      <span className="truncate text-right font-mono text-zinc-300">{v}</span>
    </div>
  );
}

function Body({ env }: { env: EnvironmentInfo }) {
  const { t } = useTranslation();
  if (!env.success) {
    return <p className="text-sm text-red-400">{env.error ?? t("env.scanFailed")}</p>;
  }
  const sys = env.system_info;
  const cli = env.cli_ai;
  const pkgs = env.packages;
  return (
    <div className="space-y-4">
      {sys && (
        <Section title={t("env.system")}>
          <Row k="OS" v={`${sys.os} ${sys.os_version ?? ""}`.trim()} />
          <Row k={t("env.arch")} v={String(sys.architecture ?? "")} />
          <Row k="Python" v={env.python_version ?? sys.python_version ?? ""} />
          {env.python_path && <Row k={t("env.pythonPath")} v={env.python_path} />}
        </Section>
      )}
      {cli && (
        <Section title={t("env.cliAi", { command: cli.command })}>
          <div className="flex items-center justify-between gap-2">
            <StatusBadge ok={cli.installed} label={cli.installed ? t("env.installed") : t("env.notInstalled")} />
            <span className="truncate text-right text-xs font-mono text-zinc-400">
              {cli.installed ? (cli.version ?? "") : (cli.detail ?? cli.error ?? "")}
            </span>
          </div>
        </Section>
      )}
      {pkgs && (
        <Section title={t("env.packages")}>
          <div className="mb-1">
            <StatusBadge
              ok={pkgs.all_required_installed}
              label={
                pkgs.all_required_installed ? t("env.allRequiredOk") : t("env.someRequiredMissing")
              }
            />
          </div>
          <div className="mb-0.5 text-[11px] uppercase tracking-wide text-zinc-500">
            {t("env.required")}
          </div>
          <ul>
            {pkgs.required.map((p) => (
              <PackageRow key={p.package} p={p} />
            ))}
          </ul>
          {pkgs.optional.length > 0 && (
            <>
              <div className="mb-0.5 mt-2 text-[11px] uppercase tracking-wide text-zinc-500">
                {t("env.optional")}
              </div>
              <ul>
                {pkgs.optional.map((p) => (
                  <PackageRow key={p.package} p={p} />
                ))}
              </ul>
            </>
          )}
        </Section>
      )}
    </div>
  );
}

export function EnvironmentDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["environment"],
    queryFn: fetchEnvironment,
    staleTime: Infinity, // 스캔이 무거우므로 자동 refetch 금지 — 새로고침 버튼으로만.
    refetchOnWindowFocus: false,
  });
  const rescan = useMutation({
    mutationFn: () => qc.invalidateQueries({ queryKey: ["environment"] }),
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 animate-in fade-in duration-150"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-[min(560px,92vw)] flex-col overflow-hidden rounded-xl border border-zinc-700 bg-zinc-950 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">{t("env.title")}</h2>
          <div className="flex items-center gap-1">
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7"
              title={t("env.rescan")}
              disabled={isLoading}
              onClick={() => rescan.mutate()}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />
            </Button>
            <Button size="icon" variant="ghost" className="h-7 w-7" title={t("common.close")} onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {isLoading && (
            <div className="flex items-center gap-2 py-8 text-sm text-zinc-400">
              <Loader2 className="h-4 w-4 animate-spin" /> {t("env.scanning")}
            </div>
          )}
          {isError && (
            <p className="text-sm text-red-400">
              {t("env.loadFailed", { message: (error as Error)?.message ?? "" })}
            </p>
          )}
          {data && <Body env={data} />}
        </div>
      </div>
    </div>
  );
}
