// 시나리오 관찰 드라이버 — ohdo 제품 워크플로 전체를 눈에 보이게 구동한다.
//
// 흐름: ohdo 기동(headed+slowMo) → 세션 생성 → 자연어 요청을 단계별로 입력(AI=agy 가 Python 생성)
//      → "모두 실행" 으로 생성 코드 실행(실제 메모장을 진짜 마우스/키보드로 제어)
//      → 저장된 파일 + step 상태로 시나리오 성공 여부 검증.
//
// 이것은 자동 수정 루프가 아니라 "현재 동작을 관찰"하는 도구다. 무엇이 되고 안 되는지 본 뒤
// 루프의 codegen 수정 경로(core/prompt_builder.py·win_inspector.py·config/prompts.json)를 설계한다.
//
// 실행: cd devloop && npx tsx scenarios/notepad_saveas.mts
// 주의: 실행 단계에서 메모장이 실제로 떠 마우스/키보드를 점유한다 — 그동안 PC 를 만지지 말 것.

import { existsSync, mkdirSync, readFileSync, rmSync } from "fs";
import { dirname } from "path";
import { _electron as electron, type ElectronApplication, type Page } from "playwright";
import {
  DESKTOP_MAIN_ENTRY,
  DESKTOP_V3_DIR,
  REPO_ROOT,
  VENV_PYTHON,
  cleanElectronEnv,
  electronBinary,
} from "../src/paths";

// ── 시나리오 정의 ────────────────────────────────────────────────────────────
const SAVE_PATH = "C:\\Users\\doosung.oh\\My_Projects\\ohdo\\tmp\\ohdo_scenario_test.txt";
const TYPED_TEXT = "안녕하세요 ohdo 자동화 시나리오 테스트입니다";

const STEPS: string[] = [
  "메모장(notepad)을 실행해줘",
  `메모장에 "${TYPED_TEXT}" 라고 입력해줘`,
  `다른 이름으로 저장으로 "${SAVE_PATH}" 경로에 저장해줘`,
];

// agy 생성은 실측상 단계당 ~1.5~2분 걸린다(첫 단계 108초). 넉넉히 5분.
const GEN_TIMEOUT_MS = 300_000; // agy 생성 1건 대기 상한
const RUN_TIMEOUT_MS = 180_000; // 전체 실행 대기 상한

function log(msg: string): void {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  process.stdout.write(`[${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}] ${msg}\n`);
}

interface ApiInfo {
  baseUrl: string;
  token: string;
}

async function api<T>(info: ApiInfo, path: string): Promise<T> {
  const res = await fetch(`${info.baseUrl}${path}`, {
    headers: { Authorization: `Bearer ${info.token}` },
  });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return (await res.json()) as T;
}

interface SessionLite {
  session_id: string;
  updated_at?: string;
}
interface StepLite {
  step_id: number;
  status: string;
  user_request?: string;
}

async function listSessionIds(info: ApiInfo): Promise<Set<string>> {
  const data = await api<{ sessions: SessionLite[] }>(info, "/sessions");
  return new Set(data.sessions.map((s) => s.session_id));
}

async function getSteps(info: ApiInfo, sid: string): Promise<StepLite[]> {
  const data = await api<{ session: { steps: StepLite[] } }>(info, `/sessions/${sid}`);
  return data.session.steps ?? [];
}

async function waitFor(predicate: () => Promise<boolean>, timeoutMs: number, label: string): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await predicate()) return true;
    await new Promise((r) => setTimeout(r, 1000));
  }
  log(`⏱  타임아웃: ${label} (${timeoutMs}ms)`);
  return false;
}

