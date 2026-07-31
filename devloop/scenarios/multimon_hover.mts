// 멀티모니터 picker 실측 — handoff §76(브리지 DPI awareness) + §77(디스플레이별 hover 오버레이).
//
// 흐름: ohdo 기동 → 세션 → 계산기를 DPI 다른 보조모니터로 이동 → '요소 선택' →
//      num7Button 위로 실제 마우스 hover → 전 모니터 스크린샷(붉은 박스가 그 디스플레이에만,
//      요소 위에 정확히 있는지) → 실제 클릭 픽 → '첨부된 요소' 칩 텍스트로 §76 정확도 확인.
//
// 실행: cd devloop && npx tsx scenarios/multimon_hover.mts
// 주의: 마우스를 점유한다 — 실행 중 PC 만지지 말 것. AI 생성은 호출 안 함(무비용).

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
const SHOT_DIR = process.env.MULTIMON_SHOT_DIR ?? join(DEVLOOP_DIR, "runs", "multimon");

function log(m: string): void {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  process.stdout.write(`[${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}] ${m}\n`);
}

function helper(...args: string[]): string {
  const p = spawnSync(VENV_PYTHON, [HELPER, ...args], {
    encoding: "utf8",
    env: { ...process.env, PYTHONIOENCODING: "utf-8", MULTIMON_SHOT_DIR: SHOT_DIR },
  });
  return ((p.stdout || "") + (p.stderr || "")).trim();
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

interface ApiInfo {
  baseUrl: string;
  token: string;
}

async function api<T>(info: ApiInfo, path: string): Promise<T> {
  const res = await fetch(`${info.baseUrl}${path}`, {
    headers: { Authorization: `Bearer ${info.token}` },
  });
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return (await res.json()) as T;
}
async function listIds(info: ApiInfo): Promise<Set<string>> {
  const d = await api<{ sessions: { session_id: string }[] }>(info, "/sessions");
  return new Set(d.sessions.map((s) => s.session_id));
}
async function apiPost(info: ApiInfo, path: string): Promise<void> {
  await fetch(`${info.baseUrl}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${info.token}` },
  }).catch(() => {});
}
async function waitFor(pred: () => Promise<boolean>, ms: number, label: string): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < ms) {
    if (await pred()) return true;
    await sleep(700);
  }
  log(`TIMEOUT: ${label}`);
  return false;
}

async function main(): Promise<number> {
  log("멀티모니터 picker 실측 시작 (§76/§77)");

  const app: ElectronApplication = await electron.launch({
    executablePath: electronBinary(),
    args: [DESKTOP_MAIN_ENTRY],
    cwd: DESKTOP_V3_DIR,
    env: cleanElectronEnv({ OHDO_PYTHON: VENV_PYTHON, OHDO_PROJECT_ROOT: REPO_ROOT }),
  });
  const win: Page = await app.firstWindow();
  await win.waitForLoadState("domcontentloaded");
  await win.locator("#root").waitFor({ state: "attached", timeout: 20_000 });
  win.on("dialog", (d) => void d.accept().catch(() => {}));
  await win.evaluate(() => {
    window.confirm = () => true;
  });

  const info = (await win.evaluate(async () => {
    const w = window as unknown as { ohdo?: { getApiInfo?: () => Promise<ApiInfo | null> } };
    return (await w.ohdo?.getApiInfo?.()) ?? null;
  })) as ApiInfo | null;
  if (!info) {
    log("FAIL: 브리지 미연결");
    await app.close();
    return 1;
  }
  log(`브리지: ${info.baseUrl}`);

  // 세션 생성 (pick 캡처 저장에 필요).
  const before = await listIds(info);
  const cta = win.getByTestId("empty-create-session");
  if (await cta.count()) await cta.click();
  else {
    await win.mouse.click(640, 400);
    await win.keyboard.press("Control+n");
  }
  let sid = "";
  await waitFor(
    async () => {
      for (const id of await listIds(info)) if (!before.has(id)) { sid = id; return true; }
      return false;
    },
    15_000,
    "세션 생성",
  );
  if (!sid) {
    log("FAIL: 세션 생성 실패");
    await app.close();
    return 1;
  }
  log(`세션: ${sid}`);
  await win.locator("textarea").first().waitFor({ state: "visible", timeout: 20_000 });

  // 계산기를 보조모니터(주와 DPI 최대 차이)로 이동 + num7 좌표 확보.
  log("계산기 준비(보조모니터로 이동)…");
  const setup = helper("setup");
  log(setup);
  const mt = setup.match(/TARGET num7Button (\d+) (\d+)/);
  if (!mt) {
    log("FAIL: setup 좌표 파싱 실패");
    await app.close();
    helper("teardown");
    return 1;
  }
  const tx = Number(mt[1]);
  const ty = Number(mt[2]);

  // '요소 선택' 진입 → hover → 스크린샷 → 클릭 픽.
  const pickBtn = win.getByRole("button", { name: /요소 선택|Select element|Pick element/i }).first();
  const pickReady = await waitFor(
    async () => (await pickBtn.count()) > 0 && (await pickBtn.isEnabled().catch(() => false)),
    15_000,
    "요소선택 버튼 활성",
  );
  if (!pickReady) {
    log("FAIL: 요소선택 버튼 비활성");
    await app.close();
    helper("teardown");
    return 1;
  }
  await pickBtn.click();
  await sleep(3000); // 최소화 + 디스플레이별 오버레이 + LL 후크 armed 대기

  log(`hover → num7Button (${tx}, ${ty})`);
  log(helper("hover", String(tx), String(ty)));
  await sleep(1800); // hover 폴링 → 붉은 박스 렌더 대기
  log("전 모니터 스크린샷(hover 상태)…");
  for (const line of helper("shot", "hover_num7").split("\n")) log(`  ${line}`);

  log("실제 클릭 픽…");
  log(helper("click", String(tx), String(ty)));
  const attached = await waitFor(
    async () => (await win.getByText(/첨부된 요소|Attached element/).count()) > 0,
    25_000,
    "요소 첨부",
  );
  let chip = "";
  if (attached) {
    chip = (await win.getByText(/첨부된 요소|Attached element/).first().textContent().catch(() => "")) ?? "";
    // 칩 주변 컨테이너 텍스트도 시도 (요소 이름 포함 가능).
    const parentText =
      (await win
        .getByText(/첨부된 요소|Attached element/)
        .first()
        .locator("xpath=..")
        .textContent()
        .catch(() => "")) ?? "";
    log(`첨부 칩: "${chip.trim()}" / 컨테이너: "${parentText.trim()}"`);
  } else {
    await apiPost(info, "/pick/cancel");
  }
  await sleep(800);
  await win.screenshot({ path: join(SHOT_DIR, "app_after_pick.png") }).catch(() => {});

  log("── 판정 ──");
  log(`  §77 hover 박스: hover_num7_*.png 스크린샷 눈검증 (보조모니터에만 + num7 위)`);
  log(`  §76 픽 정확도: 첨부 ${attached ? "OK" : "FAIL"} — 세션 ${sid} captures 확인`);

  await app.close();
  helper("teardown");
  return attached ? 0 : 2;
}

main().then(
  (c) => process.exit(c),
  (e) => {
    log(`EXCEPTION: ${(e as Error).stack ?? e}`);
    helper("teardown");
    process.exit(1);
  },
);
