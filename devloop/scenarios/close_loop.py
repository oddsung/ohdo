# SPDX-License-Identifier: AGPL-3.0-or-later
"""Save As 닫힌 루프 — step3(다른이름저장) 재생성(새 가이드) → 실행 → 파일 저장 확인.

prompts.json 가이드(#22 save_as_to_path) + 라이브러리 shim 헬퍼 반영 후, 기존 세션의
Save As step 만 재생성해 AI 가 save_as_to_path 를 쓰는지 + 실제 파일이 저장되는지 검증한다."""

from __future__ import annotations

import asyncio
import glob
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
TARGET = r"C:\Users\doosung.oh\My_Projects\ohdo\tmp\ohdo_closeloop.txt"


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

    sid = os.path.basename(glob.glob(os.path.join(DATA, "sessions", "9bf25e0c*"))[0])
    session = svc.get_session(sid)
    print(f"세션 {sid} steps={len(session.steps)}", flush=True)

    req3 = f'다른 이름으로 저장으로 "{TARGET}" 경로에 저장해줘'

    async def go():
        print("step 3 재생성(새 가이드)…", flush=True)
        step, resp = await svc.generate_step(session, req3, prompt_builder=pb, replaces_step_id=3)
        if not resp.success or step is None:
            print(f"❌ 재생성 실패: {getattr(resp, 'error', None)}", flush=True)
            return
        code = (
            step.get("generated_code", "")
            if isinstance(step, dict)
            else getattr(step, "generated_code", "")
        )
        uses_helper = "save_as_to_path" in code
        print(f"재생성 OK — save_as_to_path 사용: {uses_helper}", flush=True)
        print("--- 재생성된 step3 코드(일부) ---", flush=True)
        for ln in code.splitlines():
            if "save_as" in ln or "저장" in ln or "hotkey" in ln:
                print("  " + ln, flush=True)

        # 재실행.
        session2 = svc.get_session(sid)  # 갱신된 세션 재로드
        kernel = svc.create_kernel()
        kernel.start()
        try:
            kernel.push_secrets()
        except Exception:
            pass
        print("\n전체 실행…", flush=True)
        report = await svc.run_blocks(
            session=session2,
            kernel=kernel,
            on_step_start=lambda s: print(f"[START] {s}", flush=True),
            on_step_complete=lambda s, r: print(
                f"[DONE] {s}: success={getattr(r, 'success', None)} {str(getattr(r, 'output', ''))[:80]}",
                flush=True,
            ),
            on_log=lambda m: None,
        )
        print(f"[REPORT] success_steps={report.successful_steps}/{report.total_steps}", flush=True)

    asyncio.run(go())

    saved = os.path.exists(TARGET)
    print(f"\n=== 🎯 파일 저장됨: {'✅ ' + TARGET if saved else '❌ 없음'} ===", flush=True)
    if saved:
        print(f"내용: {open(TARGET, encoding='utf-8').read()[:80]}", flush=True)
    return 0 if saved else 2


if __name__ == "__main__":
    sys.exit(main())
