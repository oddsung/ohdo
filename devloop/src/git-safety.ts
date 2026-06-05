// git 안전장치 — 루프는 항상 전용 브랜치에서만 커밋하고, main 은 절대 직접 수정/푸시하지 않는다.
// 모든 명령은 REPO_ROOT 에서 execFile(shell 미경유)로 실행해 인용/주입 위험을 없앤다.

import { execFileSync } from "child_process";
import { REPO_ROOT } from "./paths";

const MAIN_LIKE = new Set(["main", "master"]);

function git(args: string[]): string {
  return execFileSync("git", args, {
    cwd: REPO_ROOT,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  }).trim();
}

function gitQuiet(args: string[]): { ok: boolean; out: string } {
  try {
    return { ok: true, out: git(args) };
  } catch (e) {
    const err = e as { stdout?: Buffer | string; stderr?: Buffer | string };
    const out = String(err.stderr ?? err.stdout ?? e);
    return { ok: false, out };
  }
}

export function currentBranch(): string {
  return git(["rev-parse", "--abbrev-ref", "HEAD"]);
}

export function isMainLike(branch: string): boolean {
  return MAIN_LIKE.has(branch);
}

export function headSha(): string {
  return git(["rev-parse", "HEAD"]);
}

/** working tree 변경(추적/미추적) 파일 목록 — porcelain 파싱. REPO_ROOT 상대 경로. */
export function statusFiles(): string[] {
  const out = git(["status", "--porcelain"]);
  if (!out) return [];
  return out
    .split("\n")
    .map((l) => l.slice(3).trim())
    .filter(Boolean)
    // rename "old -> new" 는 new 만 취한다.
    .map((p) => (p.includes(" -> ") ? p.split(" -> ")[1] : p));
}

export function isDirty(): boolean {
  return statusFiles().length > 0;
}

/** 전용 작업 브랜치 생성 후 체크아웃. 반환: 브랜치 이름. */
export function createRunBranch(prefix: string, runId: string): string {
  const branch = `${prefix}/auto-${runId}`;
  git(["checkout", "-b", branch]);
  return branch;
}

/**
 * working tree 전체를 커밋한다. main 계열 브랜치에서는 거부한다(안전장치).
 * 변경이 없으면 null 반환.
 */
export function commitAll(message: string): string | null {
  const branch = currentBranch();
  if (isMainLike(branch)) {
    throw new Error(`안전장치: main 계열 브랜치(${branch})에서는 자동 커밋을 거부합니다.`);
  }
  if (!isDirty()) return null;
  git(["add", "-A"]);
  // 커밋 메시지는 -F - (stdin) 대신 -m 다중 사용으로 안전 전달.
  const lines = message.split("\n");
  const args = ["commit"];
  for (const line of lines) args.push("-m", line);
  git(args);
  return headSha();
}

/** 전용 브랜치를 origin 에 푸시. main 계열은 거부. */
export function pushBranch(branch: string): { ok: boolean; out: string } {
  if (isMainLike(branch)) {
    return { ok: false, out: `안전장치: main 계열 브랜치(${branch})는 푸시하지 않습니다.` };
  }
  return gitQuiet(["push", "-u", "origin", branch]);
}

/** 특정 커밋으로 하드 리셋(롤백). 자동 호출 안 함 — 운영자 수동 복구용 헬퍼. */
export function resetHard(sha: string): void {
  const branch = currentBranch();
  if (isMainLike(branch)) {
    throw new Error(`안전장치: main 계열 브랜치(${branch})에서는 reset --hard 를 거부합니다.`);
  }
  git(["reset", "--hard", sha]);
}

/** origin/main 대비 로컬이 몇 커밋 앞/뒤인지(진단용). */
export function aheadBehindMain(): { ahead: number; behind: number } | null {
  const r = gitQuiet(["rev-list", "--left-right", "--count", "origin/main...HEAD"]);
  if (!r.ok) return null;
  const [behind, ahead] = r.out.split(/\s+/).map(Number);
  return { ahead: ahead || 0, behind: behind || 0 };
}
