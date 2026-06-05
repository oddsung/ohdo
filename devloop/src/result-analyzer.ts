// 실패 분석 — TestResult 의 실패들을 수정 가능한 FailureContext 로 정리하고,
// circuit breaker 용 안정 시그니처를 만든다.

import { createHash } from "crypto";
import { existsSync } from "fs";
import { isAbsolute, join, relative } from "path";
import { REPO_ROOT } from "./paths";
import type { FailureContext, TestResult } from "./types";

/** 실패 집합의 안정 식별자 — 동일 실패 반복 감지(같은 테스트+같은 에러 첫 줄). */
export function failureSignature(result: TestResult): string {
  const parts = result.failures
    .map((f) => `${f.title}::${f.message.split("\n")[0]}`)
    .sort();
  return createHash("sha1").update(parts.join("|")).digest("hex").slice(0, 12);
}

const FILE_TOKEN = /([\w./\\-]+\.(?:tsx?|jsx?|py))(?::\d+)?/g;

/** 에러 텍스트에서 REPO_ROOT 내 실재 소스 파일들을 추정 추출. */
function extractCandidateFiles(texts: string[]): string[] {
  const found = new Set<string>();
  for (const text of texts) {
    const matches = text.matchAll(FILE_TOKEN);
    for (const m of matches) {
      let raw = m[1].replace(/\\/g, "/");
      // node_modules / 하네스 자신은 수정 대상 아님.
      if (raw.includes("node_modules") || raw.includes("/devloop/")) continue;
      const abs = isAbsolute(raw) ? raw : join(REPO_ROOT, raw);
      if (existsSync(abs)) {
        const rel = relative(REPO_ROOT, abs).replace(/\\/g, "/");
        if (!rel.startsWith("..")) found.add(rel);
      }
    }
  }
  return [...found];
}

export function analyze(result: TestResult): FailureContext {
  const texts = result.failures.flatMap((f) => [f.message, f.snippet ?? "", f.file]);
  return {
    signature: failureSignature(result),
    failures: result.failures,
    candidateFiles: extractCandidateFiles(texts),
  };
}
