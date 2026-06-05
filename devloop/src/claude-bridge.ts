// claude --print 래퍼 — 프롬프트를 stdin 으로 넘기고 JSON 결과를 파싱한다.
// 변경 파일은 호출 전후 git status 스냅샷 diff 로 감지(오케스트레이터가 호출 전 working tree 를
// 깨끗이 커밋해 두므로, 호출 후 status 가 곧 claude 의 변경분).

import { spawnSync } from "child_process";
import { IS_WIN, REPO_ROOT } from "./paths";
import { statusFiles } from "./git-safety";
import type { LoopConfig } from "./config";
import type { ClaudeResult } from "./types";

const CALL_TIMEOUT_MS = 15 * 60 * 1000; // 단일 호출 상한 15분.

interface ClaudeJson {
  is_error?: boolean;
  result?: string;
  total_cost_usd?: number;
  duration_ms?: number;
  subtype?: string;
}

/**
 * claude 를 헤드리스로 호출해 코드 수정을 수행시킨다.
 * @param prompt 수정 지시문(stdin 으로 전달).
 */
export function callClaude(prompt: string, config: LoopConfig): ClaudeResult {
  const before = new Set(statusFiles());
  const start = Date.now();

  const args = ["--print", "--output-format", "json", "--permission-mode", config.permissionMode];
  if (config.model) args.push("--model", config.model);

  const proc = spawnSync(config.claudeBin, args, {
    cwd: REPO_ROOT,
    input: prompt,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
    timeout: CALL_TIMEOUT_MS,
    shell: IS_WIN, // claude.cmd
    env: { ...process.env },
  });

  const durationMs = Date.now() - start;
  const after = statusFiles();
  const changedFiles = after.filter((f) => !before.has(f));

  if (proc.error) {
    return {
      ok: false,
      text: "",
      durationMs,
      changedFiles,
      error: `claude 실행 실패: ${proc.error.message}`,
    };
  }

  const stdout = proc.stdout ?? "";
  let parsed: ClaudeJson | null = null;
  try {
    parsed = JSON.parse(stdout) as ClaudeJson;
  } catch {
    // JSON 파싱 실패 — 출력 원문을 텍스트로 보존.
    return {
      ok: proc.status === 0 && changedFiles.length > 0,
      text: stdout.slice(0, 4000),
      durationMs,
      changedFiles,
      error: proc.status === 0 ? undefined : `claude exit=${proc.status}: ${proc.stderr ?? ""}`,
    };
  }

  return {
    ok: !parsed.is_error && proc.status === 0,
    text: parsed.result ?? "",
    costUsd: parsed.total_cost_usd,
    durationMs: parsed.duration_ms ?? durationMs,
    changedFiles,
    raw: parsed,
    error: parsed.is_error ? `claude 오류(subtype=${parsed.subtype})` : undefined,
  };
}
