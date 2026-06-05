// a11y 회귀 테스트 — 영속 UI(대화상자 제외)의 보이는 버튼은 모두 접근 가능한 이름을 가져야 한다.
//
// 현재 ChatPanel 의 전송 버튼은 아이콘 전용(SendHorizonal)이며 aria-label/title/텍스트가
// 전혀 없어 접근 이름이 없다 → 스크린리더·자동화가 식별 불가. 이 테스트가 그 결함을 잡는다.
// (i18n 텍스트에 의존하지 않도록 "이름 없는 버튼" 을 열거하는 방식으로 검증한다.)

import { test, expect } from "./fixtures";

test("영속 UI의 보이는 버튼은 모두 접근 가능한 이름을 가진다", async ({ window }) => {
  // 세션을 만들어 ChatPanel(전송 버튼 포함)을 렌더한다.
  // Ctrl+N 은 입력창 포커스가 아닐 때만 동작 → 먼저 빈 메인 영역을 클릭해 포커스를 비운다.
  await window.mouse.click(640, 400);
  await window.keyboard.press("Control+n");

  // ChatPanel 입력창(textarea)이 DOM 에 붙을 때까지 대기.
  await expect(window.locator("textarea").first()).toBeAttached({ timeout: 20_000 });
  await window.waitForTimeout(600);

  const offenders = await window.evaluate(() => {
    const bad: string[] = [];
    for (const b of Array.from(document.querySelectorAll("button"))) {
      const el = b as HTMLElement;
      if (el.closest('[role="dialog"]')) continue; // 온보딩/팔레트 등 대화상자 제외
      if (el.getClientRects().length === 0) continue; // 렌더 안 됨 제외
      const cs = getComputedStyle(el);
      if (cs.visibility === "hidden" || cs.display === "none") continue;
      const name = (
        el.getAttribute("aria-label") ||
        el.getAttribute("title") ||
        (el.getAttribute("aria-labelledby") ? "ref" : "") ||
        el.textContent ||
        ""
      ).trim();
      if (!name) bad.push(el.outerHTML.replace(/\s+/g, " ").slice(0, 140));
    }
    return bad;
  });

  expect(offenders, `접근 이름(aria-label/title/text)이 없는 버튼: ${offenders.join("  ||  ")}`).toEqual(
    [],
  );
});
