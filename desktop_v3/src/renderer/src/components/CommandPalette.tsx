// SPDX-License-Identifier: AGPL-3.0-or-later
// 커맨드 팔레트 (handoff §51, 백로그 #16) — Ctrl+K 로 열어 세션 전환/실행/녹화/요소선택/
// 설정/테마/언어 등 주요 동작을 검색·실행. 기존 스토어/액션 재사용 (백엔드 무관, core 0줄).
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Activity,
  Circle,
  Copy,
  Download,
  Hash,
  HelpCircle,
  KeyRound,
  Languages,
  Moon,
  MousePointerClick,
  Play,
  Plus,
  Settings,
  Square,
  Sun,
  Upload,
} from "lucide-react";
import {
  createSession,
  duplicateSession,
  exportSession,
  fetchSessions,
  importSession,
} from "@/api/client";
import { useUiStore } from "@/store/uiStore";
import { usePickStore } from "@/store/pickStore";
import { useRecordStore } from "@/store/recordStore";
import { useThemeStore } from "@/store/themeStore";
import { useExecution } from "@/hooks/useExecution";
import { toast } from "@/store/toastStore";
import { currentLang, setLang } from "@/i18n";

interface Command {
  id: string;
  label: string;
  hint?: string;
  icon: ReactNode;
  run: () => void;
}