async function main(): Promise<number> {
  // 검증 대상 파일 사전 정리.
  mkdirSync(dirname(SAVE_PATH), { recursive: true });
  if (existsSync(SAVE_PATH)) rmSync(SAVE_PATH);
  log(`시나리오 시작 — 저장 대상: ${SAVE_PATH}`);
  log(`단계 ${STEPS.length}개: ${STEPS.map((s, i) => `(${i + 1}) ${s}`).join("  ")}`);

  log("ohdo 기동(headed, slowMo)…");
  const app: ElectronApplication = await electron.launch({
    executablePath: electronBinary(),
    args: [DESKTOP_MAIN_ENTRY],
    cwd: DESKTOP_V3_DIR,
    env: cleanElectronEnv({ OHDO_PYTHON: VENV_PYTHON, OHDO_PROJECT_ROOT: REPO_ROOT }),
    // 사람이 따라볼 수 있게 각 동작에 지연.
    // @ts-expect-error slowMo 는 launch 옵션으로 지원되지만 타입에 없을 수 있음.
    slowMo: 350,
  });

  const win: Page = await app.firstWindow();
  await win.waitForLoadState("domcontentloaded");
  await win.locator("#root").waitFor({ state: "attached", timeout: 20_000 });
  log("창 로드됨.");

  // ohdo 의 평문-시크릿 감지(#21b)는 따옴표로 감싼 일반 텍스트를 quoted_literal 로 오탐해
  // window.confirm 네이티브 모달을 띄워 자동화를 막는다(실측 발견). 사용자가 "그대로 전송"을
  // 누르는 것과 동등하게 confirm 을 자동 승인하도록 렌더러에 주입한다. (별도로: 이 오탐 자체가
  // ohdo 개선 후보 — 루프가 고칠 대상.)
  win.on("dialog", (d) => void d.accept().catch(() => {}));
  await win.evaluate(() => {
    window.confirm = () => true;
  });
  log("confirm 자동승인 주입(평문감지 모달 우회).");

  // 브리지 API 정보.
  const info = (await win.evaluate(async () => {
    const w = window as unknown as { ohdo?: { getApiInfo?: () => Promise<ApiInfo | null> } };
    return (await w.ohdo?.getApiInfo?.()) ?? null;
  })) as ApiInfo | null;
  if (!info) {
    log("🚨 브리지 API 정보를 못 받음 — 백엔드 미기동. 중단.");
    await app.close();
    return 1;
  }
  log(`브리지: ${info.baseUrl}`);

  // 세션 생성 (EmptyState CTA → 없으면 Ctrl+N).
  const before = await listSessionIds(info);
  const cta = win.getByTestId("empty-create-session");
  if (await cta.count()) {
    log("빈 상태 CTA '새 세션 만들기' 클릭…");
    await cta.click();
  } else {
    log("Ctrl+N 으로 세션 생성…");
    await win.mouse.click(640, 400);
    await win.keyboard.press("Control+n");
  }

  // 새 세션 id 확정.
  let sid = "";
  await waitFor(
    async () => {
      const now = await listSessionIds(info);
      for (const id of now) if (!before.has(id)) { sid = id; return true; }
      return false;
    },
    15_000,
    "새 세션 생성",
  );
  if (!sid) {
    log("🚨 새 세션 id 확정 실패. 중단.");
    await app.close();
    return 1;
  }
  log(`세션 생성됨: ${sid.slice(0, 8)}`);
  await win.locator("textarea").first().waitFor({ state: "visible", timeout: 20_000 });

  // ── 단계별 자연어 요청 → AI 코드 생성 ──────────────────────────────────────
  for (let i = 0; i < STEPS.length; i++) {
    const req = STEPS[i];
    log(`▶ 단계 ${i + 1}/${STEPS.length} 요청: ${req}`);
    const ta = win.locator("textarea").first();
    await ta.click();
    await ta.fill(req);
    await ta.press("Enter");

    const target = i + 1;
    const ok = await waitFor(
      async () => (await getSteps(info, sid)).length >= target,
      GEN_TIMEOUT_MS,
      `단계 ${target} 생성`,
    );
    if (!ok) {
      log(`🚨 단계 ${target} 코드 생성 실패/타임아웃 — 관찰 중단.`);
      break;
    }
    const steps = await getSteps(info, sid);
    log(`  ✓ 생성됨 (현재 step ${steps.length}개)`);
  }

  const genSteps = await getSteps(info, sid);
  log(`생성 완료 — 총 step ${genSteps.length}개. 5초 후 실행합니다 (메모장이 뜹니다, PC 만지지 마세요)…`);
  await new Promise((r) => setTimeout(r, 5000));

  // ── 실행 ("모두 실행") ──────────────────────────────────────────────────────
  if (genSteps.length === 0) {
    log("실행할 step 이 없음 — 중단.");
    await app.close();
    return 1;
  }
  const runBtn = win.getByRole("button", { name: /전체 실행|Run all/ });
  // busy(생성중) 가 남아 있으면 헤더에 Run 버튼이 안 보일 수 있어 잠깐 대기.
  const runReady = await runBtn
    .first()
    .waitFor({ state: "visible", timeout: 20_000 })
    .then(() => true)
    .catch(() => false);
  if (runReady) {
    log("'모두 실행' 클릭 → 생성 코드 실행 시작…");
    await runBtn.first().click();
  } else {
    log("🚨 '모두 실행' 버튼을 못 찾음 — 중단.");
    await app.close();
    return 1;
  }

  // 모든 step 이 pending 을 벗어날 때까지 대기.
  await waitFor(
    async () => {
      const s = await getSteps(info, sid);
      return s.length > 0 && s.every((st) => st.status !== "pending" && st.status !== "running");
    },
    RUN_TIMEOUT_MS,
    "전체 실행 완료",
  );

  // ── 결과 검증 ────────────────────────────────────────────────────────────────
  const finalSteps = await getSteps(info, sid);
  log("── 실행 결과 ──");
  for (const st of finalSteps) {
    log(`  STEP ${st.step_id}: ${st.status}  (${(st.user_request ?? "").slice(0, 40)})`);
  }
  const fileExists = existsSync(SAVE_PATH);
  let content = "";
  if (fileExists) content = readFileSync(SAVE_PATH, "utf8");
  const contentOk = fileExists && content.includes(TYPED_TEXT.slice(0, 6));

  log("── 시나리오 판정 ──");
  log(`  파일 존재(${SAVE_PATH}): ${fileExists ? "✅" : "❌"}`);
  if (fileExists) log(`  내용 일치(입력 텍스트 포함): ${contentOk ? "✅" : "❌"}  내용="${content.slice(0, 60)}"`);
  const allCompleted = finalSteps.length > 0 && finalSteps.every((s) => s.status === "completed");
  log(`  모든 step completed: ${allCompleted ? "✅" : "❌"}`);
  const scenarioOk = allCompleted && contentOk;
  log(scenarioOk ? "🎯 시나리오 성공" : "⚠️  시나리오 미완 — 개선 필요(관찰 데이터 확보)");

  log("8초 후 창을 닫습니다(결과 확인용)…");
  await new Promise((r) => setTimeout(r, 8000));
  await app.close();
  return scenarioOk ? 0 : 2;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    log(`🚨 드라이버 예외: ${(err as Error).stack ?? err}`);
    process.exit(1);
  },
);
