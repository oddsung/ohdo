// 서버 컴포넌트에서 사용할 auth helper.
// 쿠키를 직접 읽어 백엔드 /v0/users/me 를 호출한다. 클라이언트 컴포넌트는
// lib/api.ts 의 apiFetch 를 사용.

import { cookies } from "next/headers";

const SESSION_COOKIE = "ohdo_session";
const backend = process.env.API_BASE_URL ?? "http://localhost:8000";

export type CurrentUser = {
  id: string;
  email: string;
  created_at: string;
};

export async function getCurrentUser(): Promise<CurrentUser | null> {
  const store = await cookies();
  const session = store.get(SESSION_COOKIE);
  if (!session?.value) return null;

  let res: Response;
  try {
    res = await fetch(`${backend}/v0/users/me`, {
      method: "GET",
      headers: {
        cookie: `${SESSION_COOKIE}=${session.value}`,
      },
      cache: "no-store",
    });
  } catch {
    // 백엔드가 다운됐을 수도. 일단 로그인 안 된 것으로 취급.
    return null;
  }

  if (!res.ok) return null;
  return (await res.json()) as CurrentUser;
}
