"use client";

import Link from "next/link";
import { useCallback, useState, useTransition } from "react";
import { apiFetch } from "@/lib/api";
import {
  type ExecutionStatus,
  formatDateTime,
  formatDuration,
  shortenExecId,
} from "@/lib/format";
import type { Execution, ExecutionListResponse } from "@/lib/executions";
import { Button } from "@/components/ui/button";
import { ExecutionStatusBadge } from "@/components/execution-status-badge";

const PAGE_SIZE = 20;
const STATUS_OPTIONS: { value: ExecutionStatus | "all"; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "queued", label: "대기" },
  { value: "accepted", label: "수락" },
  { value: "running", label: "실행 중" },
  { value: "completed", label: "완료" },
  { value: "failed", label: "실패" },
  { value: "cancelled", label: "취소" },
];

export function ExecutionsList({
  initialItems,
}: {
  initialItems: Execution[];
}) {
  const [items, setItems] = useState<Execution[]>(initialItems);
  const [statusFilter, setStatusFilter] = useState<ExecutionStatus | "all">(
    "all",
  );
  const [hasMore, setHasMore] = useState(initialItems.length === PAGE_SIZE);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [loadingMore, setLoadingMore] = useState(false);

  const buildQuery = useCallback(
    (
      filter: ExecutionStatus | "all",
      offset: number,
    ): string => {
      const qs = new URLSearchParams();
      qs.set("limit", String(PAGE_SIZE));
      qs.set("offset", String(offset));
      if (filter !== "all") qs.set("status", filter);
      return qs.toString();
    },
    [],
  );

  const reload = useCallback(
    (filter: ExecutionStatus | "all") => {
      setError(null);
      startTransition(async () => {
        const res = await apiFetch<ExecutionListResponse>(
          `/v0/executions?${buildQuery(filter, 0)}`,
        );
        if (res.status === 200 && res.data) {
          setItems(res.data.items);
          setHasMore(res.data.items.length === PAGE_SIZE);
        } else {
          setError(`불러오기 실패 (status=${res.status})`);
        }
      });
    },
    [buildQuery],
  );

  const loadMore = useCallback(async () => {
    setLoadingMore(true);
    setError(null);
    const res = await apiFetch<ExecutionListResponse>(
      `/v0/executions?${buildQuery(statusFilter, items.length)}`,
    );
    setLoadingMore(false);
    if (res.status === 200 && res.data) {
      setItems((prev) => [...prev, ...res.data!.items]);
      setHasMore(res.data.items.length === PAGE_SIZE);
    } else {
      setError(`더 불러오기 실패 (status=${res.status})`);
    }
  }, [buildQuery, items.length, statusFilter]);

  function onFilterChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const next = e.target.value as ExecutionStatus | "all";
    setStatusFilter(next);
    reload(next);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">상태</label>
          <select
            value={statusFilter}
            onChange={onFilterChange}
            disabled={pending}
            className="rounded-md border border-gray-300 bg-white px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <Button
          variant="ghost"
          onClick={() => reload(statusFilter)}
          disabled={pending}
        >
          {pending ? "새로고침 중…" : "새로고침"}
        </Button>
      </div>

      {error ? (
        <div className="text-sm rounded-md border border-red-200 bg-red-50 text-red-700 p-3">
          {error}
        </div>
      ) : null}

      {items.length === 0 ? (
        <div className="text-sm text-gray-500 rounded-md border border-gray-200 bg-white p-8 text-center">
          실행 기록이 없습니다.
        </div>
      ) : (
        <div className="rounded-md border border-gray-200 bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2 font-medium">상태</th>
                <th className="px-4 py-2 font-medium">execution_id</th>
                <th className="px-4 py-2 font-medium">스텝</th>
                <th className="px-4 py-2 font-medium">소요 시간</th>
                <th className="px-4 py-2 font-medium">생성 시각</th>
                <th className="px-4 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map((it) => (
                <tr key={it.execution_id} className="hover:bg-gray-50">
                  <td className="px-4 py-2">
                    <ExecutionStatusBadge status={it.status} />
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-gray-700">
                    {shortenExecId(it.execution_id)}
                  </td>
                  <td className="px-4 py-2 text-gray-700">
                    {it.successful_steps ?? "—"}/{it.executed_steps ?? "—"}
                    <span className="text-gray-400 text-xs ml-1">
                      / {it.total_steps ?? "—"}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-700">
                    {formatDuration(it.total_time_ms)}
                  </td>
                  <td className="px-4 py-2 text-gray-600 whitespace-nowrap">
                    {formatDateTime(it.created_at)}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Link
                      href={`/executions/${it.execution_id}`}
                      className="text-sm text-gray-900 hover:underline"
                    >
                      상세 →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {hasMore ? (
        <div className="flex justify-center">
          <Button
            variant="secondary"
            onClick={loadMore}
            disabled={loadingMore || pending}
          >
            {loadingMore ? "더 불러오는 중…" : "더 보기"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
