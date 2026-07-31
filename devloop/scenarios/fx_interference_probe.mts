// §79 FX 간섭 프로브 — FX(오버레이+관찰훅) armed 상태에서 메모장 idempotent 스니펫 실행.
// 실행: cd devloop && npx tsx scenarios/fx_interference_probe.mts
import { spawnSync } from "child_process";
import { _electron as electron, type ElectronApplication, type Page } from "playwright";
import {
  DESKTOP_MAIN_ENTRY,
  DESKTOP_V3_DIR,
  REPO_ROOT,
  VENV_PYTHON,
  cleanElectronEnv,
  electronBinary,
} from "../src/paths";

function log(m: string): void {
  process.stdout.write(`${m}\n`);
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const SNIPPET = `
import subprocess, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from pywinauto import Application
t0 = time.time()
try:
    app = Application(backend='uia').connect(title_re=r'.*메모장', timeout=5, found_index=0)
    print(f'REUSE ({time.time()-t0:.1f}s)')
except Exception:
    print(f'NO-EXISTING ({time.time()-t0:.1f}s) -> Popen')
    subprocess.Popen(['notepad.exe'])
    time.sleep(1.5)
    t1 = time.time()
    try:
        app = Application(backend='uia').connect(title_re=r'.*메모장', timeout=10, found_index=0)
        print(f'CONNECT-OK (+{time.time()-t1:.1f}s)')
    except Exception as e:
        print(f'CONNECT-FAIL (+{time.time()-t1:.1f}s): {type(e).__name__}')
        sys.exit(1)
`;

function closeNotepad(): void {
  // 정중한 종료(WM_CLOSE) — Win11 메모장은 세션 탭을 자동 보존.
  spawnSync(
    VENV_PYTHON,
    [
      "-c",
      "import ctypes\n" +
        "from pywinauto import findwindows\n" +
        "for e in findwindows.find_elements(title_re='.*메모장', backend='uia'):\n" +
        "    h = getattr(e, 'handle', None)\n" +
        "    if h: ctypes.windll.user32.PostMessageW(int(h), 0x0010, 0, 0)\n",
    ],
    { encoding: "utf8" },
  );
}

async function main(): Promise<number> {
  closeNotepad();
  await sleep(1200);

  const app: ElectronApplication = await electron.launch({
    executablePath: electronBinary(),
    args: [DESKTOP_MAIN_ENTRY],
    cwd: DESKTOP_V3_DIR,
    env: cleanElectronEnv({ OHDO_PYTHON: VENV_PYTHON, OHDO_PROJECT_ROOT: REPO_ROOT }),
  });
  const win: Page = await app.firstWindow();
  await win.waitForLoadState("domcontentloaded");
  await win.locator("#root").waitFor({ state: "attached", timeout: 20_000 });
  await sleep(1500);

  await win.evaluate(async () => {
    const w = window as unknown as { ohdo: Record<string, (...a: unknown[]) => Promise<void>> };
    await w.ohdo.runFxStart();
    await w.ohdo.runFxProgress({ current: 0, total: 2, label: "FX probe" });
  });
  log("FX armed (오버레이 + 관찰훅)");
  await sleep(1200);

  const p = spawnSync(VENV_PYTHON, ["-X", "utf8", "-c", SNIPPET], {
    encoding: "utf8",
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    timeout: 40_000,
  });
  log("--- snippet (FX ON) ---");
  log(((p.stdout || "") + (p.stderr || "")).trim());
  const ok = (p.stdout || "").includes("CONNECT-OK") || (p.stdout || "").includes("REUSE");

  await win.evaluate(async () => {
    const w = window as unknown as { ohdo: Record<string, (...a: unknown[]) => Promise<void>> };
    await w.ohdo.runFxStop({ success: true });
  });
  await sleep(1000);
  await app.close();
  closeNotepad();
  log(`VERDICT: ${ok ? "FX 간섭 없음 (스니펫 성공)" : "FX 간섭 의심 (스니펫 실패!)"}`);
  return ok ? 0 : 2;
}

main().then(
  (c) => process.exit(c),
  (e) => {
    log(`EXCEPTION: ${(e as Error).stack ?? e}`);
    process.exit(1);
  },
);
