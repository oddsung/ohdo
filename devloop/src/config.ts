// 루프 설정 + 인자 파싱. 외부 의존성 없이 process.argv 만 직접 해석한다.

import { claudeBinary } from "./paths";

export interface LoopConfig {
  /** 앱·claude·git 을 건드리지 않고 흐름만 시뮬레이션. */
  dryRun: boolean;
  /** 최대 반복 횟수(수정 + 자율전진 합산 상한). */
  maxIterations: number;
  /** 동일 실패 시그니처가 이 횟수만큼 연속되면 중단(circuit breaker). */
  maxRepeatedFailures: number;
  /** 전용 브랜치를 origin 에 푸시할지. main 은 절대 푸시하지 않는다. */
  push: boolean;
  /** 전용 브랜치 접두사. 최종 이름: <prefix>/auto-<runId>. */
  branchPrefix: string;
  /** 테스트 전부 통과 후 AI 가 다음 개선점을 스스로 구현하는 자율 모드. */
  autonomous: boolean;
  /** 자율 모드에서 한 실행당 추가할 개선(기능) 최대 개수. */
  maxFeatures: number;
  /** 한 실행에서 누적 허용 비용(USD). 초과 시 안전 중단. 0 = 무제한. */
  maxCostUsd: number;
  /** claude --permission-mode 값. unattended 편집을 위해 acceptEdits 기본. */
  permissionMode: string;
  /** claude --model override(미지정 시 CLI 기본). */
  model?: string;
  /** claude 실행 파일. */
  claudeBin: string;
  /** E2E 전에 desktop_v3 를 빌드할지(electron-vite build). */
  buildBeforeRun: boolean;
  /** Playwright --grep 필터. */
  grep?: string;
}

const DEFAULTS: LoopConfig = {
  dryRun: false,
  maxIterations: 20,
  maxRepeatedFailures: 3,
  push: false,
  branchPrefix: "devloop",
  autonomous: false,
  maxFeatures: 3,
  maxCostUsd: 0,
  permissionMode: "acceptEdits",
  model: undefined,
  claudeBin: claudeBinary(),
  buildBeforeRun: true,
  grep: undefined,
};

function nextVal(argv: string[], i: number, flag: string): string {
  const v = argv[i + 1];
  if (v === undefined || v.startsWith("--")) {
    throw new Error(`플래그 ${flag} 에 값이 필요합니다.`);
  }
  return v;
}

export function parseArgs(argv: string[]): LoopConfig {
  const cfg: LoopConfig = { ...DEFAULTS };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case "--dry-run":
        cfg.dryRun = true;
        break;
      case "--push":
        cfg.push = true;
        break;
      case "--no-push":
        cfg.push = false;
        break;
      case "--autonomous":
        cfg.autonomous = true;
        break;
      case "--no-build":
        cfg.buildBeforeRun = false;
        break;
      case "--max-iterations":
        cfg.maxIterations = Number(nextVal(argv, i++, a));
        break;
      case "--max-repeated-failures":
        cfg.maxRepeatedFailures = Number(nextVal(argv, i++, a));
        break;
      case "--max-features":
        cfg.maxFeatures = Number(nextVal(argv, i++, a));
        break;
      case "--max-cost":
        cfg.maxCostUsd = Number(nextVal(argv, i++, a));
        break;
      case "--permission-mode":
        cfg.permissionMode = nextVal(argv, i++, a);
        break;
      case "--model":
        cfg.model = nextVal(argv, i++, a);
        break;
      case "--branch-prefix":
        cfg.branchPrefix = nextVal(argv, i++, a);
        break;
      case "--grep":
        cfg.grep = nextVal(argv, i++, a);
        break;
      case "--help":
      case "-h":
        printHelp();
        process.exit(0);
        break;
      default:
        if (a.startsWith("--")) {
          throw new Error(`알 수 없는 플래그: ${a} (--help 참고)`);
        }
    }
  }
  if (!Number.isFinite(cfg.maxIterations) || cfg.maxIterations < 1) {
    throw new Error("--max-iterations 는 1 이상이어야 합니다.");
  }
  return cfg;
}

export function printHelp(): void {
  // 사용자 노출 텍스트 — 콘솔 출력이 목적.
  process.stdout.write(
    [
      "ohdo devloop — desktop_v3 자율 테스트-개발 루프",
      "",
      "사용법: npm run loop -- [옵션]   |   npx tsx src/orchestrator.ts [옵션]",
      "",
      "옵션:",
      "  --dry-run                 앱·claude·git 미접촉, 흐름만 시뮬레이션",
      "  --max-iterations N        최대 반복 (기본 20)",
      "  --max-repeated-failures N 동일 실패 N회 연속 시 중단 (기본 3)",
      "  --autonomous              테스트 통과 후 다음 개선점 자율 구현",
      "  --max-features N          자율 모드 기능 추가 상한 (기본 3)",
      "  --max-cost USD            누적 비용 상한, 초과 시 중단 (기본 0=무제한)",
      "  --push                    전용 브랜치를 origin 에 푸시 (main 은 절대 안 함)",
      "  --no-build                E2E 전 desktop_v3 빌드 생략",
      "  --permission-mode MODE    claude --permission-mode (기본 acceptEdits)",
      "  --model NAME              claude --model override",
      "  --branch-prefix NAME      전용 브랜치 접두사 (기본 devloop)",
      "  --grep PATTERN            Playwright --grep 필터",
      "",
    ].join("\n") + "\n",
  );
}
