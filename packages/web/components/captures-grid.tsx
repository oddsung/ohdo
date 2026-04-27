"use client";

import { useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import type { Capture, CaptureListResponse } from "@/lib/executions";
import { TERMINAL_STATUSES, type ExecutionStatus } from "@/lib/format";

const POLL_INTERVAL_MS = 3000;

type Props = {
  executionId: string;
  initialStatus: ExecutionStatus;
  initialItems: Capture[];
};

export function CapturesGrid({
  executionId,
  initialStatus,
  initialItems,
}: Props) {
  const [items, setItems] = useState<Capture[]>(initialItems);
  const [status, setStatus] = useState<ExecutionStatus>(initialStatus);
  const tickRef = useRef(0);

  useEffect(() => {
    if (TERMINAL_STATUSES.has(status)) return;

    const id = window.setInterval(async () => {
      tickRef.current += 1;
      const my = tickRef.current;

      const stRes = await apiFetch<{ status: ExecutionStatus }>(
        `/v0/executions/${encodeURIComponent(executionId)}`,
      );
      if (my !== tickRef.current) return;
      if (stRes.status === 200 && stRes.data) {
        setStatus(stRes.data.status);
      }

      const cRes = await apiFetch<CaptureListResponse>(
        `/v0/executions/${encodeURIComponent(executionId)}/captures`,
      );
      if (my !== tickRef.current) return;
      if (cRes.status === 200 && cRes.data) {
        setItems(cRes.data.items);
      }
    }, POLL_INTERVAL_MS);

    return () => window.clearInterval(id);
  }, [status, executionId]);

  if (items.length === 0) {
    return <p className="text-sm text-gray-500">캡처 없음</p>;
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {items.map((c) => (
        <CaptureCard key={c.capture_id} capture={c} />
      ))}
    </div>
  );
}

function CaptureCard({ capture }: { capture: Capture }) {
  const [missing, setMissing] = useState(false);
  const url = `/v0/captures/${encodeURIComponent(capture.capture_id)}`;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="block rounded-md border border-gray-200 bg-white overflow-hidden hover:border-gray-400 transition-colors"
    >
      <div className="aspect-[16/10] bg-gray-100 flex items-center justify-center">
        {missing ? (
          <span className="text-xs text-gray-400">이미지 사라짐 (410)</span>
        ) : (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={url}
            alt={`step ${capture.step_id ?? ""} 캡처`}
            onError={() => setMissing(true)}
            className="w-full h-full object-contain"
          />
        )}
      </div>
      <div className="px-3 py-2 flex items-center justify-between text-xs text-gray-600">
        <span>
          step <span className="text-gray-900">{capture.step_id ?? "—"}</span>
        </span>
        <span>{(capture.size_bytes / 1024).toFixed(1)} KB</span>
      </div>
    </a>
  );
}
