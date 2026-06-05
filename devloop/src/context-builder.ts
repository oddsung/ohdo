// 프롬프트 조립 — FailureContext 를 claude --print 가 받을 수정 지시문으로 변환한다.

import type { FailureContext } from "./types";

const GUARDRAILS = [
  "## 제약 (반드시 지킬 것)",
  "- 이것은 **자율 루프**가 보내는 요청이다. 사람이 즉시 검토하지 않으니, 추측보다 근본 원인을 고쳐라.",
  "- 수정 대상: `desktop_v3/`(Electron+React+TS), `api_server/`(FastAPI), 필요 시 `core/`.",
  "- **절대 금지**: `devloop/` 하네스 코드 수정, E2E 스펙(`devloop/tests/e2e/`)을 삭제·약화·skip 처리해서 통과시키는 행위.",
  "  테스트는 의도된 검증이다. 테스트가 잘못됐다고 판단되면 고치지 말고 그 근거를 결과에 적어라.",
  "- TS 를 건드렸으면 `desktop_v3` 에서 `npm run typecheck` 로 타입 오류가 없는지 확인하라.",
  "- 변경은 최소·정확하게. 무관한 리팩터링/포매팅 금지.",
  "- 프로젝트 규약은 루트 `CLAUDE.md` 와 `devloop/CLAUDE.md` 를 따른다.",
].join("\n");

export function buildFixPrompt(ctx: FailureContext): string {
  const failureBlocks = ctx.failures
    .map((f, i) => {
      const loc = f.line ? `${f.file}:${f.line}` : f.file;
      return [
        `### 실패 ${i + 1}: ${f.title}`,
        `위치: ${loc}`,
        "```",
        f.message,
        "```",
      ].join("\n");
    })
    .join("\n\n");

  const candidates =
    ctx.candidateFiles.length > 0
      ? ctx.candidateFiles.map((c) => `- ${c}`).join("\n")
      : "- (에러에서 자동 추출된 후보 없음 — 직접 탐색 필요)";

  return [
    "# desktop_v3 E2E 실패 자동 수정 요청",
    "",
    "아래 Playwright E2E 테스트가 실패한다. desktop_v3 앱이 올바르게 동작하도록 **제품 코드**를 고쳐라.",
    "",
    "## 실패한 테스트",
    failureBlocks,
    "",
    "## 관련 후보 파일(추정)",
    candidates,
    "",
    GUARDRAILS,
    "",
    "## 작업 절차",
    "1. 실패 원인을 코드에서 근본적으로 진단한다.",
    "2. 제품 코드를 최소 수정한다.",
    "3. TS 변경 시 타입체크로 회귀가 없는지 확인한다.",
    "4. 무엇을 왜 고쳤는지 2~4줄로 요약해 마지막에 적는다.",
  ].join("\n");
}
