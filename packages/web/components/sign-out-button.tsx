"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function SignOutButton() {
  const [loading, setLoading] = useState(false);

  async function handleClick() {
    setLoading(true);
    try {
      await apiFetch("/v0/auth/logout", { method: "POST" });
    } finally {
      // /sign-in 으로 하드 네비게이션. 서버 컴포넌트가 getCurrentUser null 을 보고
      // 루트에서 /sign-in 으로 redirect 한다.
      window.location.assign("/sign-in");
    }
  }

  return (
    <Button variant="secondary" onClick={handleClick} disabled={loading}>
      {loading ? "로그아웃 중…" : "로그아웃"}
    </Button>
  );
}
