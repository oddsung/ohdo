"use client";

import { type FormEvent, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Status = "idle" | "submitting" | "sent" | "error";

type MagicLinkResponse = { email: string; expires_in: number };
type ErrorResponse = { detail?: { error?: string } | unknown };

export default function SignInPage() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState<string>("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setStatus("submitting");
    setMessage("");

    const res = await apiFetch<MagicLinkResponse | ErrorResponse>(
      "/v0/auth/magic-link",
      {
        method: "POST",
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      },
    );

    if (res.status === 202) {
      setStatus("sent");
      setMessage(
        "이메일 함을 확인하세요. (개발 환경에서는 백엔드 서버 로그의 " +
          "[MAGIC LINK] 라인의 URL 을 브라우저에 붙여넣기)",
      );
    } else if (res.status === 422) {
      setStatus("error");
      setMessage("올바른 이메일 형식이 아닙니다.");
    } else {
      setStatus("error");
      setMessage(`요청 실패 (status=${res.status}).`);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">ohdo.ai</h1>
          <p className="text-sm text-gray-500">
            이메일로 로그인. 비밀번호 없이 링크 클릭 한 번.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <label className="block space-y-1">
            <span className="text-sm font-medium text-gray-700">이메일</span>
            <Input
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={status === "submitting" || status === "sent"}
            />
          </label>

          <Button
            type="submit"
            className="w-full"
            disabled={
              status === "submitting" ||
              status === "sent" ||
              email.trim().length === 0
            }
          >
            {status === "submitting"
              ? "발송 중…"
              : status === "sent"
                ? "발송 완료"
                : "로그인 링크 받기"}
          </Button>
        </form>

        {message ? (
          <div
            className={
              "text-sm rounded-md border p-3 " +
              (status === "error"
                ? "border-red-200 bg-red-50 text-red-700"
                : "border-gray-200 bg-white text-gray-700")
            }
          >
            {message}
          </div>
        ) : null}
      </div>
    </main>
  );
}
