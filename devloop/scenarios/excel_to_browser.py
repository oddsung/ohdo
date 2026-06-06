# SPDX-License-Identifier: AGPL-3.0-or-later
"""제품 시나리오 — 엑셀 데이터를 웹 폼에 하나씩 입력 (NL, picker 없음).

실제 사용자가 ohdo 채팅으로 단계별 대화하며 자동화를 만드는 흐름을 그대로 재현:
  1) 엑셀 실행 + 데이터 파일 열기
  2) A열 값 전부 읽기
  3) 크롬으로 로컬 웹 폼 열기 (Selenium)
  4) 읽은 값을 하나씩 입력창에 입력 + 전송 반복
  5) 결과 목록(#out) 텍스트 출력 (검증용)

agy 가 단계별 Python 생성 → run_blocks 로 실제 실행(엑셀/크롬 구동) →
**실산출물(#out 에 모든 값 누적)** 으로 성공 판정 (step.status/success 불신 — devloop #6b).
AppService 직접 사용(Electron/Playwright 불필요). project_type="auto" 로 데스크톱+브라우저 혼용 허용.
"""

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
XLSX = os.path.join(REPO, "devloop", "scenarios", "excel_data.xlsx")
HTML = os.path.join(REPO, "devloop", "scenarios", "excel_web_form.html").replace("\\", "/")
URL = "file:///" + HTML
EXPECT = ["Alice", "Bob", "Carol"]  # excel_data.xlsx A1:A3

STEPS = [
    f"엑셀을 실행해서 '{XLSX}' 파일을 열어줘",
    "방금 연 엑셀의 A열에 있는 값들을 위에서부터 전부 읽어서 파이썬 리스트로 만들어줘",
    f"크롬 브라우저로 '{URL}' 페이지를 열어줘",
    "엑셀에서 읽은 값들을 하나씩 입력창(placeholder '값을 입력하세요')에 입력하고 '전송' 버튼을 클릭하는 걸 값마다 반복해줘",
    "id 가 out 인 결과 목록의 텍스트를 print 로 출력해줘",
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

    # 데스크톱(엑셀)+브라우저(Selenium) 혼용 — project_type="auto" 가 둘 다 허용 가이드 발동.
    session = svc.create_session(title="엑셀→웹폼 NL 검증", project_type="auto")
    print(f"세션 {session.session_id[:8]}  XLSX={os.path.basename(XLSX)}  URL={URL}", flush=True)

    outputs: list[str] = []

    async def go():
        for i, req in enumerate(STEPS, 1):
            print(f"\n[GEN {i}/{len(STEPS)}] {req}", flush=True)
            step, resp = await svc.generate_step(session, req, prompt_builder=pb)
            if not resp.success:
                print(f"  ❌ 생성 실패: {getattr(resp, 'error', None)}", flush=True)
                return
            code = (
                step.get("generated_code", "")
                if isinstance(step, dict)
                else getattr(step, "generated_code", "")
            )
            low = code.lower()
            # 단계별 codegen 라우팅 관찰 (Excel: openpyxl/win32com, 브라우저: selenium)
            tags = []
            for lib in ("openpyxl", "win32com", "selenium", "webdriver", "pywinauto", "pyautogui"):
                if lib in low:
                    tags.append(lib)
            print(f"  코드 {len(code)}자 · 라이브러리: {', '.join(tags) or '?'}", flush=True)

        s2 = svc.get_session(session.session_id)
        kernel = svc.create_kernel()
        kernel.start()
        try:
            kernel.push_secrets()
        except Exception:
            pass
        print("\n전체 실행…", flush=True)

        def _done(s, r):
            out = str(getattr(r, "output", "") or "")
            outputs.append(out)
            err = str(getattr(r, "error", "") or "")
            print(
                f"[DONE] step{s}: success={getattr(r, 'success', None)} "
                f"out={out[:120]!r}{(' ERR=' + err[:160]) if err else ''}",
                flush=True,
            )

        report = await svc.run_blocks(
            session=s2,
            kernel=kernel,
            on_step_start=lambda s: print(f"[START] step{s}", flush=True),
            on_step_complete=_done,
            on_log=lambda m: None,
        )
        print(f"\n[REPORT] {report.successful_steps}/{report.total_steps} 성공", flush=True)

    asyncio.run(go())

    # 실산출물 검증 — #out 출력 텍스트에 Excel 값이 모두 누적됐는지.
    joined = "\n".join(outputs)
    found = [v for v in EXPECT if v in joined]
    ok = len(found) == len(EXPECT)
    print(
        f"\n=== 🎯 웹폼 입력 검증: {len(found)}/{len(EXPECT)} "
        f"({', '.join(found) or '없음'}) {'✅' if ok else '❌'} ===",
        flush=True,
    )
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
