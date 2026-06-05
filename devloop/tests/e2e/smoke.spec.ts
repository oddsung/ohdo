// desktop_v3 스모크 E2E — 앱이 기동되고 렌더러가 마운트되는지 검증한다.
// 자율 루프의 최초 안전망: 이게 깨지면 다른 검증은 의미 없다.

import { test, expect } from "./fixtures";

test("앱이 기동되고 메인 윈도우 렌더러가 마운트된다", async ({ electronApp, window }) => {
  expect(electronApp).toBeTruthy();

  // 타이틀(index.html: <title>ohdo</title>).
  const title = await window.title();
  expect(title).toContain("ohdo");

  // React 마운트 지점(#root)이 붙고 내용이 채워진다.
  await expect(window.locator("#root")).toBeAttached({ timeout: 20_000 });
  await expect(window.locator("#root")).not.toBeEmpty({ timeout: 20_000 });
});

test("렌더러가 백엔드 브리지 API 정보를 받는다", async ({ window }) => {
  // preload 가 노출한 window.ohdo.getApiInfo() 로 브리지 핸드셰이크 확인.
  // 브리지 기동 실패 시 null → 이 테스트가 회귀를 잡는다.
  const apiInfo = await window.evaluate(async () => {
    const w = window as unknown as {
      ohdo?: { getApiInfo?: () => Promise<{ baseUrl: string; token: string } | null> };
    };
    if (!w.ohdo?.getApiInfo) return { available: false, info: null };
    const info = await w.ohdo.getApiInfo();
    return { available: true, info };
  });

  expect(apiInfo.available).toBe(true);
  expect(apiInfo.info).not.toBeNull();
  expect(apiInfo.info?.baseUrl).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);
});
