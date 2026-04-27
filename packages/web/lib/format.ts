// 상태 색·시각·duration 포맷터.

export type ExecutionStatus =
  | "queued"
  | "accepted"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export const TERMINAL_STATUSES: ReadonlySet<ExecutionStatus> = new Set([
  "completed",
  "failed",
  "cancelled",
]);

export const STATUS_STYLES: Record<ExecutionStatus, string> = {
  queued: "bg-gray-100 text-gray-700 border-gray-200",
  accepted: "bg-blue-100 text-blue-700 border-blue-200",
  running: "bg-indigo-100 text-indigo-700 border-indigo-200 animate-pulse",
  completed: "bg-green-100 text-green-700 border-green-200",
  failed: "bg-red-100 text-red-700 border-red-200",
  cancelled: "bg-amber-100 text-amber-700 border-amber-200",
};

export const STATUS_LABELS: Record<ExecutionStatus, string> = {
  queued: "대기",
  accepted: "수락",
  running: "실행 중",
  completed: "완료",
  failed: "실패",
  cancelled: "취소",
};

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  // YYYY-MM-DD HH:mm:ss in local timezone
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    d.getFullYear() +
    "-" +
    pad(d.getMonth() + 1) +
    "-" +
    pad(d.getDate()) +
    " " +
    pad(d.getHours()) +
    ":" +
    pad(d.getMinutes()) +
    ":" +
    pad(d.getSeconds())
  );
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  const totalSec = ms / 1000;
  if (totalSec < 60) return `${totalSec.toFixed(1)}s`;
  const m = Math.floor(totalSec / 60);
  const s = Math.floor(totalSec % 60);
  return `${m}m ${s}s`;
}

export function shortenExecId(id: string | null | undefined): string {
  if (!id) return "";
  if (id.length < 18) return id;
  return id.slice(0, 9) + "…" + id.slice(-4);
}
