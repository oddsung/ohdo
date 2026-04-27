"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { TERMINAL_STATUSES, type ExecutionStatus } from "@/lib/format";
import type { LogEntry, LogListResponse } from "@/lib/executions";

const STREAM_OPTIONS = [
  { value: "all", label: "전체" },
  { value: "engine", label: "엔진" },
  { value: "stdout", label: "stdout" },
  { value: "stderr", label: "stderr" },
] as const;

const PAGE_SIZE = 200;
const POLL_INTERVAL_MS = 3000;

const STREAM_LINE_CLS: Record<string, string> = {
  engine: "text-gray-500",
  stdout: "text-gray-900",
  stderr: "text-red-700",
};

export function ExecutionLogsTail({
  executionId,
  initialStatus,
  initialItems,
}: {
  executionId: string;
  initialStatus: ExecutionStatus;
  initialItems: LogEntry[];
}) {
  const [items, setItems] = useState<LogEntry[]>(initialItems);
  const [stream, setStream] = useState<string>("all");
  const [status, setStatus] = useState<ExecutionStatus>(initialStatus);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(initialItems.length === PAGE_SIZE);
  const [loadingMore, setLoadingMore] = useState(false);
  const pollTickRef = useRef<number>(0);

  const buildLogQuery = useCallback(
    (s: string, offset: number) => {
      const qs = new URLSearchParams();
      qs.set("limit", String(PAGE_SIZE));
      qs.set("offset", String(offset));
      if (s !== "all") qs.set("stream", s);
      return qs.toString();
    },
    [],
  );

  const reload = useCallback(
    async (s: string) => {
      setError(null);
      const res = await apiFetch<LogListResponse>(
        `/v0/executions/${encodeURIComponent(executionId)}/logs?${buildLogQuery(s, 0)}`,
      );
      if (res.status === 200 && res.data) {
        setItems(res.data.items);
        setHasMore(res.data.items.length === PAGE_SIZE);
      } else {
        setError(`로그 불러오기 실패 (status=${res.status})`);
      }
    },
    [executionId, buildLogQuery],
  );

  // Polling: terminal 도달 시 자동 정지.
  useEffect(() => {
    if (TERMINAL_STATUSES.has(status)) return;

    const tick = async () => {
      pollTickRef.current += 1;
      const my = pollTickRef.current;

      // status 다시 확인 — 종료됐으면 polling 중단.
      const stRes = await apiFetch<{ status: ExecutionStatus }>(
        `/v0/executions/${encodeURIComponent(executionId)}`,
      );
      if (my !== pollTickRef.current) return; // 더 새로운 tick 가 시작됐음 (예: stream 변경)
      if (stRes.status === 200 && stRes.data) {
        setStatus(stRes.data.status);
      }

      // 로그도 같이 refresh
      const logRes = await apiFetch<LogListResponse>(
        `/v0/executions/${encodeURIComponent(executionId)}/logs?${buildLogQuery(stream, 0)}`,
      );
      if (my !== pollTickRef.current) return;
      if (logRes.status === 200 && logRes.data) {
        setItems(logRes.data.items);
        setHasMore(logRes.data.items.length === PAGE_SIZE);
      }
    };

    const id = window.setInterval(tick, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [status, stream, executionId, buildLogQuery]);

  function onStreamChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const next = e.target.value;
    setStream(next);
    void reload(next);
  }

  const loadMore = useCallback(async () => {
    setLoadingMore(true);
    const res = await apiFetch<LogListResponse>(
      `/v0/executions/${encodeURIComponent(executionId)}/logs?${buildLogQuery(stream, items.length)}`,
    );
    setLoadingMore(false);
    if (res.status === 200 && res.data) {
      setItems((prev) => [...prev, ...res.data!.items]);
      setHasMore(res.data.items.length === PAGE_SIZE);
    } else {
      setError(`더 불러오기 실패 (status=${res.status})`);
    }
  }, [buildLogQuery, executionId, items.length, stream]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">스트림</label>
          <select
            value={stream}
            onChange={onStreamChange}
            className="rounded-md border border-gray-300 bg-white px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
          >
            {STREAM_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="text-xs text-gray-500">
          {TERMINAL_STATUSES.has(status)
            ? "종료된 실행 (자동 새로고침 정지)"
            : "3초마다 자동 새로고침"}
          {" · "}
          {items.length} 라인
        </div>
      </div>

      {error ? (
        <div className="text-sm rounded-md border border-red-200 bg-red-50 text-red-700 p-3">
          {error}
        </div>
      ) : null}

      <pre className="rounded-md border border-gray-200 bg-white p-4 text-xs font-mono overflow-x-auto max-h-[60vh]">
        {items.length === 0 ? (
          <span className="text-gray-400">(로그 없음)</span>
        ) : (
          items.map((e) => {
            const cls =
              STREAM_LINE_CLS[e.stream] ?? "text-gray-700";
            const stepTag = e.step_id != null ? `step ${e.step_id}` : "—";
            return (
              <div key={e.seq} className={cls}>
                <span className="text-gray-400">
                  [{e.stream}/{stepTag}]
                </span>{" "}
                {e.line}
              </div>
            );
          })
        )}
      </pre>

      {hasMore ? (
        <div className="flex justify-center">
          <button
            onClick={loadMore}
            disabled={loadingMore}
            className="text-sm text-gray-700 hover:underline disabled:text-gray-400"
          >
            {loadingMore ? "더 불러오는 중…" : "더 보기"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
