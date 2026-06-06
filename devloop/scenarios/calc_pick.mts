// 계산기 요소 선택(picker) 시나리오 — 7 + 3 = 10. 버튼 4개를 실제 마우스로 픽.
//
// 흐름: ohdo 기동 → 세션 → 계산기 실행(NL) → 실행 → [num7,+,num3,=] 각 버튼을 ohdo '요소
//      선택' + pyautogui 실제 클릭으로 픽 → "선택한 버튼 클릭"(NL, element_context 첨부) → 생성
//      → 전체 실행 → CalculatorResults 가 10 인지 검증.
//
// 실행: cd devloop && npx tsx scenarios/calc_pick.mts
// 주의: 계산기가 떠 마우스를 점유한다 — 실행 중 PC 만지지 말 것.

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

const HELPER = join(DEVLOOP_DIR, "scenarios", "calc_pick_target.py");
const BUTTONS = [
  { id: "num7Button", label: "7" },
  { id: "plusButton", label: "+" },
  { id: "num3Button", label: "3" },
  { id: "equalButton", label: "=" },
];
const EXPECT = "10";
const GEN_TIMEOUT_MS = 300_000;

function log(m: string): void {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  process.stdout.write(`[${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}] ${m}\n`);
}

interface ApiInfo {
  baseUrl: string;
  token: string;
}
interface StepLite {
  step_id: number;
  status: string;
}

