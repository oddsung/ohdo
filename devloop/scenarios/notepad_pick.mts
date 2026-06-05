// 요소 선택(picker) 포함 시나리오 드라이버 — 충실한 ohdo 워크플로 관찰.
//
// 흐름: ohdo 기동 → 세션 생성 → ① "메모장 실행"(NL) → 실행해 메모장 띄움 → ② ohdo '요소 선택'
//      클릭 + pyautogui 로 메모장 입력창을 **실제 클릭**(picker 캡처) → element_context 첨부된
//      채로 "입력" 요청(NL) → ③ "다른이름 저장"(NL) → 전체 실행 → 저장 파일로 검증.
//
// 실행: cd devloop && npx tsx scenarios/notepad_pick.mts
// 주의: 메모장이 실제로 떠 마우스/키보드를 점유한다 — 실행 중 PC 를 만지지 말 것.

import { spawnSync } from "child_process";
import { existsSync, mkdirSync, readFileSync, rmSync } from "fs";
import { dirname, join } from "path";
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

const SAVE_PATH = "C:\\Users\\doosung.oh\\My_Projects\\ohdo\\tmp\\ohdo_pick_test.txt";
const TYPED_TEXT = "안녕하세요 ohdo picker 시나리오 테스트입니다";
const PICK_HELPER = join(DEVLOOP_DIR, "scenarios", "pick_target.py");

const GEN_TIMEOUT_MS = 300_000;
const RUN_TIMEOUT_MS = 180_000;

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
  user_request?: string;
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

async function requestStep(win: Page, info: ApiInfo, sid: string, req: string, target: number): Promise<boolean> {
  log(`▶ 요청(${target}): ${req}`);
  const ta = win.locator("textarea").first();
  await ta.click();
  await ta.fill(req);
  await ta.press("Enter");
  const ok = await waitFor(async () => (await getSteps(info, sid)).length >= target, GEN_TIMEOUT_MS, `단계 ${target} 생성`);
  if (ok) log(`  ✓ 생성됨 (step ${(await getSteps(info, sid)).length}개)`);
  return ok;
}

async function clickRunAll(win: Page): Promise<boolean> {
  const btn = win.getByRole("button", { name: /전체 실행|Run all/ });
  const ready = await btn.first().waitFor({ state: "visible", timeout: 20_000 }).then(() => true).catch(() => false);
  if (ready) await btn.first().click();
  return ready;
}

async function main(): Promise<number> {
  mkdirSync(dirname(SAVE_PATH), { recursive: true });
  if (existsSync(SAVE_PATH)) rmSync(SAVE_PATH);
  log(`picker 시나리오 시작 — 저장: ${SAVE_PATH}`);

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
  log("창 로드 + confirm 자동승인 주입.");

  const info = (await win.evaluate(async () => {
    const w = window as unknown as { ohdo?: { getApiInfo?: () => Promise<ApiInfo | null> } };
    return (await w.ohdo?.getApiInfo?.()) ?? null;
  })) as ApiInfo | null;
  if (!info) {
    log("🚨 브리지 미연결. 중단.");
    await app.close();
    return 1;
  }
  log(`브리지: ${info.baseUrl}`);

  // 세션 생성.
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
    log("🚨 세션 생성 실패.");
    await app.close();
    return 1;
  }
  log(`세션: ${sid.slice(0, 8)}`);
  await win.locator("textarea").first().waitFor({ state: "visible", timeout: 20_000 });

  // ① 메모장 실행 요청 + 실행(메모장 띄우기).
  if (!(await requestStep(win, info, sid, "메모장을 실행해줘", 1))) {
    await app.close();
    return 1;
  }
  log("메모장을 띄우기 위해 step 1 실행…");
  if (!(await clickRunAll(win))) {
    log("🚨 전체 실행 버튼 못 찾음.");
    await app.close();
    return 1;
  }
  await waitFor(
    async () => {
      const s = await getSteps(info, sid);
      return s.length >= 1 && s[0].status !== "pending" && s[0].status !== "running";
    },
    RUN_TIMEOUT_MS,
    "step 1 실행(메모장 오픈)",
  );
  // 메모장이 실제로 떴는지 헬퍼로 확인.
  await new Promise((r) => setTimeout(r, 2000));
  const locate = spawnSync(VENV_PYTHON, [PICK_HELPER, "locate"], { encoding: "utf8" });
  log(`메모장 입력창 위치: ${(locate.stdout || locate.stderr || "").trim()}`);

  // ② 요소 선택(picker) — ohdo '요소 선택' 클릭 + pyautogui 실제 클릭.
  log("'요소 선택'(picker) 클릭 → 메모장 입력창을 실제 마우스로 선택…");
  const pickBtn = win.getByRole("button", { name: /요소 선택|Select element|Pick element/i });
  if (await pickBtn.count()) {
    await pickBtn.first().click();
    await new Promise((r) => setTimeout(r, 2500)); // 오버레이/후크 armed 대기
    const click = spawnSync(VENV_PYTHON, [PICK_HELPER, "click"], { encoding: "utf8" });
    log(`pyautogui 클릭: ${(click.stdout || click.stderr || "").trim()}`);
    const picked = await waitFor(
      async () => (await win.getByText(/첨부된 요소|Attached element/).count()) > 0,
      20_000,
      "요소 선택 첨부",
    );
    log(picked ? "✅ 요소 선택 첨부됨(element_context)" : "⚠️ 요소 선택 첨부 안 됨 — element_context 없이 진행");
  } else {
    log("⚠️ '요소 선택' 버튼 못 찾음 — element_context 없이 진행");
  }

  // ③ 입력 요청(선택 요소 컨텍스트 첨부됨) + 저장 요청.
  if (!(await requestStep(win, info, sid, `선택한 메모장 입력창에 ${TYPED_TEXT} 를 입력해줘`, 2))) {
    await app.close();
    return 1;
  }
  if (!(await requestStep(win, info, sid, `다른 이름으로 저장으로 ${SAVE_PATH} 경로에 저장해줘`, 3))) {
    await app.close();
    return 1;
  }

  // 전체 실행.
  log("전체 실행 → 생성 코드로 메모장 입력·저장 (PC 만지지 마세요)…");
  await new Promise((r) => setTimeout(r, 1500));
  if (!(await clickRunAll(win))) {
    log("🚨 전체 실행 버튼 못 찾음.");
    await app.close();
    return 1;
  }
  await waitFor(
    async () => {
      const s = await getSteps(info, sid);
      return s.length === 3 && s.every((st) => st.status !== "pending" && st.status !== "running");
    },
    RUN_TIMEOUT_MS,
    "전체 실행 완료",
  );

  // 검증.
  const fin = await getSteps(info, sid);
  log("── 실행 결과 ──");
  for (const st of fin) log(`  STEP ${st.step_id}: ${st.status}`);
  const fileOk = existsSync(SAVE_PATH);
  const content = fileOk ? readFileSync(SAVE_PATH, "utf8") : "";
  const contentOk = fileOk && content.includes(TYPED_TEXT.slice(0, 6));
  const allDone = fin.length === 3 && fin.every((s) => s.status === "completed");
  log("── 판정 ──");
  log(`  파일 존재: ${fileOk ? "✅" : "❌"}  내용일치: ${contentOk ? "✅" : "❌"}  전체 completed: ${allDone ? "✅" : "❌"}`);
  if (fileOk) log(`  내용="${content.slice(0, 60)}"`);
  const ok = allDone && contentOk;
  log(ok ? "🎯 picker 시나리오 성공" : "⚠️ 미완 — 개선 데이터 확보");

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
