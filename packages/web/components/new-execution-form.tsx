"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type StepDraft = { code: string };
type ApiError = { detail?: { error?: string } | unknown };

const PLACEHOLDER_STEP = "import time\nprint('hello from web form')\ntime.sleep(2)";

export function NewExecutionForm() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState("");
  const [requirementsText, setRequirementsText] = useState("");
  const [steps, setSteps] = useState<StepDraft[]>([{ code: "" }]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function addStep() {
    setSteps((prev) => [...prev, { code: "" }]);
  }

  function removeStep(idx: number) {
    setSteps((prev) => prev.filter((_, i) => i !== idx));
  }

  function updateStepCode(idx: number, code: string) {
    setSteps((prev) =>
      prev.map((s, i) => (i === idx ? { ...s, code } : s)),
    );
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    const stepsClean = steps
      .map((s, i) => ({
        step_id: i + 1,
        generated_code: s.code,
      }))
      .filter((s) => s.generated_code.trim().length > 0);

    if (stepsClean.length === 0) {
      setError("최소 한 개의 비어있지 않은 스텝이 필요합니다.");
      setSubmitting(false);
      return;
    }

    const requirements = requirementsText
      .split("\n")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    const snapshot: Record<string, unknown> = {
      session_id: sessionId.trim() || `web-${Date.now()}`,
      steps: stepsClean,
    };
    if (requirements.length > 0) snapshot.requirements = requirements;

    const res = await apiFetch<{ execution_id?: string } & ApiError>(
      "/v0/executions",
      {
        method: "POST",
        body: JSON.stringify({ session_snapshot: snapshot }),
      },
    );
    setSubmitting(false);

    if (res.status === 201 && res.data?.execution_id) {
      router.push(`/executions/${res.data.execution_id}`);
      return;
    }

    const detail = res.data?.detail as { error?: string } | undefined;
    const errCode = detail?.error;

    if (res.status === 400 && errCode === "no_agent_available") {
      setError(
        "등록된 agent 가 없습니다. 먼저 데스크톱 agent 를 설치하고 Sign In 하세요.",
      );
    } else if (res.status === 422) {
      setError("입력 형식 오류입니다. (스텝 코드, requirements 형식을 확인하세요)");
    } else if (res.status === 401) {
      setError("로그인이 만료되었습니다. 새로고침 후 다시 로그인하세요.");
    } else {
      setError(
        `제출 실패 (status=${res.status}${errCode ? `, ${errCode}` : ""})`,
      );
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="space-y-2">
        <label htmlFor="session_id" className="block text-sm font-medium text-gray-700">
          session_id <span className="text-gray-400">(선택)</span>
        </label>
        <Input
          id="session_id"
          type="text"
          placeholder="비우면 자동: web-{timestamp}"
          value={sessionId}
          onChange={(e) => setSessionId(e.target.value)}
          disabled={submitting}
        />
      </div>

      <div className="space-y-2">
        <label
          htmlFor="requirements"
          className="block text-sm font-medium text-gray-700"
        >
          requirements <span className="text-gray-400">(선택, 한 줄에 하나)</span>
        </label>
        <textarea
          id="requirements"
          placeholder={"requests\nbeautifulsoup4>=4"}
          value={requirementsText}
          onChange={(e) => setRequirementsText(e.target.value)}
          disabled={submitting}
          rows={3}
          className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-mono text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-900 focus:border-transparent"
        />
        <p className="text-xs text-gray-500">
          번들된 패키지 (pywinauto / pyautogui / selenium / mss) 외에 필요한 것만 추가.
        </p>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-gray-700">steps</span>
          <Button
            type="button"
            variant="ghost"
            onClick={addStep}
            disabled={submitting}
          >
            + 스텝 추가
          </Button>
        </div>

        {steps.map((step, idx) => (
          <div
            key={idx}
            className="rounded-md border border-gray-200 bg-white p-3 space-y-2"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-gray-500">
                스텝 {idx + 1}
              </span>
              {steps.length > 1 ? (
                <button
                  type="button"
                  onClick={() => removeStep(idx)}
                  disabled={submitting}
                  className="text-xs text-gray-500 hover:text-red-600 disabled:text-gray-300"
                >
                  제거
                </button>
              ) : null}
            </div>
            <textarea
              value={step.code}
              onChange={(e) => updateStepCode(idx, e.target.value)}
              disabled={submitting}
              rows={6}
              placeholder={idx === 0 ? PLACEHOLDER_STEP : ""}
              className="block w-full rounded-md border border-gray-300 bg-gray-50 px-3 py-2 text-xs font-mono text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-900 focus:border-transparent"
            />
          </div>
        ))}
      </div>

      {error ? (
        <div className="text-sm rounded-md border border-red-200 bg-red-50 text-red-700 p-3">
          {error}
        </div>
      ) : null}

      <div className="flex items-center justify-end gap-2">
        <Button type="submit" disabled={submitting}>
          {submitting ? "제출 중…" : "실행 생성"}
        </Button>
      </div>
    </form>
  );
}
