// Playwright E2E 실행 + JSON 리포트 정규화 → 단일 TestResult.

import { spawnSync } from "child_process";
import { existsSync, mkdirSync, readFileSync } from "fs";
import { dirname, join } from "path";
import { DEVLOOP_DIR, IS_WIN, REPO_ROOT, VENV_PYTHON, cleanElectronEnv } from "./paths";
import type { LoopConfig } from "./config";
import type { TestFailure, TestResult } from "./types";

const NPX = IS_WIN ? "npx.cmd" : "npx";
const REPORT_PATH = join(DEVLOOP_DIR, "runs", "last-playwright.json");

/** Playwright JSON 리포트의 (부분) 형태. */
interface PwReport {
  suites?: PwSuite[];
  stats?: { expected?: number; unexpected?: number; skipped?: number; flaky?: number; duration?: number };
}
interface PwSuite {
  title?: string;
  file?: string;
  specs?: PwSpec[];
  suites?: PwSuite[];
}
interface PwSpec {
  title?: string;
  ok?: boolean;
  file?: string;
  line?: number;
  tests?: PwTest[];
}
interface PwTest {
  status?: string;
  results?: PwTestResult[];
}
interface PwTestResult {
  status?: string;
  duration?: number;
  error?: { message?: string; stack?: string };
  errors?: { message?: string }[];
}

function cleanError(msg: string | undefined): string {
  if (!msg) return "(에러 메시지 없음)";
  // ANSI 컬러 코드 제거 + 앞부분만(스택 노이즈 절단).
  // eslint-disable-next-line no-control-regex
  const noAnsi = msg.replace(/\[[0-9;]*m/g, "");
  return noAnsi.split("\n").slice(0, 12).join("\n").trim();
}

function walk(
  suite: PwSuite,
  parentTitles: string[],
  acc: { total: number; passed: number; failed: number; skipped: number; failures: TestFailure[] },
): void {
  const titles = suite.title ? [...parentTitles, suite.title] : parentTitles;
  for (const spec of suite.specs ?? []) {
    acc.total++;
    const results = (spec.tests ?? []).flatMap((t) => t.results ?? []);
    const statuses = results.map((r) => r.status);
    const isSkipped = statuses.length > 0 && statuses.every((s) => s === "skipped");
    const passed = spec.ok === true && !isSkipped;
    if (isSkipped) {
      acc.skipped++;
    } else if (passed) {
      acc.passed++;
    } else {
      acc.failed++;
      const failing = results.find((r) => r.status && r.status !== "passed" && r.status !== "skipped");
      const errMsg =
        failing?.error?.message ?? failing?.errors?.[0]?.message ?? failing?.error?.stack;
      acc.failures.push({
        title: [...titles, spec.title ?? "(무제)"].filter(Boolean).join(" › "),
        file: spec.file ?? suite.file ?? "(파일 미상)",
        line: spec.line,
        message: cleanError(errMsg),
        snippet: failing?.error?.stack ? cleanError(failing.error.stack) : undefined,
      });
    }
  }
  for (const child of suite.suites ?? []) walk(child, titles, acc);
}

function parseReport(report: PwReport): TestResult {
  const acc = { total: 0, passed: 0, failed: 0, skipped: 0, failures: [] as TestFailure[] };
  for (const s of report.suites ?? []) walk(s, [], acc);
  return {
    total: acc.total,
    passed: acc.passed,
    failed: acc.failed,
    skipped: acc.skipped,
    durationMs: Math.round(report.stats?.duration ?? 0),
    ok: acc.failed === 0 && acc.total > 0,
    failures: acc.failures,
    reportPath: REPORT_PATH,
  };
}

/** Playwright 를 실행하고 결과를 정규화해 돌려준다. */
export function runE2E(config: LoopConfig): TestResult {
  const args = ["playwright", "test"];
  if (config.grep) args.push("--grep", config.grep);

  // JSON 리포트는 환경변수로 강제(절대경로). config 의 outputFile 은 runs/ 디렉터리가
  // 없으면 조용히 실패하지만, PLAYWRIGHT_JSON_OUTPUT_NAME 은 디렉터리까지 만들어 확실히 쓴다.
  mkdirSync(dirname(REPORT_PATH), { recursive: true });

  const proc = spawnSync(NPX, args, {
    cwd: DEVLOOP_DIR,
    encoding: "utf8",
    maxBuffer: 128 * 1024 * 1024,
    shell: IS_WIN,
    // 빌드본 Electron 이 .venv python 으로 api_server 를 띄우도록 핀(휴리스틱 의존 제거).
    // cleanElectronEnv: VS Code 상속 환경의 ELECTRON_RUN_AS_NODE 등 제거(자식 electron launch 보호).
    env: cleanElectronEnv({
      OHDO_PYTHON: VENV_PYTHON,
      OHDO_PROJECT_ROOT: REPO_ROOT,
      PLAYWRIGHT_JSON_OUTPUT_NAME: REPORT_PATH,
      CI: "1", // forbidOnly 등 CI 동작 일관성.
    }),
  });

  if (!existsSync(REPORT_PATH)) {
    // 리포트가 없으면 = playwright 자체가 못 돈 것(설치/설정 오류). 전부 실패로 간주.
    return {
      total: 0,
      passed: 0,
      failed: 1,
      skipped: 0,
      durationMs: 0,
      ok: false,
      failures: [
        {
          title: "playwright 실행 실패",
          file: "(harness)",
          message: cleanError(
            `Playwright 가 리포트를 생성하지 못했습니다 (exit=${proc.status}).\n` +
              `${proc.stdout ?? ""}\n${proc.stderr ?? ""}`,
          ),
        },
      ],
    };
  }

  let report: PwReport;
  try {
    report = JSON.parse(readFileSync(REPORT_PATH, "utf8")) as PwReport;
  } catch (e) {
    return {
      total: 0,
      passed: 0,
      failed: 1,
      skipped: 0,
      durationMs: 0,
      ok: false,
      failures: [{ title: "리포트 파싱 실패", file: REPORT_PATH, message: String(e) }],
    };
  }
  return parseReport(report);
}
