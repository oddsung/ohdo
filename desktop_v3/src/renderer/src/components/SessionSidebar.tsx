// SPDX-License-Identifier: AGPL-3.0-or-later
// 좌측 세션 사이드바 — 목록 + 새 세션 생성 + 브리지 상태 + 테마/언어 토글.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Activity, Copy, Languages, Moon, Pencil, Plus, Settings, Sun, Trash2 } from "lucide-react";
import {
  createSession,
  deleteSession,
  duplicateSession,
  fetchHealth,
  fetchSessions,
  renameSession,
  type SessionSummary,
} from "@/api/client";
import { SettingsDialog } from "@/components/SettingsDialog";
import { EnvironmentDialog } from "@/components/EnvironmentDialog";
import { useUiStore } from "@/store/uiStore";
import { useThemeStore } from "@/store/themeStore";
import { toast } from "@/store/toastStore";
import { currentLang, setLang } from "@/i18n";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

function HealthDot() {
  const { t } = useTranslation();
  const { data, isError } = useQuery({ queryKey: ["health"], queryFn: fetchHealth });
  const ok = !!data && !isError && data.status === "ok";
  return (
    <div className="flex items-center gap-2 text-xs text-discord-muted">
      <span
        className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-discord-green" : "bg-red-500"}`}
        title={ok ? "bridge online" : "bridge offline"}
      />
      {ok ? t("bridge.online", { version: data?.version }) : t("bridge.offline")}
    </div>
  );
}

function SessionRow({
  s,
  busy,
  onRename,
  onDuplicate,
  onDelete,
}: {
  s: SessionSummary;
  busy: boolean;
  onRename: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const selectedId = useUiStore((st) => st.selectedSessionId);
  const select = useUiStore((st) => st.selectSession);
  const active = selectedId === s.session_id;
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => select(s.session_id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") select(s.session_id);
      }}
      className={`group w-full cursor-pointer rounded px-2 py-2 text-left transition-colors ${
        active ? "bg-discord-card text-white" : "text-discord-muted hover:bg-discord-card/60"
      }`}
    >
      <div className="flex items-center gap-1">
        <span className="flex-1 truncate text-sm font-medium">{s.title || t("chat.untitled")}</span>
        <span className="flex items-center opacity-0 transition-opacity group-hover:opacity-100">
          <Button
            size="icon"
            variant="ghost"
            className="h-5 w-5 text-discord-muted hover:text-white"
            title={t("session.rename")}
            disabled={busy}
            onClick={(e) => {
              e.stopPropagation();
              onRename();
            }}
          >
            <Pencil className="h-3 w-3" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-5 w-5 text-discord-muted hover:text-white"
            title={t("session.duplicate")}
            disabled={busy}
            onClick={(e) => {
              e.stopPropagation();
              onDuplicate();
            }}
          >
            <Copy className="h-3 w-3" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-5 w-5 text-discord-muted hover:text-red-400"
            title={t("session.delete")}
            disabled={busy}
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </span>
      </div>
      <div className="mt-0.5 text-xs text-discord-muted">
        {t("chat.stepsInfo", {
          project: s.project_type,
          done: s.completed_steps,
          total: s.total_steps,
        })}
      </div>
    </div>
  );
}

