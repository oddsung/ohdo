// SPDX-License-Identifier: AGPL-3.0-or-later
// 좌측 세션 사이드바 — 목록 + 새 세션 생성 + 브리지 상태 + 테마/언어 토글.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Copy, Download, Pencil, Plus, Trash2, Upload } from "lucide-react";
import {
  deleteSession,
  duplicateSession,
  exportSession,
  fetchHealth,
  fetchSessions,
  importSession,
  renameSession,
  type SessionSummary,
} from "@/api/client";
import { SettingsDialog } from "@/components/SettingsDialog";
import { EnvironmentDialog } from "@/components/EnvironmentDialog";
import { SecretsDialog } from "@/components/SecretsDialog";
import { useUiStore } from "@/store/uiStore";
import { toast } from "@/store/toastStore";
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
  onRenameSubmit,
  onDuplicate,
  onExport,
  onDelete,
}: {
  s: SessionSummary;
  busy: boolean;
  onRenameSubmit: (title: string) => void;
  onDuplicate: () => void;
  onExport: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const selectedId = useUiStore((st) => st.selectedSessionId);
  const select = useUiStore((st) => st.selectSession);
  const active = selectedId === s.session_id;
  // 인라인 이름 편집 (§89) — Electron 은 window.prompt 미지원이라 행 내 input 으로 편집.
  // Enter=저장, Esc/blur=취소.
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const startEdit = () => {
    setDraft(s.title || "");
    setEditing(true);
  };
  const commitEdit = () => {
    const title = draft.trim();
    setEditing(false);
    if (!title || title === s.title) return;
    onRenameSubmit(title);
  };
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => select(s.session_id)}
      onKeyDown={(e) => {
        if (!editing && (e.key === "Enter" || e.key === " ")) select(s.session_id);
      }}
      className={`group w-full cursor-pointer rounded px-2 py-2 text-left transition-colors ${
        active ? "bg-discord-card text-white" : "text-discord-muted hover:bg-discord-card/60"
      }`}
    >
      <div className="flex items-center gap-1">
        {editing ? (
          <input
            autoFocus
            data-testid="session-rename-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === "Enter") commitEdit();
              if (e.key === "Escape") setEditing(false);
            }}
            onBlur={() => setEditing(false)}
            className="w-0 flex-1 rounded border border-discord-accent bg-discord-card px-1.5 py-0.5 text-sm text-white outline-none"
          />
        ) : (
          <span className="flex-1 truncate text-sm font-medium">
            {s.title || t("chat.untitled")}
          </span>
        )}
        <span className="flex items-center opacity-0 transition-opacity group-hover:opacity-100">
          <Button
            size="icon"
            variant="ghost"
            className="h-5 w-5 text-discord-muted hover:text-white"
            title={t("session.rename")}
            disabled={busy}
            onClick={(e) => {
              e.stopPropagation();
              startEdit();
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
            className="h-5 w-5 text-discord-muted hover:text-white"
            title={t("session.export")}
            disabled={busy}
            onClick={(e) => {
              e.stopPropagation();
              onExport();
            }}
          >
            <Download className="h-3 w-3" />
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
  const { t } = useTranslation();
  const select = useUiStore((st) => st.selectSession);
  const closeTab = useUiStore((st) => st.closeTab);
  const settingsOpen = useUiStore((st) => st.settingsOpen);
  const setSettingsOpen = useUiStore((st) => st.setSettingsOpen);
  const envOpen = useUiStore((st) => st.envOpen);
  const setEnvOpen = useUiStore((st) => st.setEnvOpen);
  const secretsOpen = useUiStore((st) => st.secretsOpen);
  const setSecretsOpen = useUiStore((st) => st.setSecretsOpen);
  // 새 세션은 이름 입력 다이얼로그(§89, NewSessionDialog)를 연다 — 생성 로직은 그쪽.
  const setNewSessionOpen = useUiStore((st) => st.setNewSessionOpen);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["sessions"],
    queryFn: fetchSessions,
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
      closeTab(id); // 탭에서 제거 + 활성 탭이었으면 인접 탭으로 전환
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
  // ── 내보내기 / 가져오기 (§47 #15) — 네이티브 폴더 선택 후 브리지 호출 ──
  const exportMut = useMutation({
    mutationFn: (vars: { id: string; dir: string }) => exportSession(vars.id, vars.dir),
    onSuccess: (path) => {
      toast.success(t("session.exported"));
      void window.ohdo.revealPath(path).catch(() => {});
    },
    onError: (e: Error) => toast.error(t("session.exportFailed", { message: e.message })),
  });
  const importMut = useMutation({
    mutationFn: (dir: string) => importSession(dir),
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      select(session.session_id);
      toast.success(t("session.imported"));
    },
    onError: (e: Error) => toast.error(t("session.importFailed", { message: e.message })),
  });
  const onExportSession = async (s: SessionSummary) => {
    const dir = await window.ohdo.pickDirectory();
    if (dir) exportMut.mutate({ id: s.session_id, dir });
  };
  const onImport = async () => {
    const dir = await window.ohdo.pickDirectory();
    if (dir) importMut.mutate(dir);
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
        : exportMut.isPending
          ? exportMut.variables?.id
          : null;

  return (
    <aside className="flex h-full w-60 flex-col bg-discord-sidebar">
      <header className="flex h-12 items-center justify-between border-b border-black/20 px-4 shadow-sm">
        <span className="font-semibold">{t("sidebar.sessions")}</span>
        <div className="flex items-center gap-0.5">
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7 text-discord-muted hover:text-white"
            title={t("session.import")}
            disabled={importMut.isPending}
            onClick={onImport}
          >
            <Upload className="h-4 w-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7 text-discord-muted hover:text-white"
            title={t("sidebar.newSession")}
            onClick={() => setNewSessionOpen(true)}
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
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
              onRenameSubmit={(title) => renameMut.mutate({ id: s.session_id, title })}
              onDuplicate={() => duplicateMut.mutate(s)}
              onExport={() => onExportSession(s)}
              onDelete={() => onDeleteSession(s)}
            />
          ))}
        </div>
      </ScrollArea>
      <footer className="flex items-center border-t border-black/20 px-4 py-2">
        {/* 전역 유틸(도움말/환경/설정/언어/테마)은 상단 TitleBar 메뉴로 이동(§59→§78). 여기는 브리지 상태만. */}
        <HealthDot />
      </footer>
      {settingsOpen && <SettingsDialog onClose={() => setSettingsOpen(false)} />}
      {envOpen && <EnvironmentDialog onClose={() => setEnvOpen(false)} />}
      {secretsOpen && <SecretsDialog onClose={() => setSecretsOpen(false)} />}
    </aside>
  );
}
