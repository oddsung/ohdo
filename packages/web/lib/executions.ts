// Server-side fetch helpers for executions / logs / captures.
// 클라이언트 컴포넌트는 lib/api.ts 의 apiFetch 를 직접 사용한다 (rewrites 가
// 같은 origin 으로 만들어줘 쿠키 자동 첨부).

import { cookies } from "next/headers";
import type { ExecutionStatus } from "./format";

const backend = process.env.API_BASE_URL ?? "http://localhost:8000";
const SESSION_COOKIE = "ohdo_session";

export type Execution = {
  execution_id: string;
  status: ExecutionStatus;
  agent_id: string;
  user_id: string;
  from_step: number | null;
  to_step: number | null;
  total_steps: number | null;
  executed_steps: number | null;
  successful_steps: number | null;
  failed_steps: number | null;
  total_time_ms: number | null;
  error_summary: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ExecutionListResponse = { items: Execution[] };

export type LogEntry = {
  seq: number;
  stream: "stdout" | "stderr" | "engine";
  step_id: number | null;
  line: string;
  created_at: string;
};
export type LogListResponse = { items: LogEntry[] };

export type Capture = {
  capture_id: string;
  execution_id: string;
  step_id: number | null;
  kind: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};
export type CaptureListResponse = { items: Capture[] };

async function serverFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const store = await cookies();
  const session = store.get(SESSION_COOKIE);
  const headers: Record<string, string> = {
    ...((init?.headers as Record<string, string>) ?? {}),
  };
  if (session?.value) {
    headers.cookie = `${SESSION_COOKIE}=${session.value}`;
  }
  return fetch(`${backend}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
}

export async function listExecutionsServer(params: {
  limit?: number;
  offset?: number;
  status?: ExecutionStatus | "all";
}): Promise<ExecutionListResponse | null> {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));
  if (params.status && params.status !== "all") qs.set("status", params.status);
  const q = qs.toString();
  const path = "/v0/executions" + (q ? `?${q}` : "");
  const res = await serverFetch(path);
  if (!res.ok) return null;
  return (await res.json()) as ExecutionListResponse;
}

export async function getExecutionServer(
  executionId: string,
): Promise<Execution | null> {
  const res = await serverFetch(
    `/v0/executions/${encodeURIComponent(executionId)}`,
  );
  if (!res.ok) return null;
  return (await res.json()) as Execution;
}

export async function listLogsServer(
  executionId: string,
  params: { stream?: string; step_id?: number; limit?: number; offset?: number } = {},
): Promise<LogListResponse | null> {
  const qs = new URLSearchParams();
  if (params.stream) qs.set("stream", params.stream);
  if (params.step_id != null) qs.set("step_id", String(params.step_id));
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));
  const q = qs.toString();
  const path = `/v0/executions/${encodeURIComponent(executionId)}/logs${q ? `?${q}` : ""}`;
  const res = await serverFetch(path);
  if (!res.ok) return null;
  return (await res.json()) as LogListResponse;
}

export async function listCapturesServer(
  executionId: string,
): Promise<CaptureListResponse | null> {
  const res = await serverFetch(
    `/v0/executions/${encodeURIComponent(executionId)}/captures`,
  );
  if (!res.ok) return null;
  return (await res.json()) as CaptureListResponse;
}
