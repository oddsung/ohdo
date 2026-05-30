// SPDX-License-Identifier: AGPL-3.0-or-later
// 시크릿 볼트 다이얼로그 (handoff §61, 백로그 #21) — 사용자 비밀(ID/PW/토큰) CRUD.
// core ADR0003 KeyringVault(OS keyring) 를 /secrets 브리지로 노출. **값은 절대 표시 안 됨**
// (목록은 label 만). 코드에서는 get_secret('label') 로 참조 — AI 가이드가 평문 대신 이 패턴 유도.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { KeyRound, Loader2, Plus, Trash2, X } from "lucide-react";
import { deleteSecret, fetchSecrets, setSecret } from "@/api/client";
import { toast } from "@/store/toastStore";
import { Button } from "@/components/ui/button";

const LABEL_RE = /^[a-z0-9_]{1,32}$/;

export function SecretsDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["secrets"], queryFn: fetchSecrets });
  const [label, setLabel] = useState("");
  const [value, setValue] = useState("");

  const available = data?.available ?? false;
  const labels = data?.labels ?? [];
  const labelValid = LABEL_RE.test(label);

  const addMut = useMutation({
    mutationFn: () => setSecret(label, value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["secrets"] });
      setLabel("");
      setValue("");
      toast.success(t("secrets.saved"));
    },
    onError: (e: Error) => toast.error(t("secrets.saveFailed", { message: e.message })),
  });
  const delMut = useMutation({
    mutationFn: (l: string) => deleteSecret(l),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["secrets"] });
      toast.success(t("secrets.deleted"));
    },
    onError: (e: Error) => toast.error(t("secrets.deleteFailed", { message: e.message })),
  });

  const submit = () => {
    if (!labelValid || !value || addMut.isPending) return;
    addMut.mutate();
  };

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
          <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
            <KeyRound className="h-4 w-4" /> {t("secrets.title")}
          </h2>
          <Button size="icon" variant="ghost" className="h-7 w-7" title={t("common.close")} onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3">
          <p className="mb-3 text-xs text-zinc-500">{t("secrets.hint")}</p>

          {isLoading && (
            <div className="flex items-center gap-2 py-4 text-sm text-zinc-400">
              <Loader2 className="h-4 w-4 animate-spin" />
            </div>
          )}

          {!isLoading && !available && (
            <p className="rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs text-amber-300">
              {t("secrets.unavailable")}
            </p>
          )}

          {available && (
            <>
              {/* 등록 폼 */}
              <div className="mb-4 space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
                <div className="flex flex-col gap-1">
                  <label className="text-[11px] uppercase tracking-wide text-zinc-500">
                    {t("secrets.label")}
                  </label>
                  <input
                    value={label}
                    onChange={(e) => setLabel(e.target.value)}
                    placeholder="gmail_pw"
                    className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none"
                  />
                  {label && !labelValid && (
                    <span className="text-[11px] text-red-400">{t("secrets.labelInvalid")}</span>
                  )}
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[11px] uppercase tracking-wide text-zinc-500">
                    {t("secrets.value")}
                  </label>
                  <input
                    type="password"
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") submit();
                    }}
                    placeholder="••••••••"
                    className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none"
                  />
                </div>
                <Button
                  size="sm"
                  className="w-full"
                  disabled={!labelValid || !value || addMut.isPending}
                  onClick={submit}
                >
                  {addMut.isPending ? (
                    <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Plus className="mr-1 h-3.5 w-3.5" />
                  )}
                  {labels.includes(label) ? t("secrets.update") : t("secrets.add")}
                </Button>
              </div>

              {/* 목록 */}
              <div className="mb-1 text-[11px] uppercase tracking-wide text-zinc-500">
                {t("secrets.registered", { count: labels.length })}
              </div>
              {labels.length === 0 ? (
                <p className="py-3 text-center text-xs text-zinc-600">{t("secrets.empty")}</p>
              ) : (
                <ul className="space-y-1">
                  {labels.map((l) => (
                    <li
                      key={l}
                      className="flex items-center justify-between gap-2 rounded-md bg-zinc-900/40 px-3 py-1.5"
                    >
                      <code className="text-xs text-zinc-300">{l}</code>
                      <span className="flex items-center gap-2">
                        <code className="text-[11px] text-zinc-600">{`get_secret('${l}')`}</code>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-6 w-6 text-zinc-500 hover:text-red-400"
                          title={t("secrets.delete")}
                          disabled={delMut.isPending}
                          onClick={() => {
                            if (window.confirm(t("secrets.confirmDelete", { label: l }))) delMut.mutate(l);
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
