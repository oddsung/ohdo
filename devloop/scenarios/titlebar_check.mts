// §78 타이틀바 UI 스모크 — 기동 → 타이틀바 스크린샷 → 햄버거 메뉴 → 세션 생성(탭) → 라이트 테마.
// 실행: cd devloop && npx tsx scenarios/titlebar_check.mts (SHOT_DIR env 로 저장 위치 지정)
import { join } from "path";
import { _electron as electron, type ElectronApplication, type Page } from "playwright";
import {
  DESKTOP_MAIN_ENTRY,
  DESKTOP_V3_DIR,
  DEVLOOP_DIR,
  REPO_ROOT,
  VENV_PYTHON,
  cleanElectronEnv,
  electronBinary,
} from "../src/paths";

const OUT = process.env.SHOT_DIR || join(DEVLOOP_DIR, "runs", "titlebar");

function log(m: string): void {
  process.stdout.write(`${m}\n`);
}

async function main(): Promise<number> {
  const app: ElectronApplication = await electron.launch({
    executablePath: electronBinary(),
    args: [DESKTOP_MAIN_ENTRY],
    cwd: DESKTOP_V3_DIR,
    env: cleanElectronEnv({ OHDO_PYTHON: VENV_PYTHON, OHDO_PROJECT_ROOT: REPO_ROOT }),
  });
  const win: Page = await app.firstWindow();
  await win.waitForLoadState("domcontentloaded");
  await win.locator("#root").waitFor({ state: "attached", timeout: 20_000 });
  await new Promise((r) => setTimeout(r, 2500));

  await win.screenshot({ path: join(OUT, "tb1_initial.png") });
  log("shot tb1_initial");

  // 햄버거 메뉴 열기.
  await win.getByRole("button", { name: /메뉴|Menu/ }).first().click();
  await new Promise((r) => setTimeout(r, 400));
  await win.screenshot({ path: join(OUT, "tb2_menu.png") });
  log("shot tb2_menu");
  await win.keyboard.press("Escape");

  // 세션 생성 → 타이틀바 탭 확인.
  const cta = win.getByTestId("empty-create-session");
  if (await cta.count()) await cta.click();
  await new Promise((r) => setTimeout(r, 1500));
  await win.screenshot({ path: join(OUT, "tb3_session_tab.png") });
  log("shot tb3_session_tab");

  // 라이트 테마 전환 (우측 유틸 토글) — WCO 오버레이 동기화 확인용.
  await win.getByRole("button", { name: /라이트 테마로|Switch to light/ }).first().click();
  await new Promise((r) => setTimeout(r, 700));
  await win.screenshot({ path: join(OUT, "tb4_light.png") });
  log("shot tb4_light");

  await app.close();
  return 0;
}

main().then(
  (c) => process.exit(c),
  (e) => {
    log(`EXCEPTION: ${(e as Error).stack ?? e}`);
    process.exit(1);
  },
);
