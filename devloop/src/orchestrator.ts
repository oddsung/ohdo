// ohdo devloop 오케스트레이터 — desktop_v3 자율 테스트-개발 루프의 메인 제어.
//
// 루프: [빌드] → [E2E] → 통과면 (자율 전진 or 종료) / 실패면 (분석 → claude 수정 → 커밋) → 반복.
// 안전: 전용 브랜치에서만 커밋, main 직접 수정/푸시 금지, 동일 실패 N회 시 중단, 비용 상한, dry-run.

import { buildDesktop, preflight } from "./app-controller";
import { callClaude } from "./claude-bridge";
import { parseArgs, type LoopConfig } from "./config";
import { buildFixPrompt } from "./context-builder";
import {
  aheadBehindMain,
  commitAll,
  createRunBranch,
  currentBranch,
  headSha,
  isMainLike,
  pushBranch,
} from "./git-safety";
import { History } from "./history";
import { Logger } from "./logger";
import { advance } from "./next-step-advisor";
import { analyze } from "./result-analyzer";
import { runE2E } from "./test-runner";
import type { BuildResult } from "./app-controller";
import type { IterationRecord, RunRecord, TestResult } from "./types";

function makeRunId(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(
    d.getMinutes(),
  )}${p(d.getSeconds())}`;
}

function buildFailureAsTestResult(build: BuildResult): TestResult {
  return {
    total: 1,
    passed: 0,
    failed: 1,
    skipped: 0,
    durationMs: build.durationMs,
    ok: false,
    failures: [
      {
        title: "desktop_v3 빌드 실패 (electron-vite build)",
        file: "desktop_v3",
        message: build.output.split("\n").slice(-40).join("\n").trim() || "(빌드 출력 없음)",
      },
    ],
  };
}

function testSummary(t: TestResult): string {
  return `total=${t.total} pass=${t.passed} fail=${t.failed} skip=${t.skipped}`;
}

function printConfig(logger: Logger, config: LoopConfig): void {
  logger.info(`설정: ${JSON.stringify({ ...config, claudeBin: config.claudeBin })}`);
}

// ── dry-run: 아무것도 건드리지 않고 흐름만 설명 ───────────────────────────────
function runDryRun(config: LoopConfig, logger: Logger): void {
  logger.step("DRY-RUN — 앱·claude·git 미접촉, 흐름 시뮬레이션");
  const pf = preflight();
  logger.info(`preflight: ${pf.ok ? "OK" : "문제 있음"}`);
  for (const p of pf.problems) logger.warn(`  - ${p}`);
  const base = currentBranch();
  const ab = aheadBehindMain();
  logger.info(`현재 브랜치: ${base}${ab ? ` (origin/main 대비 ahead=${ab.ahead} behind=${ab.behind})` : ""}`);
  logger.info(`생성될 전용 브랜치: ${config.branchPrefix}/auto-<runId>`);
  logger.info(`푸시: ${config.push ? "전용 브랜치만 origin 에 푸시" : "안 함(로컬 커밋만)"}`);
  logger.info("");
  logger.info("시뮬레이션된 반복:");
  logger.info(`  iter 1: [빌드${config.buildBeforeRun ? "" : "(생략)"}] → [E2E] → 실패 가정`);
  logger.info("          → 분석(시그니처/후보파일) → claude --print 수정 → 커밋 devloop(iter 1): fix");
  logger.info("  iter 2: [빌드] → [E2E] → 통과 가정");
  if (config.autonomous) {
    logger.info("          → 자율 모드: claude 가 다음 개선 구현 + E2E 추가 → 커밋 devloop(iter 2): advance #1");
    logger.info(`          → --max-features=${config.maxFeatures} 까지 반복`);
  } else {
    logger.info("          → 자율 모드 꺼짐 → 성공 종료");
  }
  logger.info("");
  logger.info(`circuit breaker: 동일 실패 ${config.maxRepeatedFailures}회 연속 시 중단`);
  logger.info(`최대 반복: ${config.maxIterations}, 비용 상한: ${config.maxCostUsd || "무제한"}`);
  logger.step("DRY-RUN 종료 (실제 변경 없음)");
}

// ── live 실행 ────────────────────────────────────────────────────────────────
function runLive(config: LoopConfig, logger: Logger, runId: string): number {
  const pf = preflight();
  if (!pf.ok) {
    logger.error("preflight 실패 — 다음 문제를 해결하세요:");
    for (const p of pf.problems) logger.error(`  - ${p}`);
    return 1;
  }

  const baseBranch = currentBranch();
  const branch = createRunBranch(config.branchPrefix, runId);
  logger.step(`전용 브랜치 생성: ${branch} (base=${baseBranch})`);

  const baselineSha = commitAll(`devloop: baseline (run ${runId})`) ?? headSha();
  logger.info(`baseline: ${baselineSha.slice(0, 10)}`);

  const record: RunRecord = {
    runId,
    branch,
    baseBranch,
    baselineSha,
    startedAt: new Date().toISOString(),
    config: { ...config },
    iterations: [],
  };
  const history = new History(record);

  let lastSig = "";
  let repeatCount = 0;
  let features = 0;
  let totalCost = 0;
  let outcome: RunRecord["outcome"] = "max-iterations";

  for (let n = 1; n <= config.maxIterations; n++) {
    const iterStart = Date.now();
    logger.step(`iteration ${n}/${config.maxIterations}`);

    // 1) 빌드
    let test: TestResult;
    if (config.buildBeforeRun) {
      logger.info("desktop_v3 빌드 중…");
      const build = buildDesktop();
      if (!build.ok) {
        logger.warn(`빌드 실패 (${build.durationMs}ms) — 빌드 오류를 수정 대상으로 처리`);
        test = buildFailureAsTestResult(build);
      } else {
        logger.info(`빌드 OK (${build.durationMs}ms) — E2E 실행`);
        test = runE2E(config);
      }
    } else {
      test = runE2E(config);
    }
    logger.info(`E2E 결과: ${testSummary(test)} (${test.durationMs}ms)`);

    // 2) 통과 처리
    if (test.ok) {
      if (config.autonomous && features < config.maxFeatures) {
        if (config.maxCostUsd > 0 && totalCost >= config.maxCostUsd) {
          logger.warn(`비용 상한 도달($${totalCost.toFixed(2)}) — 자율 전진 중단, 성공 종료`);
          outcome = "success";
          break;
        }
        features++;
        logger.step(`자율 전진 #${features}/${config.maxFeatures} — 다음 개선 구현`);
        const cr = advance(features, config);
        totalCost += cr.costUsd ?? 0;
        const sha = commitAll(
          `devloop(iter ${n}): advance #${features}\n\n${cr.text.slice(0, 500)}`,
        );
        const it: IterationRecord = {
          n,
          phase: "advance",
          startedAt: new Date(iterStart).toISOString(),
          durationMs: Date.now() - iterStart,
          test: { total: test.total, passed: test.passed, failed: test.failed, ok: test.ok },
          claude: {
            ok: cr.ok,
            changedFiles: cr.changedFiles,
            costUsd: cr.costUsd,
            summary: cr.text.slice(0, 300),
          },
          commitSha: sha ?? undefined,
          note: cr.ok ? `변경 ${cr.changedFiles.length}개` : `claude 오류: ${cr.error ?? ""}`,
        };
        history.addIteration(it);
        logger.info(`전진 ${cr.ok ? "완료" : "실패"} — 변경 ${cr.changedFiles.length}개, 커밋 ${sha?.slice(0, 10) ?? "없음"}`);
        continue;
      }
      outcome = "success";
      logger.step("모든 테스트 통과 — 종료");
      break;
    }

    // 3) 실패 처리 + circuit breaker
    const ctx = analyze(test);
    if (ctx.signature === lastSig) repeatCount++;
    else {
      lastSig = ctx.signature;
      repeatCount = 1;
    }
    logger.info(`실패 시그니처 ${ctx.signature} (연속 ${repeatCount}/${config.maxRepeatedFailures}), 후보파일 ${ctx.candidateFiles.length}개`);

    if (repeatCount >= config.maxRepeatedFailures) {
      logger.error(`동일 실패 ${repeatCount}회 연속 — circuit breaker 중단`);
      history.addIteration({
        n,
        phase: "fix",
        startedAt: new Date(iterStart).toISOString(),
        durationMs: Date.now() - iterStart,
        test: { total: test.total, passed: test.passed, failed: test.failed, ok: test.ok },
        failureSignature: ctx.signature,
        note: "circuit breaker",
      });
      outcome = "circuit-break";
      break;
    }

    if (config.maxCostUsd > 0 && totalCost >= config.maxCostUsd) {
      logger.error(`비용 상한 도달($${totalCost.toFixed(2)}) — 중단`);
      outcome = "error";
      break;
    }

    // 4) claude 수정
    logger.info("claude --print 로 수정 요청…");
    const cr = callClaude(buildFixPrompt(ctx), config);
    totalCost += cr.costUsd ?? 0;
    const sha = commitAll(
      `devloop(iter ${n}): fix ${ctx.signature}\n\n${cr.text.slice(0, 500)}`,
    );
    history.addIteration({
      n,
      phase: "fix",
      startedAt: new Date(iterStart).toISOString(),
      durationMs: Date.now() - iterStart,
      test: { total: test.total, passed: test.passed, failed: test.failed, ok: test.ok },
      failureSignature: ctx.signature,
      claude: {
        ok: cr.ok,
        changedFiles: cr.changedFiles,
        costUsd: cr.costUsd,
        summary: cr.text.slice(0, 300),
      },
      commitSha: sha ?? undefined,
      note: cr.ok ? `변경 ${cr.changedFiles.length}개` : `claude 오류: ${cr.error ?? ""}`,
    });
    logger.info(`수정 ${cr.ok ? "적용" : "실패"} — 변경 ${cr.changedFiles.length}개, 커밋 ${sha?.slice(0, 10) ?? "없음"}, 누적비용 $${totalCost.toFixed(3)}`);
  }

  // 마무리
  if (config.push) {
    logger.step(`전용 브랜치 푸시: ${branch}`);
    const r = pushBranch(branch);
    logger.info(r.ok ? "푸시 완료" : `푸시 실패: ${r.out}`);
  }
  history.finish(outcome, new Date().toISOString());

  logger.step(`종료: ${outcome} — 반복 ${record.iterations.length}회, 누적비용 $${totalCost.toFixed(3)}`);
  logger.info(`이력: devloop/runs/${runId}/run.json, devloop/runs/loop-history.json`);
  return outcome === "success" ? 0 : 1;
}

function main(): number {
  let config: LoopConfig;
  try {
    config = parseArgs(process.argv.slice(2));
  } catch (e) {
    process.stderr.write(`인자 오류: ${(e as Error).message}\n`);
    return 2;
  }

  const runId = makeRunId();
  const logger = new Logger(config.dryRun ? undefined : runId);
  logger.step(`ohdo devloop 시작 (runId=${runId})`);
  printConfig(logger, config);

  if (config.dryRun) {
    runDryRun(config, logger);
    return 0;
  }

  // 안전 확인: main 계열에서 직접 돌려도 전용 브랜치로 분기하므로 OK. 경고만.
  const cur = currentBranch();
  if (isMainLike(cur)) {
    logger.warn(`현재 ${cur} 브랜치 — 전용 브랜치로 분기 후 작업합니다(main 직접 수정 안 함).`);
  }

  return runLive(config, logger, runId);
}

process.exit(main());
