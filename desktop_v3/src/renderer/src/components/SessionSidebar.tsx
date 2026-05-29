// SPDX-License-Identifier: AGPL-3.0-or-later
// 좌측 세션 사이드바 — 목록 + 새 세션 생성 + 브리지 상태.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Moon, Plus, Sun } from "lucide-react";
import { createSession, fetchHealth, fetchSessions, type SessionSummary } from "@/api/client";
import { useUiStore } from "@/store/uiStore";
import { useThemeStore } from "@/store/themeStore";
import { toast } from "@/store/toastStore";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

function HealthDot() {
  const { data, isError } = useQuery({ queryKey: ["health"], queryFn: fetchHealth });
  const ok = !!data && !isError && data.status === "ok";
  return (
    <div className="flex items-center gap-2 text-xs text-discord-muted">
      <span
        className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-discord-green" : "bg-red-500"}`}
        title={ok ? "bridge online" : "bridge offline"}
      />
      {ok ? `bridge v${data?.version}` : "bridge 연결 안됨"}
    </div>
  );
}

function SessionRow({ s }: { s: SessionSummary }) {
  const selectedId = useUiStore((st) => st.selectedSessionId);
  const select = useUiStore((st) => st.selectSession);
  const active = selectedId === s.session_id;
  return (
    <button
      onClick={() => select(s.session_id)}
      className={`w-full rounded px-2 py-2 text-left transition-colors ${
        active ? "bg-discord-card text-white" : "text-discord-muted hover:bg-discord-card/60"
      }`}
    >
      <div className="truncate text-sm font-medium">{s.title || "(제목 없음)"}</div>
      <div className="mt-0.5 text-xs text-discord-muted">
        {s.project_type} · {s.completed_steps}/{s.total_steps} steps
      </div>
    </button>
  );
}

export function SessionSidebar() {
  const qc = useQueryClient();
  const select = useUiStore((st) => st.selectSession);
  const [creating, setCreating] = useState(false);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["sessions"],
    queryFn: fetchSessions,
  });

  const theme = useThemeStore((st) => st.theme);
  const toggleTheme = useThemeStore((st) => st.toggle);

  const createMut = useMutation({
    mutationFn: () => {
      const stamp = new Date().toISOString().slice(5, 16).replace("T", " ");
      return createSession(`v3 새 세션 ${stamp}`);
    },
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      select(session.session_id);
      toast.success("새 세션 생성됨");
    },
    onError: (e) => toast.error(`세션 생성 실패: ${(e as Error).message}`),
    onSettled: () => setCreating(false),
  });

  return (
    <aside className="flex h-full w-60 flex-col bg-discord-sidebar">
      <header className="flex h-12 items-center justify-between border-b border-black/20 px-4 shadow-sm">
        <span className="font-semibold">세션</span>
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7 text-discord-muted hover:text-white"
          title="새 세션"
          disabled={creating || createMut.isPending}
          onClick={() => {
            setCreating(true);
            createMut.mutate();
          }}
        >
          <Plus className="h-4 w-4" />
        </Button>
      </header>
      <ScrollArea className="flex-1">
        <div className="space-y-1 p-2">
          {isLoading && <p className="px-2 py-4 text-sm text-discord-muted">불러오는 중…</p>}
          {isError && (
            <p className="px-2 py-4 text-sm text-red-400">에러: {(error as Error).message}</p>
          )}
          {data && data.length === 0 && (
            <p className="px-2 py-4 text-sm text-discord-muted">세션이 없습니다. + 로 생성하세요.</p>
          )}
          {data?.map((s) => <SessionRow key={s.session_id} s={s} />)}
        </div>
      </ScrollArea>
      <footer className="flex items-center justify-between border-t border-black/20 px-4 py-2">
        <HealthDot />
        <Button
          size="icon"
          variant="ghost"
          className="h-6 w-6 text-discord-muted hover:text-white"
          title={theme === "dark" ? "라이트 테마로" : "다크 테마로"}
          onClick={toggleTheme}
        >
          {theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
        </Button>
      </footer>
    </aside>
  );
}
