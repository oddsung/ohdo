# SPDX-License-Identifier: AGPL-3.0-or-later
"""Save As 닫힌 루프(클린) — 새 세션 3스텝 생성 → 실행 → 파일 저장 확인.

새 가이드(#22 save_as_to_path) + shim 헬퍼 반영 후, 깨끗한 세션에서:
  step1 메모장 실행 → step2 텍스트 입력 → step3 다른 이름으로 저장.
AI 가 save_as_to_path 를 생성하고 실제 파일이 저장되면 = 닫힌 루프 완성(test→fix→retest)."""

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
TARGET = r"C:\Users\doosung.oh\My_Projects\ohdo\tmp\ohdo_closeloop2.txt"
TEXT = "ohdo 닫힌루프 검증 성공"

STEPS = [
    "메모장을 실행해줘",
    f'메모장에 "{TEXT}" 라고 입력해줘',
    f'다른 이름으로 저장으로 "{TARGET}" 경로에 저장해줘',
]


def main() -> int:
    from core.app_service import AppService
    from core.prompt_builder import PromptBuilder

    if os.path.exists(TARGET):
        os.remove(TARGET)

    settings = json.load(open(os.path.join(REPO, "config", "settings.json"), encoding="utf-8"))
    prompts = json.load(open(os.path.join(REPO, "config", "prompts.json"), encoding="utf-8"))
    svc = AppService.create_default(data_dir=DATA, settings=settings)
    if settings.get("ai"):
        svc.reload_ai(settings)
    pb = PromptBuilder(prompts)

    session = svc.create_session(title="closeloop 검증", project_type="desktop")
    print(f"새 세션 {session.session_id[:8]}", flush=True)

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
            if i == 3:
                print(f"  save_as_to_path 사용: {'save_as_to_path' in code}", flush=True)

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
            on_step_complete=lambda s, r: print(
                f"[DONE] {s}: success={getattr(r, 'success', None)} {str(getattr(r, 'output', ''))[:90]}",
                flush=True,
            ),
            on_log=lambda m: None,
        )
        print(f"[REPORT] {report.successful_steps}/{report.total_steps}", flush=True)

    asyncio.run(go())

    saved = os.path.exists(TARGET)
    print(f"\n=== 🎯 파일 저장됨: {'✅ ' + TARGET if saved else '❌ 없음'} ===", flush=True)
    if saved:
        print(f"내용: {open(TARGET, encoding='utf-8').read()[:80]}", flush=True)
    return 0 if saved else 2


if __name__ == "__main__":
    sys.exit(main())
