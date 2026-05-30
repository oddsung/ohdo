// SPDX-License-Identifier: AGPL-3.0-or-later
// 온보딩 위저드 (handoff §58/백로그 #19) — 첫 실행 시 자동 + 사이드바/팔레트로 재오픈.
// 순수 프론트: 환경 점검(GET /environment)/엔진 전환(GET·POST /ai/*)/세션 생성은 모두
// 기존 엔드포인트 재사용 — core/api_server 0줄. 완료/건너뛰기 시 localStorage 플래그 영속.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Check, Loader2, X } from "lucide-react";
import {
  createSession,
  fetchAiEngines,
  fetchEnvironment,
  switchAiEngine,
} from "@/api/client";
import { useUiStore } from "@/store/uiStore";
import { toast } from "@/store/toastStore";
import { currentLang, setLang, type Lang } from "@/i18n";
import { Button } from "@/components/ui/button";

const ONBOARDED_KEY = "ohdo.onboarded";

/** 첫 실행 여부 — 아직 온보딩을 마치지 않았으면 true. */
export function shouldShowOnboarding(): boolean {
  return localStorage.getItem(ONBOARDED_KEY) !== "1";
}

/** 온보딩 완료 표시 (자동 재오픈 방지). */
export function markOnboarded(): void {
  localStorage.setItem(ONBOARDED_KEY, "1");
}

const TOTAL = 4;

function LangPicker() {
  const { t, i18n } = useTranslation();
  const active = (i18n.language || currentLang()).startsWith("ko") ? "ko" : "en";
  const opt = (lang: Lang, label: string) => (
    <button
      type="button"
      onClick={() => setLang(lang)}
      className={`rounded-md border px-3 py-1.5 text-sm transition-colors ${
        active === lang
          ? "border-indigo-500 bg-indigo-600/20 text-zinc-100"
          : "border-zinc-700 text-zinc-400 hover:bg-zinc-800/60"
      }`}
    >
      {label}
    </button>
  );
  return (
    <div>
      <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-500">
        {t("onboarding.chooseLang")}
      </div>
      <div className="flex gap-2">
        {opt("ko", "한국어")}
        {opt("en", "English")}
      </div>
    </div>
  );
}

function EnvStep() {
  const { t } = useTranslation();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["environment"],
    queryFn: fetchEnvironment,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
  return (
    <div className="space-y-3">
      <p className="text-sm text-zinc-400">{t("onboarding.envBody")}</p>
      {isLoading && (
        <div className="flex items-center gap-2 py-4 text-sm text-zinc-400">
          <Loader2 className="h-4 w-4 animate-spin" /> {t("env.scanning")}
        </div>
      )}
      {isError && (
        <p className="text-sm text-red-400">
          {t("env.loadFailed", { message: (error as Error)?.message ?? "" })}
        </p>
      )}
      {data?.success && (
        <div className="space-y-1.5 rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-xs">
          <div className="flex justify-between gap-3">
            <span className="text-zinc-500">Python</span>
            <span className="truncate text-right font-mono text-zinc-300">
              {data.python_version ?? data.system_info?.python_version ?? "—"}
            </span>
          </div>
          {data.cli_ai && (
            <div className="flex justify-between gap-3">
              <span className="text-zinc-500">{t("env.cliAi", { command: data.cli_ai.command })}</span>
              <span
                className={data.cli_ai.installed ? "text-emerald-400/90" : "text-red-400/90"}
              >
                {data.cli_ai.installed ? t("env.installed") : t("env.notInstalled")}
              </span>
            </div>
          )}
          {data.packages && (
            <div className="flex justify-between gap-3">
              <span className="text-zinc-500">{t("env.packages")}</span>
              <span
                className={
                  data.packages.all_required_installed ? "text-emerald-400/90" : "text-red-400/90"
                }
              >
                {data.packages.all_required_installed
                  ? t("env.allRequiredOk")
                  : t("env.someRequiredMissing")}
              </span>
            </div>
          )}
        </div>
      )}
      {data && !data.success && (
        <p className="text-sm text-red-400">{data.error ?? t("env.scanFailed")}</p>
      )}
    </div>
  );
}

