// SPDX-License-Identifier: AGPL-3.0-or-later
// 설정 다이얼로그 (handoff §47 #20) — AI 엔진/모델/키 등 config/settings.json 편집.
// 브리지 GET/PUT /settings 사용. core 무관 (v2 와 동일 파일 공유 → 설정이 양쪽에 반영).
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Loader2, X } from "lucide-react";
import { fetchSettings, saveSettings, type AppSettings } from "@/api/client";
import { toast } from "@/store/toastStore";
import { Button } from "@/components/ui/button";

type Dict = Record<string, unknown>;

/** api_key 류는 password 로 마스킹. */
function isSecretKey(key: string): boolean {
  return /key|secret|token|password/i.test(key);
}

/** 단일 설정 값 입력 — 타입(bool/number/string)에 따라 컨트롤 분기. */
function Field({
  k,
  value,
  onChange,
}: {
  k: string;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const id = `set-${k}`;
  if (typeof value === "boolean") {
    return (
      <label htmlFor={id} className="flex items-center gap-2 py-1 text-sm text-zinc-300">
        <input
          id={id}
          type="checkbox"
          checked={value}
          onChange={(e) => onChange(e.target.checked)}
          className="accent-indigo-500"
        />
        <span className="font-mono text-xs">{k}</span>
      </label>
    );
  }
  const isNum = typeof value === "number";
  return (
    <div className="py-1">
      <label htmlFor={id} className="block text-xs font-mono text-zinc-400 mb-0.5">
        {k}
      </label>
      <input
        id={id}
        type={isSecretKey(k) ? "password" : isNum ? "number" : "text"}
        value={value == null ? "" : String(value)}
        onChange={(e) =>
          onChange(isNum && e.target.value !== "" ? Number(e.target.value) : e.target.value)
        }
        className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
      />
    </div>
  );
}

export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["settings"],
    queryFn: fetchSettings,
  });
  const [draft, setDraft] = useState<AppSettings | null>(null);

  useEffect(() => {
    if (data?.settings) setDraft(structuredClone(data.settings));
  }, [data]);

  const saveMut = useMutation({
    mutationFn: (s: AppSettings) => saveSettings(s),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      toast.success(t("settings.saved"));
      onClose();
    },
    onError: (e: Error) => toast.error(t("settings.saveFailed", { message: e.message })),
  });

  const ai = (draft?.ai as Dict | undefined) ?? undefined;
  const engines = (ai?.available_engines as Record<string, Dict> | undefined) ?? {};
  const engineKeys = Object.keys(engines);
  const selected = (ai?.selected as string | undefined) ?? engineKeys[0] ?? "";
  const engineCfg = engines[selected] ?? {};

  const setSelected = (name: string) =>
    setDraft((d) => {
      if (!d) return d;
      const next = structuredClone(d) as Dict;
      (next.ai as Dict) = { ...(next.ai as Dict), selected: name };
      return next as AppSettings;
    });

  const setEngineField = (key: string, v: unknown) =>
    setDraft((d) => {
      if (!d) return d;
      const next = structuredClone(d) as Dict;
      const nai = next.ai as Dict;
      const nengines = nai.available_engines as Record<string, Dict>;
      nengines[selected] = { ...nengines[selected], [key]: v };
      return next as AppSettings;
    });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 animate-in fade-in duration-150"
      onClick={onClose}
    >
      <div
        className="w-[min(560px,92vw)] max-h-[85vh] overflow-hidden rounded-xl border border-zinc-700 bg-zinc-950 shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">{t("settings.title")}</h2>
          <button
            type="button"
            onClick={onClose}
            title={t("common.close")}
            className="p-1 rounded hover:bg-zinc-800 text-zinc-400"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
          {isLoading && (
            <div className="flex items-center gap-2 text-sm text-zinc-400">
              <Loader2 className="w-4 h-4 animate-spin" /> {t("settings.loading")}
            </div>
          )}
          {isError && (
            <p className="text-sm text-red-400">
              {t("settings.loadFailed", { message: (error as Error)?.message ?? "" })}
            </p>
          )}
          {draft && (
            <>
              <section>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 mb-1.5">
                  {t("settings.aiEngine")}
                </h3>
                {engineKeys.length > 0 ? (
                  <select
                    value={selected}
                    onChange={(e) => setSelected(e.target.value)}
                    className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
                  >
                    {engineKeys.map((k) => (
                      <option key={k} value={k}>
                        {k}
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="text-xs text-zinc-500">{t("settings.noEngines")}</p>
                )}
              </section>

              {Object.keys(engineCfg).length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 mb-1">
                    {t("settings.engineConfig", { engine: selected })}
                  </h3>
                  <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2">
                    {Object.entries(engineCfg).map(([k, v]) => (
                      <Field key={k} k={k} value={v} onChange={(nv) => setEngineField(k, nv)} />
                    ))}
                  </div>
                  <p className="mt-1 text-[11px] text-zinc-500">{t("settings.secretHint")}</p>
                </section>
              )}
            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => draft && saveMut.mutate(draft)}
            disabled={!draft || saveMut.isPending}
          >
            {saveMut.isPending && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />}
            {t("common.save")}
          </Button>
        </div>
      </div>
    </div>
  );
}