export function CommandPalette() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const open = useUiStore((s) => s.paletteOpen);
  const setOpen = useUiStore((s) => s.setPaletteOpen);
  const setSettingsOpen = useUiStore((s) => s.setSettingsOpen);
  const setEnvOpen = useUiStore((s) => s.setEnvOpen);
  const setOnboardingOpen = useUiStore((s) => s.setOnboardingOpen);
  const setSecretsOpen = useUiStore((s) => s.setSecretsOpen);
  const selectedSessionId = useUiStore((s) => s.selectedSessionId);
  const selectSession = useUiStore((s) => s.selectSession);

  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const activeRef = useRef<HTMLButtonElement>(null);

  const { data: sessions } = useQuery({
    queryKey: ["sessions"],
    queryFn: fetchSessions,
    enabled: open,
  });
  const { running, run, stop } = useExecution(selectedSessionId ?? "");
  const recording = useRecordStore((s) => s.recording);
  const startRec = useRecordStore((s) => s.start);
  const stopRec = useRecordStore((s) => s.stopReview);
  const startPick = usePickStore((s) => s.startPick);
  const theme = useThemeStore((s) => s.theme);
  const toggleTheme = useThemeStore((s) => s.toggle);
  const lang = (i18n.language || currentLang()).startsWith("ko") ? "ko" : "en";

  const createMut = useMutation({
    mutationFn: () => {
      const stamp = new Date().toISOString().slice(5, 16).replace("T", " ");
      return createSession(t("sidebar.newSessionName", { stamp }));
    },
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      selectSession(s.session_id);
      toast.success(t("session.created"));
    },
    onError: (e) => toast.error(t("session.createFailed", { message: (e as Error).message })),
  });

  // 팔레트 열릴 때 검색어/선택 리셋 + 입력 포커스.
  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const close = () => setOpen(false);

  // 컨텍스트(세션 선택/실행/녹화 상태)에 따라 사용 가능한 명령만 구성.
  const commands: Command[] = [];
  commands.push({
    id: "new-session",
    label: t("palette.newSession"),
    hint: "Ctrl+N",
    icon: <Plus className="h-4 w-4" />,
    run: () => createMut.mutate(),
  });
  if (selectedSessionId && !recording) {
    commands.push(
      running
        ? { id: "stop", label: t("palette.stop"), hint: "Ctrl+R", icon: <Square className="h-4 w-4" />, run: () => stop() }
        : { id: "run-all", label: t("palette.runAll"), hint: "Ctrl+R", icon: <Play className="h-4 w-4" />, run: () => run("all", null) },
    );
  }
  if (selectedSessionId && !running) {
    commands.push(
      recording
        ? {
            id: "stop-rec",
            label: t("palette.stopRecording"),
            icon: <Square className="h-4 w-4" />,
            run: () => stopRec(selectedSessionId),
          }
        : { id: "start-rec", label: t("palette.startRecording"), icon: <Circle className="h-4 w-4" />, run: () => startRec(selectedSessionId) },
    );
  }
  if (selectedSessionId && !recording) {
    commands.push({
      id: "pick",
      label: t("palette.pickElement"),
      icon: <MousePointerClick className="h-4 w-4" />,
      run: () => startPick(selectedSessionId ?? undefined),
    });
  }
  if (selectedSessionId) {
    const cur = (sessions ?? []).find((x) => x.session_id === selectedSessionId);
    commands.push({
      id: "duplicate",
      label: t("palette.duplicateSession"),
      icon: <Copy className="h-4 w-4" />,
      run: () =>
        duplicateSession(
          selectedSessionId,
          `${cur?.title || t("chat.untitled")} ${t("session.copySuffix")}`,
        )
          .then((s) => {
            qc.invalidateQueries({ queryKey: ["sessions"] });
            selectSession(s.session_id);
            toast.success(t("session.duplicated"));
          })
          .catch((e) => toast.error(t("session.duplicateFailed", { message: (e as Error).message }))),
    });
    commands.push({
      id: "export",
      label: t("palette.exportSession"),
      icon: <Download className="h-4 w-4" />,
      run: async () => {
        const dir = await window.ohdo.pickDirectory();
        if (!dir) return;
        try {
          const path = await exportSession(selectedSessionId, dir);
          toast.success(t("session.exported"));
          void window.ohdo.revealPath(path).catch(() => {});
        } catch (e) {
          toast.error(t("session.exportFailed", { message: (e as Error).message }));
        }
      },
    });
  }
  commands.push({
    id: "import",
    label: t("palette.importProject"),
    icon: <Upload className="h-4 w-4" />,
    run: async () => {
      const dir = await window.ohdo.pickDirectory();
      if (!dir) return;
      try {
        const s = await importSession(dir);
        qc.invalidateQueries({ queryKey: ["sessions"] });
        selectSession(s.session_id);
        toast.success(t("session.imported"));
      } catch (e) {
        toast.error(t("session.importFailed", { message: (e as Error).message }));
      }
    },
  });
  commands.push({
    id: "environment",
    label: t("palette.environment"),
    icon: <Activity className="h-4 w-4" />,
    run: () => setEnvOpen(true),
  });
  commands.push({
    id: "secrets",
    label: t("palette.secrets"),
    icon: <KeyRound className="h-4 w-4" />,
    run: () => setSecretsOpen(true),
  });
  commands.push({
    id: "onboarding",
    label: t("palette.onboarding"),
    icon: <HelpCircle className="h-4 w-4" />,
    run: () => setOnboardingOpen(true),
  });
  commands.push({
    id: "settings",
    label: t("palette.settings"),
    icon: <Settings className="h-4 w-4" />,
    run: () => setSettingsOpen(true),
  });
  commands.push({
    id: "theme",
    label: t("palette.toggleTheme"),
    icon: theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />,
    run: () => toggleTheme(),
  });
  commands.push({
    id: "lang",
    label: t("palette.toggleLanguage"),
    icon: <Languages className="h-4 w-4" />,
    run: () => setLang(lang === "ko" ? "en" : "ko"),
  });
  for (const s of sessions ?? []) {
    if (s.session_id === selectedSessionId) continue;
    commands.push({
      id: `go-${s.session_id}`,
      label: t("palette.goToSession", { title: s.title || t("chat.untitled") }),
      icon: <Hash className="h-4 w-4" />,
      run: () => selectSession(s.session_id),
    });
  }

  const q = query.trim().toLowerCase();
  const filtered = q ? commands.filter((c) => c.label.toLowerCase().includes(q)) : commands;
  const activeIdx = Math.min(active, Math.max(filtered.length - 1, 0));

  // 활성 항목이 보이는 영역 밖(특히 아래쪽)으로 가면 스크롤로 따라가게.
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [activeIdx]);

  if (!open) return null;

  const execute = (cmd?: Command) => {
    if (!cmd) return;
    close();
    cmd.run();
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center bg-black/50 pt-[18vh] animate-in fade-in duration-100"
      onClick={close}
    >
      <div
        className="w-[min(560px,92vw)] overflow-hidden rounded-xl border border-zinc-700 bg-zinc-950 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.stopPropagation();
              close();
            } else if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, filtered.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              execute(filtered[activeIdx]);
            }
          }}
          placeholder={t("palette.placeholder")}
          className="w-full border-b border-zinc-800 bg-transparent px-4 py-3 text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none"
        />
        <ul className="max-h-[50vh] overflow-y-auto py-1">
          {filtered.length === 0 && (
            <li className="px-4 py-6 text-center text-sm text-zinc-500">{t("palette.empty")}</li>
          )}
          {filtered.map((c, i) => (
            <li key={c.id}>
              <button
                type="button"
                ref={i === activeIdx ? activeRef : null}
                onMouseEnter={() => setActive(i)}
                onClick={() => execute(c)}
                className={`flex w-full items-center gap-3 px-4 py-2 text-left text-sm ${
                  i === activeIdx ? "bg-indigo-600/30 text-zinc-100" : "text-zinc-300 hover:bg-zinc-800/60"
                }`}
              >
                <span className="shrink-0 text-zinc-400">{c.icon}</span>
                <span className="flex-1 truncate">{c.label}</span>
                {c.hint && <span className="shrink-0 font-mono text-[11px] text-zinc-500">{c.hint}</span>}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
