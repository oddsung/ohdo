// SPDX-License-Identifier: AGPL-3.0-or-later
// Python 브리지 HTTP 클라이언트. main 프로세스가 보유한 {baseUrl, token} 를
// preload(window.ohdo) 를 통해 받아 Authorization 헤더를 붙인다.
import i18n from "@/i18n";

export interface SessionSummary {
  session_id: string;
  title: string;
  description: string;
  project_type: string;
  created_at: string;
  updated_at: string;
  total_steps: number;
  completed_steps: number;
}

// core/session_manager.py 의 Step dataclass (asdict) 미러 — Phase B 에서 쓰는 필드만.
export interface Step {
  step_id: number;
  status: string; // "pending" | "completed" | "failed"
  user_request: string;
  ai_description: string;
  generated_code: string;
  step_code: string;
  required_packages: string[];
  validation_warnings: { kind: string; message: string; line: number }[];
}

export interface SessionDetail {
  session_id: string;
  title: string;
  description: string;
  project_type: string;
  created_at: string;
  updated_at: string;
  steps: Step[];
  settings?: Record<string, unknown>;
  workflow_metadata?: Record<string, unknown>;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  auth_required: boolean;
}

export interface GenerateResult {
  success: boolean;
  step?: Step;
  session?: SessionDetail;
  description?: string;
  error?: string;
  partial?: boolean;
}

async function apiInfo(): Promise<{ baseUrl: string; token: string }> {
  const info = await window.ohdo.getApiInfo();
  if (!info) throw new Error(i18n.t("bridge.disconnected"));
  return info;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const { baseUrl, token } = await apiInfo();
  const res = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.json())?.detail ?? "";
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${path} → HTTP ${res.status}${detail ? `: ${detail}` : ""}`);
  }
  return res.json() as Promise<T>;
}

export function fetchHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

export async function fetchSessions(): Promise<SessionSummary[]> {
  const data = await apiFetch<{ sessions: SessionSummary[]; count: number }>("/sessions");
  return data.sessions;
}

export async function fetchSession(sessionId: string): Promise<SessionDetail> {
  const data = await apiFetch<{ session: SessionDetail }>(`/sessions/${sessionId}`);
  return data.session;
}

export async function createSession(
  title: string,
  projectType = "desktop",
): Promise<SessionDetail> {
  const data = await apiFetch<{ session: SessionDetail }>("/sessions", {
    method: "POST",
    body: JSON.stringify({ title, project_type: projectType }),
  });
  return data.session;
}

export interface PickResult {
  success: boolean;
  x: number;
  y: number;
  element?: Record<string, unknown>;
  label?: string;
  is_browser_element?: boolean;
  error?: string;
}

export interface PendingElement {
  label: string;
  isBrowser: boolean;
}

export function generateStep(
  sessionId: string,
  userRequest: string,
  pending?: PendingElement | null,
): Promise<GenerateResult> {
  return apiFetch<GenerateResult>(`/sessions/${sessionId}/generate`, {
    method: "POST",
    body: JSON.stringify({
      user_request: userRequest,
      element_context: pending?.label ?? null,
      is_browser_element: pending?.isBrowser ?? false,
    }),
  });
}

/** 현재 커서 위치의 element 캡처 (카운트다운 후 호출). */
export function pickElement(): Promise<PickResult> {
  return apiFetch<PickResult>("/pick", { method: "POST" });
}

export async function updateStepCode(
  sessionId: string,
  stepId: number,
  generatedCode: string,
): Promise<SessionDetail> {
  const data = await apiFetch<{ success: boolean; session: SessionDetail }>(
    `/sessions/${sessionId}/steps/${stepId}`,
    { method: "PUT", body: JSON.stringify({ generated_code: generatedCode }) },
  );
  return data.session;
}

// ── 작업 녹화 (recording) — handoff §41 #3 ──────────────

export interface RecordingStatus {
  is_recording: boolean;
  event_count: number;
}

export function recordingStart(sessionId: string): Promise<{ recording_session_id: string }> {
  return apiFetch(`/sessions/${sessionId}/recording/start`, { method: "POST" });
}

export function recordingStatus(): Promise<RecordingStatus> {
  return apiFetch<RecordingStatus>("/recording/status");
}

export function recordingMarker(): Promise<{ success: boolean }> {
  return apiFetch("/recording/marker", { method: "POST" });
}

export function recordingStopCommit(
  sessionId: string,
): Promise<{ step_count: number; session: SessionDetail }> {
  return apiFetch(`/sessions/${sessionId}/recording/stop_commit`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function recordingCancel(): Promise<{ success: boolean; was_recording: boolean }> {
  return apiFetch("/recording/cancel", { method: "POST" });
}
