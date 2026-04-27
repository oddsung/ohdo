"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { TERMINAL_STATUSES, type ExecutionStatus } from "@/lib/format";
import { Button } from "@/components/ui/button";

type Props = {
  executionId: string;
  initialStatus: ExecutionStatus;
};

export function CancelButton({ executionId, initialStatus }: Props) {
  const router = useRouter();
  const [hidden, setHidden] = useState<boolean>(
    TERMINAL_STATUSES.has(initialStatus),
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (hidden) return null;

  async function handleClick() {
    if (!window.confirm("정말 이 실행을 취소하시겠습니까?")) return;
    setLoading(true);
    setError(null);

    const res = await apiFetch<unknown>(
      `/v0/executions/${encodeURIComponent(executionId)}/cancel`,
      { method: "POST" },
    );
    setLoading(false);

    if (res.status === 202) {
      // 낙관적: 버튼 숨김 + 1.5초 뒤 server 재 fetch (헤더 status badge 갱신)
      setHidden(true);
      setTimeout(() => router.refresh(), 1500);
      return;
    }

    const detail = (res.data as { detail?: { error?: string } } | undefined)?.detail;
    const errCode = detail?.error;

    if (res.status === 409) {
      setError("이미 종료된 실행입니다.");
      setHidden(true);
      setTimeout(() => router.refresh(), 800);
    } else if (res.status === 503) {
      setError("에이전트 오프라인 — 잠시 후 다시 시도하세요.");
    } else if (res.status === 404) {
      setError("실행을 찾을 수 없습니다.");
    } else if (res.status === 401) {
      setError("로그인이 만료되었습니다. 새로고침 후 다시 로그인하세요.");
    } else {
      setError(`취소 실패 (status=${res.status}${errCode ? `, ${errCode}` : ""})`);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button variant="secondary" onClick={handleClick} disabled={loading}>
        {loading ? "취소 중…" : "취소"}
      </Button>
      {error ? (
        <span className="text-xs text-red-700 max-w-xs text-right">{error}</span>
      ) : null}
    </div>
  );
}