function EngineStep() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["aiEngines"], queryFn: fetchAiEngines });
  const mut = useMutation({
    mutationFn: (name: string) => switchAiEngine(name),
    onSuccess: (_r, name) => {
      qc.invalidateQueries({ queryKey: ["aiEngines"] });
      qc.invalidateQueries({ queryKey: ["settings"] });
      const e = data?.engines.find((x) => x.name === name);
      toast.success(t("engine.switched", { name: e?.display_name ?? name }));
    },
    onError: (e: Error) => toast.error(t("engine.switchFailed", { message: e.message })),
  });
  const engines = data?.engines ?? [];
  const current = data?.current ?? engines.find((e) => e.is_current)?.name ?? null;
  return (
    <div className="space-y-3">
      <p className="text-sm text-zinc-400">{t("onboarding.engineBody")}</p>
      {isLoading && (
        <div className="flex items-center gap-2 py-4 text-sm text-zinc-400">
          <Loader2 className="h-4 w-4 animate-spin" />
        </div>
      )}
      {!isLoading && engines.length === 0 && (
        <p className="text-sm text-amber-400/90">{t("onboarding.noEngines")}</p>
      )}
      <div className="space-y-1.5">
        {engines.map((e) => {
          const selected = e.name === current;
          return (
            <button
              key={e.name}
              type="button"
              disabled={mut.isPending}
              onClick={() => mut.mutate(e.name)}
              className={`flex w-full items-center justify-between gap-2 rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                selected
                  ? "border-indigo-500 bg-indigo-600/20 text-zinc-100"
                  : "border-zinc-700 text-zinc-300 hover:bg-zinc-800/60"
              }`}
            >
              <span className="truncate">
                {e.display_name}
                {e.available ? "" : ` (${t("engine.unavailable")})`}
              </span>
              {selected && <Check className="h-4 w-4 shrink-0 text-indigo-300" />}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function OnboardingWizard({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const selectSession = useUiStore((s) => s.selectSession);
  const [step, setStep] = useState(0);

  const finish = () => {
    markOnboarded();
    onClose();
  };

  const createMut = useMutation({
    mutationFn: () => {
      const stamp = new Date().toISOString().slice(5, 16).replace("T", " ");
      return createSession(t("sidebar.newSessionName", { stamp }));
    },
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      selectSession(s.session_id);
      toast.success(t("session.created"));
      finish();
    },
    onError: (e: Error) => toast.error(t("session.createFailed", { message: e.message })),
  });

  const titles = [
    t("onboarding.welcomeTitle"),
    t("onboarding.envTitle"),
    t("onboarding.engineTitle"),
    t("onboarding.finishTitle"),
  ];
  const isLast = step === TOTAL - 1;

  return (
    <div className="fixed inset-0 z-[55] flex items-center justify-center bg-black/60 animate-in fade-in duration-150">
      <div className="flex max-h-[85vh] w-[min(520px,92vw)] flex-col overflow-hidden rounded-xl border border-zinc-700 bg-zinc-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">{titles[step]}</h2>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            title={t("common.close")}
            onClick={finish}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4">
          {step === 0 && (
            <div className="space-y-4">
              <p className="text-sm text-zinc-300">{t("onboarding.welcomeBody")}</p>
              <LangPicker />
            </div>
          )}
          {step === 1 && <EnvStep />}
          {step === 2 && <EngineStep />}
          {step === 3 && (
            <div className="space-y-4">
              <p className="text-sm text-zinc-300">{t("onboarding.finishBody")}</p>
              <Button
                variant="default"
                disabled={createMut.isPending}
                onClick={() => createMut.mutate()}
              >
                {createMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {t("onboarding.createFirst")}
              </Button>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-zinc-800 px-4 py-3">
          <span className="text-xs text-zinc-500">{t("onboarding.step", { n: step + 1, total: TOTAL })}</span>
          <div className="flex items-center gap-2">
            {step > 0 && (
              <Button variant="ghost" size="sm" onClick={() => setStep((s) => s - 1)}>
                {t("onboarding.back")}
              </Button>
            )}
            {!isLast ? (
              <>
                <Button variant="ghost" size="sm" className="text-zinc-500" onClick={finish}>
                  {t("onboarding.skip")}
                </Button>
                <Button variant="default" size="sm" onClick={() => setStep((s) => s + 1)}>
                  {t("onboarding.next")}
                </Button>
              </>
            ) : (
              <Button variant="default" size="sm" onClick={finish}>
                {t("onboarding.finish")}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
