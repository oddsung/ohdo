// 클라이언트·서버 공용 fetch 래퍼. 브라우저가 Next.js (:3000) 에 요청하면
// rewrite proxy 를 통해 백엔드 (:8000) 로 전달된다. 쿠키는 same-origin 으로
// 자동 첨부되므로 credentials: "include" 이상의 고민 불필요.

export type ApiResult<T> = {
  status: number;
  data: T | undefined;
  ok: boolean;
};

export async function apiFetch<T = unknown>(
  path: string,
  init?: RequestInit,
): Promise<ApiResult<T>> {
  const res = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  let data: T | undefined;
  if (res.status !== 204) {
    try {
      data = (await res.json()) as T;
    } catch {
      data = undefined;
    }
  }

  return { status: res.status, data, ok: res.ok };
}
