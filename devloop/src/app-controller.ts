// desktop_v3 기동 보조 — 빌드는 여기서, 실제 Electron 런치는 Playwright fixture(tests/e2e/fixtures.ts)가
// 담당한다. 하네스는 desktop_v3 를 "외부에서 빌드·구동"할 뿐 코드/빌드 설정에 끼어들지 않는다.

import { spawnSync } from "child_process";
import { existsSync } from "fs";
import { DESKTOP_MAIN_ENTRY, DESKTOP_V3_DIR, IS_WIN, VENV_PYTHON } from "./paths";

const NPM = IS_WIN ? "npm.cmd" : "npm";

export interface BuildResult {
  ok: boolean;
  durationMs: number;
  output: string;
}

/** desktop_v3 를 electron-vite build 로 빌드. out/main/index.js 산출. */
export function buildDesktop(): BuildResult {
  const start = Date.now();
  const proc = spawnSync(NPM, ["run", "build"], {
    cwd: DESKTOP_V3_DIR,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
    // npm.cmd 는 Windows 에서 shell 경유가 안전.
    shell: IS_WIN,
  });
  const output = `${proc.stdout ?? ""}${proc.stderr ?? ""}`;
  return {
    ok: proc.status === 0 && existsSync(DESKTOP_MAIN_ENTRY),
    durationMs: Date.now() - start,
    output,
  };
}

/** 빌드 산출물이 이미 있는지. */
export function isBuilt(): boolean {
  return existsSync(DESKTOP_MAIN_ENTRY);
}

/** 사전 점검 — 하네스가 desktop_v3 를 구동할 수 있는 최소 조건. */
export function preflight(): { ok: boolean; problems: string[] } {
  const problems: string[] = [];
  if (!existsSync(DESKTOP_V3_DIR)) problems.push(`desktop_v3 디렉터리 없음: ${DESKTOP_V3_DIR}`);
  if (!existsSync(VENV_PYTHON)) {
    problems.push(`.venv Python 없음: ${VENV_PYTHON} (api_server 브리지 기동 불가)`);
  }
  return { ok: problems.length === 0, problems };
}
