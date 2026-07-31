// §79 실행 FX 스모크 — 기동 → runFxStart(+진행) → 커서 링 → 실제 클릭(자기 타이틀바) 리플
// → /fx/clicks 캡처 확인 → 종료 플래시. 스크린샷은 SHOT_DIR 에 저장.
// 실행: cd devloop && npx tsx scenarios/runfx_check.mts
import { spawnSync } from "child_process";
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

const HELPER = join(DEVLOOP_DIR, "scenarios", "multimon_target.py");
const OUT = process.env.SHOT_DIR || join(DEVLOOP_DIR, "runs", "runfx");

function log(m: string): void {
  process.stdout.write(`${m}\n`);
}
function helper(...args: string[]): string {
  const p = spawnSync(VENV_PYTHON, [HELPER, ...args], {
    encoding: "utf8",
    env: { ...process.env, PYTHONIOENCODING: "utf-8", MULTIMON_SHOT_DIR: OUT },
  });
  return ((p.stdout || "") + (p.stderr || "")).trim();
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

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
  await sleep(2000);

  const info = (await win.evaluate(async () => {
    const w = window as unknown as {
      ohdo?: { getApiInfo?: () => Promise<{ baseUrl: string; token: string } | null> };
    };
    return (await w.ohdo?.getApiInfo?.()) ?? null;
  })) as { baseUrl: string; token: string } | null;
  if (!info) {
    log("FAIL: 브리지 미연결");
    await app.close();
    return 1;
  }

  // FX 시작 + 진행 라벨.
  await win.evaluate(async () => {
    const w = window as unknown as { ohdo: Record<string, (...a: unknown[]) => Promise<void>> };
    await w.ohdo.runFxStart();
    await w.ohdo.runFxProgress({
      current: 1,
      total: 3,
      label: "ohdo 자동화 실행 중 · 1/3 완료",
    });
  });
  log("runFx 시작");
  await sleep(1200);

  // 메인 창 타이틀바 중앙(빈 드래그 영역) — 안전한 클릭 지점. DIP→물리 변환은 Electron 에게.
  const pt = (await app.evaluate(({ BrowserWindow, screen }) => {
    const w = BrowserWindow.getAllWindows().find((x) => !x.isDestroyed() && x.isVisible());
    if (!w) return null;
    const b = w.getBounds();
    return screen.dipToScreenPoint({ x: b.x + Math.round(b.width * 0.55), y: b.y + 18 });
  })) as { x: number; y: number } | null;
  if (!pt) {
    log("FAIL: 창 좌표 획득 실패");
    await app.close();
    return 1;
  }

  log(`hover → (${pt.x}, ${pt.y})`);
  log(helper("hover", String(pt.x), String(pt.y)));
  await sleep(700);
  for (const line of helper("shot", "fx_running").split("\n")) log(`  ${line}`);

  // 실제 클릭 → LL 관찰 훅 캡처 + 리플. 직후 스크린샷으로 리플 포착.
  log(helper("click", String(pt.x), String(pt.y)));
  await sleep(250);
  for (const line of helper("shot", "fx_click").split("\n")) log(`  ${line}`);

  // 브리지가 클릭을 기록했는지 확인.
  const clicks = (await fetch(`${info.baseUrl}/fx/clicks?since=0`, {
    headers: { Authorization: `Bearer ${info.token}` },
  }).then((r) => r.json())) as { seq: number; clicks: unknown[]; active: boolean };
  log(`/fx/clicks: active=${clicks.active} count=${clicks.clicks.length}`);

  // 종료 플래시(성공).
  await win.evaluate(async () => {
    const w = window as unknown as { ohdo: Record<string, (...a: unknown[]) => Promise<void>> };
    await w.ohdo.runFxStop({ success: true });
  });
  await sleep(350);
  for (const line of helper("shot", "fx_done").split("\n")) log(`  ${line}`);
  await sleep(900);

  const ok = clicks.clicks.length >= 1;
  log(`VERDICT: ${ok ? "OK" : "FAIL"} — 클릭 관찰 ${clicks.clicks.length}건`);
  await app.close();
  return ok ? 0 : 2;
}

main().then(
  (c) => process.exit(c),
  (e) => {
    log(`EXCEPTION: ${(e as Error).stack ?? e}`);
    process.exit(1);
  },
);