async function api<T>(info: ApiInfo, path: string): Promise<T> {
  const res = await fetch(`${info.baseUrl}${path}`, {
    headers: { Authorization: `Bearer ${info.token}` },
  });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return (await res.json()) as T;
}
async function listIds(info: ApiInfo): Promise<Set<string>> {
  const d = await api<{ sessions: { session_id: string }[] }>(info, "/sessions");
  return new Set(d.sessions.map((s) => s.session_id));
}
async function getSteps(info: ApiInfo, sid: string): Promise<StepLite[]> {
  const d = await api<{ session: { steps: StepLite[] } }>(info, `/sessions/${sid}`);
  return d.session.steps ?? [];
}
async function waitFor(pred: () => Promise<boolean>, ms: number, label: string): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < ms) {
    if (await pred()) return true;
    await new Promise((r) => setTimeout(r, 1000));
  }
  log(`⏱  타임아웃: ${label}`);
  return false;
}
function helper(...args: string[]): string {
  const p = spawnSync(VENV_PYTHON, [HELPER, ...args], {
    encoding: "utf8",
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  });
  return ((p.stdout || "") + (p.stderr || "")).trim();
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function apiPost(info: ApiInfo, path: string, body?: object): Promise<void> {
  await fetch(`${info.baseUrl}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${info.token}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  }).catch(() => {});
}

/** '요소 선택' 버튼이 활성(enabled)될 때까지 대기 — picking 상태가 풀렸다는 신호. */
async function ensurePickReady(win: Page): Promise<boolean> {
  const b = win.getByRole("button", { name: /요소 선택|Select element|Pick element/i }).first();
  return waitFor(
    async () => (await b.count()) > 0 && (await b.isEnabled().catch(() => false)),
    15_000,
    "요소선택 버튼 활성",
  );
}

/** 계산기가 떠서 UIA 로 버튼을 찾을 수 있을 때까지 대기. */
async function waitCalcReady(): Promise<boolean> {
  return waitFor(async () => /^\d+\s+\d+/.test(helper("locate", "num7Button")), 60_000, "계산기 준비");
}

async function requestStep(win: Page, info: ApiInfo, sid: string, req: string, target: number): Promise<boolean> {
  log(`▶ 요청(${target}): ${req}`);
  const ta = win.locator("textarea").first();
  await ta.click();
  await ta.fill(req);
  await ta.press("Enter");
  return waitFor(async () => (await getSteps(info, sid)).length >= target, GEN_TIMEOUT_MS, `step ${target} 생성`);
}

async function clickRunAll(win: Page): Promise<boolean> {
  const b = win.getByRole("button", { name: /전체 실행|Run all/ });
  const ok = await b.first().waitFor({ state: "visible", timeout: 20_000 }).then(() => true).catch(() => false);
  if (ok) await b.first().click();
  return ok;
}

async function pickButton(win: Page, info: ApiInfo, id: string, label: string, attempts = 3): Promise<boolean> {
  const pickBtn = win.getByRole("button", { name: /요소 선택|Select element|Pick element/i }).first();
  for (let a = 1; a <= attempts; a++) {
    // 이전 픽이 풀려 ✶ 가 활성(enabled)일 때까지 대기 — picking 레이스 회피.
    if (!(await ensurePickReady(win))) {
      log(`  ⚠️ [${label}] ✶ 비활성 지속 — 픽 취소 시도`);
      await apiPost(info, "/pick/cancel");
      await win.keyboard.press("Escape").catch(() => {});
      await sleep(1500);
    }
    log(`'요소 선택' → 계산기 [${label}] 픽 시도 ${a}/${attempts}…`);
    await pickBtn.click().catch(() => {});
    await sleep(3000); // 최소화+오버레이+후크 armed 대기
    log(`  pyautogui: ${helper("click", id)}`);
    const ok = await waitFor(
      async () => (await win.getByText(/첨부된 요소|Attached element/).count()) > 0,
      25_000,
      `[${label}] 첨부(시도 ${a})`,
    );
    if (ok) {
      log(`  ✅ [${label}] 요소 첨부됨`);
      return true;
    }
    // 실패 → 스크린샷 + API 취소(Esc 보다 확실) 후 재시도.
    log(`  ⚠️ [${label}] 첨부 실패(시도 ${a}) — 스크린샷 + 취소 후 재시도`);
    helper("shot", `calc_pickfail_${label}_${a}`);
    await apiPost(info, "/pick/cancel");
    await win.keyboard.press("Escape").catch(() => {});
    await sleep(2000);
  }
  return false;
}

async function main(): Promise<number> {
  log("계산기 picker 시나리오 시작 (7 + 3 = 10)");
  const app: ElectronApplication = await electron.launch({
    executablePath: electronBinary(),
    args: [DESKTOP_MAIN_ENTRY],
    cwd: DESKTOP_V3_DIR,
    env: cleanElectronEnv({ OHDO_PYTHON: VENV_PYTHON, OHDO_PROJECT_ROOT: REPO_ROOT }),
    // @ts-expect-error slowMo 지원되나 타입 없음
    slowMo: 300,
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
    log("🚨 브리지 미연결");
    await app.close();
    return 1;
  }
  log(`브리지: ${info.baseUrl}`);

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
    log("🚨 세션 생성 실패");
    await app.close();
    return 1;
  }
  log(`세션: ${sid.slice(0, 8)}`);
  await win.locator("textarea").first().waitFor({ state: "visible", timeout: 20_000 });

  // 1) 계산기 실행 + 실행(버튼 픽을 위해 계산기를 띄움).
  if (!(await requestStep(win, info, sid, "계산기를 실행해줘", 1))) {
    await app.close();
    return 1;
  }
  log("계산기를 띄우기 위해 step 1 실행…");
  if (!(await clickRunAll(win))) {
    await app.close();
    return 1;
  }
  await waitCalcReady();
  await new Promise((r) => setTimeout(r, 1500));

  // 2) 각 버튼 픽 + "선택한 버튼 클릭" 생성. 픽 실패 시 추측 방지 위해 중단.
  let target = 1;
  for (const b of BUTTONS) {
    const picked = await pickButton(win, info, b.id, b.label);
    if (!picked) {
      log(`🚨 [${b.label}] 픽 실패 — 추측 방지 위해 중단(element_context 없이 생성 안 함)`);
      await app.close();
      return 2;
    }
    target += 1;
    if (!(await requestStep(win, info, sid, "선택한 버튼을 클릭해줘", target))) {
      log(`🚨 [${b.label}] step 생성 실패 — 중단`);
      await app.close();
      return 1;
    }
  }

  // 3) 전체 실행 전 계산기 초기화(픽 중 잔여 입력 방지) → 실행 → 결과 검증.
  log(`계산기 초기화: ${helper("click", "clearButton")}`);
  await new Promise((r) => setTimeout(r, 800));
  log("전체 실행 → 계산기 버튼 클릭 (PC 만지지 마세요)…");
  await new Promise((r) => setTimeout(r, 1500));
  if (!(await clickRunAll(win))) {
    await app.close();
    return 1;
  }
  // 결과가 10 이 될 때까지 폴링(step.status 미신뢰 → 실제 디스플레이로 검증).
  let result = "";
  const ok = await waitFor(
    async () => {
      result = helper("result");
      return result.includes(EXPECT);
    },
    90_000,
    "계산 결과 10",
  );
  log("── 판정 ──");
  log(`  CalculatorResults: "${result}"`);
  log(`  결과 ${EXPECT} 포함: ${ok ? "✅" : "❌"}`);
  const finSteps = await getSteps(info, sid);
  log(`  생성 step 수: ${finSteps.length} (예상 5)`);
  log(ok ? "🎯 계산기 picker 시나리오 성공" : "⚠️ 미완 — 개선 데이터 확보");

  log("8초 후 종료…");
  await new Promise((r) => setTimeout(r, 8000));
  await app.close();
  return ok ? 0 : 2;
}

main().then(
  (c) => process.exit(c),
  (e) => {
    log(`🚨 예외: ${(e as Error).stack ?? e}`);
    process.exit(1);
  },
);
