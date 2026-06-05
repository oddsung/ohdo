// 빈 상태(세션 미선택) 행동 유도 E2E — EmptyState 가 단순 안내문이 아니라
// 곧장 세션을 만들 수 있는 1차 행동(CTA 버튼)을 제공하는지 검증한다.
//
// EmptyState 는 selectedSessionId 가 없을 때 표시된다(App.tsx). 이전엔 안내 텍스트만 있어
// 사용자가 사이드바의 작은 "+" 를 찾아야 했다 — 이 개선으로 본문에 "새 세션 만들기" 버튼이 생겼다.
//
// 결정적 진입: 첫 실행 온보딩이 자동으로 뜨면 본문을 가리므로, onboarded 플래그를 세우고
// 리로드해 온보딩 자동표시를 억제한다. uiStore 는 비영속이라 리로드 시 세션 선택이 해제되어
// EmptyState 로 진입한다. (CTA 는 data-testid 로 식별 — i18n 텍스트에 의존하지 않는다.)

import { test, expect } from "./fixtures";

test("빈 상태에서 '새 세션 만들기' CTA 로 세션을 생성할 수 있다", async ({ window }) => {
  await expect(window.locator("#root")).not.toBeEmpty({ timeout: 20_000 });

  // 온보딩 자동표시 억제 + 선택 해제 상태로 결정적 진입.
  await window.evaluate(() => localStorage.setItem("ohdo.onboarded", "1"));
  await window.reload();
  await window.waitForLoadState("domcontentloaded");
  await expect(window.locator("#root")).not.toBeEmpty({ timeout: 20_000 });

  // EmptyState 의 CTA 가 보인다. 세션 미선택이라 ChatPanel 입력창(textarea)은 아직 없다.
  const cta = window.getByTestId("empty-create-session");
  await expect(cta).toBeVisible({ timeout: 20_000 });
  await expect(cta).toBeEnabled();
  expect(await window.locator("textarea").count()).toBe(0);

  // CTA 클릭 → 세션 생성·선택 → ChatPanel(입력창) 등장 + EmptyState(CTA) 사라짐.
  await cta.click();
  await expect(window.locator("textarea").first()).toBeVisible({ timeout: 20_000 });
  await expect(window.getByTestId("empty-create-session")).toHaveCount(0);
});
