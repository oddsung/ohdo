import { defineConfig } from "@playwright/test";

// devloop E2E 설정 — desktop_v3(Electron) 단일 인스턴스를 띄워 검증한다.
// Electron 앱은 동시 실행이 불가하므로 workers=1, fullyParallel=false.
// JSON 리포트를 runs/last-playwright.json 에 떨궈 orchestrator 가 파싱한다.
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  reporter: [
    ["list"],
    ["json", { outputFile: "runs/last-playwright.json" }],
  ],
});
