# SPDX-License-Identifier: AGPL-3.0-or-later
"""실행 진단 — 이미 생성된 세션의 step 들을 run_blocks 로 실제 실행하고 단계별 결과를 출력.

api_server WS 와 동일한 실행 경로(AppService.run_blocks)를 직접 호출해, 각 step 의
성공/실패/에러/출력과 최종 persist 된 status 를 보여준다. agy 생성 없이 실행만 검증.

사용: (REPO_ROOT 에서) .venv/Scripts/python.exe devloop/scenarios/exec_diag.py [세션id접두사]
"""

from __future__ import annotations

import asyncio
import glob
import json
import os
import sys

# Windows 콘솔 기본 cp949 → 한글/기호 출력 크래시 방지(UTF-8 강제).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# REPO_ROOT 를 sys.path 에 (core 임포트 가능하게) + 절대경로 기준.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
DATA_DIR = os.path.join(REPO_ROOT, "data")
CONFIG = os.path.join(REPO_ROOT, "config", "settings.json")


def main() -> int:
    prefix = sys.argv[1] if len(sys.argv) > 1 else "9bf25e0c"
    dirs = glob.glob(os.path.join(DATA_DIR, "sessions", f"{prefix}*"))
    if not dirs:
        print(f"세션 없음: {prefix}")
        return 1
    sid = os.path.basename(dirs[0])

    from core.app_service import AppService

    settings = json.load(open(CONFIG, encoding="utf-8"))
    service = AppService.create_default(data_dir=DATA_DIR, settings=settings)
    session = service.get_session(sid)
    print(f"세션 {sid} - steps {len(session.steps)}", flush=True)

    kernel = service.create_kernel()
    kernel.start()
    try:
        kernel.push_secrets()
    except Exception:
        pass

    def on_done(s, r):
        success = getattr(r, "success", None)
        err = getattr(r, "error", None)
        out = getattr(r, "output", None) or getattr(r, "stdout", None)
        print(f"[DONE] step {s}: success={success} error={err}", flush=True)
        if out:
            print(f"        output: {str(out)[:300]}", flush=True)

    async def go():
        report = await service.run_blocks(
            session=session,
            kernel=kernel,
            start_from_step_id=1,
            stop_after_step_id=None,
            on_step_start=lambda s: print(f"[START] step {s}", flush=True),
            on_step_complete=on_done,
            on_log=lambda m: print(f"[LOG] {m}", flush=True),
        )
        print(f"[REPORT] {report}", flush=True)

    asyncio.run(go())

    s2 = service.get_session(sid)
    for st in s2.steps:
        sid_ = st.get("step_id") if isinstance(st, dict) else getattr(st, "step_id", "?")
        status = st.get("status") if isinstance(st, dict) else getattr(st, "status", "?")
        print(f"[PERSISTED] step {sid_} status={status}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
