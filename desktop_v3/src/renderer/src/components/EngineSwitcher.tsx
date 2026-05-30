// SPDX-License-Identifier: AGPL-3.0-or-later
// AI 엔진 퀵스위치 (handoff §52/백로그 #14) — 헤더에서 설정 다이얼로그 없이 엔진 전환.
// GET /ai/engines 로 목록, POST /ai/engine 로 전환(런타임 + settings.json 영속). 엔진 0개면 숨김.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Bot } from "lucide-react";
import { fetchAiEngines, switchAiEngine } from "@/api/client";
import { toast } from "@/store/toastStore";

export function EngineSwitcher() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["aiEngines"], queryFn: fetchAiEngines });

  const mut = useMutation({
    mutationFn: (name: string) => switchAiEngine(name),
    onSuccess: (_r, name) => {
      qc.invalidateQueries({ queryKey: ["aiEngines"] });
      qc.invalidateQueries({ queryKey: ["settings"] }); // 설정 다이얼로그와 일관
      const e = data?.engines.find((x) => x.name === name);
      toast.success(t("engine.switched", { name: e?.display_name ?? name }));
    },
    onError: (e: Error) => toast.error(t("engine.switchFailed", { message: e.message })),
  });

  const engines = data?.engines ?? [];
  if (engines.length === 0) return null;
  const current = data?.current ?? engines.find((e) => e.is_current)?.name ?? engines[0].name;

  return (
    <div className="flex items-center gap-1" title={t("engine.label")}>
      <Bot className="h-3.5 w-3.5 text-discord-muted" />
      <select
        value={current}
        disabled={mut.isPending}
        onChange={(e) => mut.mutate(e.target.value)}
        className="max-w-[140px] rounded bg-discord-card px-1.5 py-0.5 text-xs text-discord-text focus:outline-none"
      >
        {engines.map((e) => (
          <option key={e.name} value={e.name}>
            {e.display_name}
            {e.available ? "" : ` (${t("engine.unavailable")})`}
          </option>
        ))}
      </select>
    </div>
  );
}
