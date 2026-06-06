# SPDX-License-Identifier: AGPL-3.0-or-later
"""브라우저 NL 시나리오 — 자연어로 Selenium 자동화 생성→실행→결과 검증(picker 없음).

로컬 HTML(browser_test.html)을 Chrome 으로 열고, 입력창에 텍스트 입력, 전송 클릭,
결과 영역(#out) 출력. 마지막 step 의 실행 출력에 기대 문자열이 있으면 성공.
AppService 직접 사용(Electron/Playwright 불필요)."""

from __future__ import annotations

import asyncio
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
DATA = os.path.join(REPO, "data")
HTML = os.path.join(REPO, "devloop", "scenarios", "browser_test.html").replace("\\", "/")
URL = "file:///" + HTML
TEXT = "ohdo자동화"
EXPECT = f"입력값: {TEXT}"

STEPS = [
    f"Chrome 브라우저로 {URL} 페이지를 열어줘",
    f"페이지의 입력창에 '{TEXT}' 라고 입력해줘",
    "'전송' 버튼을 클릭해줘",
    "id 가 out 인 결과 영역의 텍스트를 print 로 출력해줘",
]


def main() -> int:
    from core.app_service import AppService
    from core.prompt_builder import PromptBuilder

    settings = json.load(open(os.path.join(REPO, "config", "settings.json"), encoding="utf-8"))
    prompts = json.load(open(os.path.join(REPO, "config", "prompts.json"), encoding="utf-8"))
    svc = AppService.create_default(data_dir=DATA, settings=settings)
    if settings.get("ai"):
        svc.reload_ai(settings)
    pb = PromptBuilder(prompts)

    session = svc.create_session(title="browser NL 검증", project_type="browser")
    print(f"세션 {session.session_id[:8]}  URL={URL}", flush=True)

    outputs: list[str] = []

    async def go():
        for i, req in enumerate(STEPS, 1):
            print(f"[GEN {i}] {req}", flush=True)
            step, resp = await svc.generate_step(session, req, prompt_builder=pb)
            if not resp.success:
                print(f"  ❌ 생성 실패: {getattr(resp, 'error', None)}", flush=True)
                return
            code = (
                step.get("generated_code", "")
                if isinstance(step, dict)
                else getattr(step, "generated_code", "")
            )
            if i == 1:
                print(
                    f"  selenium 사용: {'selenium' in code.lower() or 'webdriver' in code.lower()}",
                    flush=True,
                )

        s2 = svc.get_session(session.session_id)
        kernel = svc.create_kernel()
        kernel.start()
        try:
            kernel.push_secrets()
        except Exception:
            pass
        print("\n전체 실행…", flush=True)
        report = await svc.run_blocks(
            session=s2,
            kernel=kernel,
            on_step_start=lambda s: print(f"[START] {s}", flush=True),
            on_step_complete=lambda s, r: (
                outputs.append(str(getattr(r, "output", "") or "")),
                print(
                    f"[DONE] {s}: success={getattr(r, 'success', None)} {str(getattr(r, 'output', ''))[:120]}",
                    flush=True,
                ),
            )[-1],
            on_log=lambda m: None,
        )
        print(f"[REPORT] {report.successful_steps}/{report.total_steps}", flush=True)

    asyncio.run(go())

    joined = "\n".join(outputs)
    ok = EXPECT in joined
    print(f"\n=== 🎯 결과 '{EXPECT}' 출력 확인: {'✅' if ok else '❌'} ===", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
