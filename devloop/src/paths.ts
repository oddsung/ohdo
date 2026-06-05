// 경로 해석 — 하네스(devloop/)와 대상(desktop_v3/, api_server/, .venv)을 잇는 단일 출처.
// devloop 은 desktop_v3 와 독립이므로, 대상 경로는 모두 여기서 REPO_ROOT 기준으로 계산한다.

import { createRequire } from "module";
import { existsSync } from "fs";
import { dirname, join, resolve } from "path";
import { fileURLToPath } from "url";

const here = dirname(fileURLToPath(import.meta.url)); // devloop/src

export const DEVLOOP_DIR = resolve(here, "..");        // devloop/
export const REPO_ROOT = resolve(DEVLOOP_DIR, "..");    // ohdo/ (git 루트)
export const DESKTOP_V3_DIR = join(REPO_ROOT, "desktop_v3");
export const API_SERVER_DIR = join(REPO_ROOT, "api_server");
export const CORE_DIR = join(REPO_ROOT, "core");
export const RUNS_DIR = join(DEVLOOP_DIR, "runs");

export const IS_WIN = process.platform === "win32";

/** desktop_v3 빌드 산출물의 Electron main 엔트리 (electron-vite build 결과). */
export const DESKTOP_MAIN_ENTRY = join(DESKTOP_V3_DIR, "out", "main", "index.js");

/** 루트 .venv 의 Python 인터프리터. main.index.ts 의 dev 분기와 동일 경로. */
export const VENV_PYTHON = IS_WIN
  ? join(REPO_ROOT, ".venv", "Scripts", "python.exe")
  : join(REPO_ROOT, ".venv", "bin", "python");

/**
 * Electron 실행 바이너리 경로.
 *
 * desktop_v3 의 electron 패키지를 재사용한다 — 하네스가 electron 을 중복 설치/다운로드하지
 * 않도록. `require('electron')` 은 바이너리 경로 문자열을 반환한다(electron 패키지의 main).
 * OHDO_ELECTRON env 로 강제 override 가능(디버그/특수 환경).
 */
export function electronBinary(): string {
  if (process.env.OHDO_ELECTRON) return process.env.OHDO_ELECTRON;
  try {
    const requireFromDesktop = createRequire(join(DESKTOP_V3_DIR, "package.json"));
    const p = requireFromDesktop("electron") as unknown;
    if (typeof p === "string" && existsSync(p)) return p;
  } catch {
    /* fall through to constructed path */
  }
  // 폴백: 표준 설치 경로 직접 구성.
  const exe = IS_WIN ? "electron.exe" : "electron";
  const fallback = join(DESKTOP_V3_DIR, "node_modules", "electron", "dist", exe);
  return fallback;
}

/** claude CLI 실행 파일 (PATH 에 있다고 가정, OHDO_CLAUDE_BIN 으로 override). */
export function claudeBinary(): string {
  if (process.env.OHDO_CLAUDE_BIN) return process.env.OHDO_CLAUDE_BIN;
  return IS_WIN ? "claude.cmd" : "claude";
}

/**
 * 자식 Electron 에 넘길 정화된 환경변수.
 *
 * VS Code(=Electron) 통합 터미널 등에서 실행하면 상속 환경에 `ELECTRON_RUN_AS_NODE=1`
 * 과 `VSCODE_*` 가 들어 있다. 그대로 넘기면 desktop_v3 의 electron 이 **node 모드**로 떠서
 * 창을 만들지 않고 Playwright 가 "Process failed to launch" 로 실패한다. 위험 키를 제거한다.
 * (일반 터미널에선 애초에 없으므로 무해.)
 */
export function cleanElectronEnv(extra: Record<string, string> = {}): Record<string, string> {
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) {
    if (v === undefined) continue;
    if (k === "ELECTRON_RUN_AS_NODE") continue; // 핵심: electron 을 node 로 만드는 범인
    if (k === "NODE_OPTIONS") continue; // --require 주입 등 회피
    if (k.startsWith("VSCODE_")) continue; // VS Code IPC/ESM 훅 회피
    env[k] = v;
  }
  return { ...env, ...extra };
}