export function SessionSidebar() {
  const qc = useQueryClient();
  const { t, i18n } = useTranslation();
  const select = useUiStore((st) => st.selectSession);
  const selectedSessionId = useUiStore((st) => st.selectedSessionId);
  const settingsOpen = useUiStore((st) => st.settingsOpen);
  const setSettingsOpen = useUiStore((st) => st.setSettingsOpen);
  const envOpen = useUiStore((st) => st.envOpen);
  const setEnvOpen = useUiStore((st) => st.setEnvOpen);
  const [creating, setCreating] = useState(false);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["sessions"],
    queryFn: fetchSessions,
  });

  const theme = useThemeStore((st) => st.theme);
  const toggleTheme = useThemeStore((st) => st.toggle);
  const lang = (i18n.language || currentLang()).startsWith("ko") ? "ko" : "en";

  const createMut = useMutation({
    mutationFn: () => {
      const stamp = new Date().toISOString().slice(5, 16).replace("T", " ");
      return createSession(t("sidebar.newSessionName", { stamp }));
    },
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      select(session.session_id);
      toast.success(t("session.created"));
    },
    onError: (e) => toast.error(t("session.createFailed", { message: (e as Error).message })),
    onSettled: () => setCreating(false),
  });

  // ── 세션 이름변경 / 삭제 (§47 (A)유형) ──
  const renameMut = useMutation({
    mutationFn: (vars: { id: string; title: string }) => renameSession(vars.id, vars.title),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      qc.invalidateQueries({ queryKey: ["session", vars.id] });
      toast.success(t("session.renamed"));
    },
    onError: (e: Error) => toast.error(t("session.renameFailed", { message: e.message })),
  });
  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteSession(id),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      if (selectedSessionId === id) select(null);
      toast.success(t("session.deleted"));
    },
    onError: (e: Error) => toast.error(t("session.deleteFailed", { message: e.message })),
  });
  const duplicateMut = useMutation({
    mutationFn: (s: SessionSummary) =>
      duplicateSession(
        s.session_id,
        `${s.title || t("chat.untitled")} ${t("session.copySuffix")}`,
      ),
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      select(session.session_id);
      toast.success(t("session.duplicated"));
    },
    onError: (e: Error) => toast.error(t("session.duplicateFailed", { message: e.message })),
  });
  const onRenameSession = (s: SessionSummary) => {
    const next = window.prompt(t("session.renamePrompt"), s.title || "");
    const title = (next ?? "").trim();
    if (!title || title === s.title) return;
    renameMut.mutate({ id: s.session_id, title });
  };
  const onDeleteSession = (s: SessionSummary) => {
    if (!window.confirm(t("session.confirmDelete", { title: s.title || t("chat.untitled") }))) return;
    deleteMut.mutate(s.session_id);
  };
  const busyId = renameMut.isPending
    ? renameMut.variables?.id
    : deleteMut.isPending
      ? deleteMut.variables
      : duplicateMut.isPending
        ? duplicateMut.variables?.session_id
        : null;

  return (
    <aside className="flex h-full w-60 flex-col bg-discord-sidebar">
      <header className="flex h-12 items-center justify-between border-b border-black/20 px-4 shadow-sm">
        <span className="font-semibold">{t("sidebar.sessions")}</span>
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7 text-discord-muted hover:text-white"
          title={t("sidebar.newSession")}
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
          {isLoading && (
            <p className="px-2 py-4 text-sm text-discord-muted">{t("sidebar.loading")}</p>
          )}
          {isError && (
            <p className="px-2 py-4 text-sm text-red-400">
              {t("sidebar.error", { message: (error as Error).message })}
            </p>
          )}
          {data && data.length === 0 && (
            <p className="px-2 py-4 text-sm text-discord-muted">{t("sidebar.empty")}</p>
          )}
          {data?.map((s) => (
            <SessionRow
              key={s.session_id}
              s={s}
              busy={busyId === s.session_id}
              onRename={() => onRenameSession(s)}
              onDuplicate={() => duplicateMut.mutate(s)}
              onDelete={() => onDeleteSession(s)}
            />
          ))}
        </div>
      </ScrollArea>
      <footer className="flex items-center justify-between border-t border-black/20 px-4 py-2">
        <HealthDot />
        <div className="flex items-center gap-1">
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6 text-discord-muted hover:text-white"
            title={t("env.title")}
            onClick={() => setEnvOpen(true)}
          >
            <Activity className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6 text-discord-muted hover:text-white"
            title={t("settings.title")}
            onClick={() => setSettingsOpen(true)}
          >
            <Settings className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6 text-discord-muted hover:text-white"
            title={lang === "ko" ? t("sidebar.toEnglish") : t("sidebar.toKorean")}
            onClick={() => setLang(lang === "ko" ? "en" : "ko")}
          >
            <Languages className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6 text-discord-muted hover:text-white"
            title={theme === "dark" ? t("sidebar.toLightTheme") : t("sidebar.toDarkTheme")}
            onClick={toggleTheme}
          >
            {theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
          </Button>
        </div>
      </footer>
      {settingsOpen && <SettingsDialog onClose={() => setSettingsOpen(false)} />}
      {envOpen && <EnvironmentDialog onClose={() => setEnvOpen(false)} />}
    </aside>
  );
}
