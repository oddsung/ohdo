// 자율 전진 — 모든 테스트가 통과한 뒤, AI 가 다음 개선점을 스스로 정해 구현하고
// 그것을 검증하는 E2E 스펙까지 추가한다. (--autonomous 일 때만, --max-features 상한)

import { callClaude } from "./claude-bridge";
import type { LoopConfig } from "./config";
import type { ClaudeResult } from "./types";

const ADVANCE_GUARDRAILS = [
  "## 제약 (반드시 지킬 것)",
  "- 이것은 **자율 개발 루프**다. 사람이 즉시 검토하지 않으니, 작고 안전하며 가치 있는 단위로 전진하라.",
  "- 한 번에 **개선 1개**만. 범위를 넓히지 마라.",
  "- 구현은 `desktop_v3/`(우선), 필요 시 `api_server/`·`core/`.",
  "- 반드시 그 개선을 검증하는 **Playwright E2E 스펙**을 `devloop/tests/e2e/` 에 추가/확장하라.",
  "  (이 스펙 추가만이 devloop/ 에 허용되는 변경이다. devloop/src 하네스 로직은 건드리지 마라.)",
  "- 기존 통과 테스트를 깨지 마라. TS 변경 시 `desktop_v3` 에서 `npm run typecheck` 확인.",
  "- 외부 네트워크 호출이나 실제 Windows 네이티브 자동화에 의존하는 테스트는 피하라(루프가 무인 실행됨).",
  "- 루트 `CLAUDE.md` 와 `devloop/CLAUDE.md` 규약을 따른다.",
].join("\n");

export function buildAdvancePrompt(featureIndex: number): string {
  return [
    `# desktop_v3 자율 개선 #${featureIndex}`,
    "",
    "현재 desktop_v3 의 모든 E2E 가 통과한다. 완성도를 높일 **다음 개선 1가지**를 스스로 정해 구현하라.",
    "",
    "## 절차",
    "1. desktop_v3 의 현재 상태를 빠르게 파악해 가장 가치 있는 작은 개선 1개를 고른다.",
    "   (UX 빈틈, 에러 처리 누락, 접근성, 빈 상태 처리, 명확한 버그 등)",
    "2. 제품 코드를 구현한다.",
    "3. 그 개선을 검증하는 Playwright E2E 스펙을 `devloop/tests/e2e/` 에 추가한다.",
    "4. TS 변경 시 타입체크로 회귀가 없는지 확인한다.",
    "5. 무엇을·왜 개선했고 어떤 테스트를 추가했는지 3~5줄로 요약한다.",
    "",
    ADVANCE_GUARDRAILS,
  ].join("\n");
}

export function advance(featureIndex: number, config: LoopConfig): ClaudeResult {
  return callClaude(buildAdvancePrompt(featureIndex), config);
}
