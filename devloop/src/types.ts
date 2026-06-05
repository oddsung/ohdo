// 하네스 전역에서 공유하는 데이터 구조.

/** Playwright 실행 결과를 정규화한 단일 객체. */
export interface TestResult {
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  durationMs: number;
  ok: boolean;
  failures: TestFailure[];
  /** 원본 Playwright JSON 리포트 경로(있으면). */
  reportPath?: string;
}

export interface TestFailure {
  title: string;
  /** 스펙 파일 경로(REPO_ROOT 상대 가능). */
  file: string;
  line?: number;
  /** 정리된 에러 메시지(스택 앞부분). */
  message: string;
  /** 에러 컨텍스트 스니펫(있으면). */
  snippet?: string;
}

/** 실패를 수정 가능한 컨텍스트로 정리한 결과. */
export interface FailureContext {
  signature: string; // circuit breaker 용 안정 식별자
  failures: TestFailure[];
  /** 에러에서 추정한 관련 소스 파일들(REPO_ROOT 상대). */
  candidateFiles: string[];
}

/** claude --print 호출 결과. */
export interface ClaudeResult {
  ok: boolean;
  /** claude 의 최종 텍스트 결과(요약). */
  text: string;
  costUsd?: number;
  durationMs: number;
  /** 호출 전후 git diff 로 감지한 변경 파일(REPO_ROOT 상대). */
  changedFiles: string[];
  raw?: unknown;
  error?: string;
}

/** loop-history.json 의 iteration 한 건. */
export interface IterationRecord {
  n: number;
  phase: "fix" | "advance";
  startedAt: string;
  durationMs: number;
  test: { total: number; passed: number; failed: number; ok: boolean };
  failureSignature?: string;
  claude?: { ok: boolean; changedFiles: string[]; costUsd?: number; summary: string };
  commitSha?: string;
  note?: string;
}

/** 한 번의 루프 실행 전체 기록. */
export interface RunRecord {
  runId: string;
  branch: string;
  startedAt: string;
  finishedAt?: string;
  baseBranch: string;
  baselineSha?: string;
  config: Record<string, unknown>;
  outcome?: "success" | "max-iterations" | "circuit-break" | "error" | "dry-run";
  iterations: IterationRecord[];
  totalCostUsd?: number;
}
