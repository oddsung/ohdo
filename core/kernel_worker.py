# SPDX-License-Identifier: AGPL-3.0-or-later
"""
커널 워커 - 영속적 Python 실행 환경

이 스크립트는 서브프로세스로 실행되어 stdin으로 코드 블럭을 수신하고
동일한 Python 네임스페이스에서 exec()으로 실행합니다.
Jupyter 커널과 유사하게 변수 상태(driver, app 등)를 세션 내내 유지합니다.

IPC 프로토콜:
  stdin  → [코드 라인들]\n<<<EXECUTE_END>>>\n
  stdout ← <<<SUCCESS>>>\n[출력]\n<<<DONE>>>\n  (성공 시)
         ← <<<ERROR>>>\n[출력+트레이스백]\n<<<DONE>>>\n  (실패 시)

  ping/pong 헬스체크:
  stdin  → <<<PING>>>\n<<<EXECUTE_END>>>\n
  stdout ← <<<PONG>>>\n<<<DONE>>>\n

  시크릿 hot reload (ADR 0003 Phase 2-c PR-6):
  stdin  → <<<SET_SECRETS>>>\n{"label1": "value1", ...}\n<<<EXECUTE_END>>>\n
  stdout ← <<<SECRETS_OK>>>\n<<<DONE>>>\n
  → os.environ 의 OHDO_SECRET_* 모두 제거 후 payload 의 label/value 로 재구성.
"""

import contextlib
import io
import json
import os
import sys
import traceback

# IPC 프로토콜 센티넬
SENTINEL_END = "<<<EXECUTE_END>>>"
RESULT_SUCCESS = "<<<SUCCESS>>>"
RESULT_ERROR = "<<<ERROR>>>"
RESULT_DONE = "<<<DONE>>>"
PING_CMD = "<<<PING>>>"
PONG_RESP = "<<<PONG>>>"
SET_SECRETS_CMD = "<<<SET_SECRETS>>>"
SECRETS_OK = "<<<SECRETS_OK>>>"

# 공유 실행 네임스페이스 (모든 블럭이 동일한 Python 컨텍스트를 공유)
_globals: dict = {
    "__name__": "__main__",
    "__builtins__": __builtins__,
}


# ADR 0003 Phase 2-b — get_secret() helper 를 globals 에 주입.
# AI 가 생성한 step 코드가 `pw = get_secret('gmail_pw')` 패턴으로 vault 값을
# 읽도록 — 평문이 코드 문자열에 박히지 않게 함 (system_context #21 가이드와 페어).
# ExecutionKernel.start() 가 OHDO_SECRET_<label> 환경변수로 vault 시크릿을 주입.
def _get_secret(label: str) -> str:
    """vault 에서 시크릿 값 조회. 미존재 시 명확한 안내 메시지로 RuntimeError.

    AI 생성 코드는 import 없이 ``get_secret('label')`` 호출 가능 — globals 에
    이미 주입되어 있음.
    """
    val = os.environ.get(f"OHDO_SECRET_{label}")
    if val is None:
        raise RuntimeError(
            f"secret '{label}' 미등록 — ohdo Settings → 시크릿 관리에서 등록하세요. "
            "PR-6 hot reload 로 다음 실행에 자동 반영 (kernel 재시작 불필요)."
        )
    return val


_globals["get_secret"] = _get_secret


def _run_loop():
    # UTF-8 강제 설정 (한글 출력 깨짐 방지)
    # 일부 환경 (3.6 미만, redirected stream) 에서 reconfigure 가 OSError/AttributeError
    # 던질 수 있으므로 폴백. 기능 자체는 best-effort.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, AttributeError):
            pass
    if hasattr(sys.stdin, "reconfigure"):
        try:
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, AttributeError):
            pass

    while True:
        # 코드 블럭 수신 (SENTINEL_END까지 읽기)
        lines = []
        is_ping = False
        is_set_secrets = False
        secrets_payload: str | None = None

        try:
            for raw_line in sys.stdin:
                stripped = raw_line.rstrip("\r\n")
                if stripped == SENTINEL_END:
                    break
                if stripped == PING_CMD:
                    is_ping = True
                    # PING은 즉시 PONG 응답 후 루프 재시작
                    break
                if stripped == SET_SECRETS_CMD:
                    # ADR 0003 PR-6 — hot reload. 다음 한 줄이 JSON payload,
                    # 그 다음 SENTINEL_END 까지 consume.
                    is_set_secrets = True
                    try:
                        payload_line = next(sys.stdin)
                        secrets_payload = payload_line.rstrip("\r\n")
                    except StopIteration:
                        secrets_payload = None
                    # SENTINEL_END consume (이미 다음 iteration 의 for 가 받지만
                    # break 로 빠져나가니 명시적으로 한 줄 더 읽음)
                    try:
                        _end_line = next(sys.stdin)
                        # 위 라인이 SENTINEL_END 가 아니면 protocol 오류 — 무시
                    except StopIteration:
                        pass
                    break
                lines.append(raw_line)
        except EOFError:
            # stdin이 닫히면 프로세스 종료
            break

        if is_ping:
            sys.stdout.write("\n" + PONG_RESP + "\n" + RESULT_DONE + "\n")
            sys.stdout.flush()
            continue

        if is_set_secrets:
            try:
                data = json.loads(secrets_payload) if secrets_payload else {}
                # 기존 OHDO_SECRET_* 모두 제거 후 payload 로 재구성 — vault 와 env
                # 가 항상 1:1 동기화. 사용자가 vault 에서 삭제한 시크릿이 env 에
                # 잔존하지 않도록.
                for k in list(os.environ):
                    if k.startswith("OHDO_SECRET_"):
                        del os.environ[k]
                for label, value in data.items():
                    os.environ[f"OHDO_SECRET_{label}"] = str(value)
                sys.stdout.write("\n" + SECRETS_OK + "\n" + RESULT_DONE + "\n")
            except Exception as exc:
                sys.stdout.write("\n" + RESULT_ERROR + "\n")
                sys.stdout.write(f"SET_SECRETS 실패: {exc}\n")
                sys.stdout.write(RESULT_DONE + "\n")
            sys.stdout.flush()
            continue

        code = "".join(lines)
        if not code.strip():
            sys.stdout.write("\n" + RESULT_SUCCESS + "\n" + RESULT_DONE + "\n")
            sys.stdout.flush()
            continue

        # stdout/stderr 캡처하여 exec 실행
        captured_out = io.StringIO()
        captured_err = io.StringIO()

        try:
            with contextlib.redirect_stdout(captured_out), contextlib.redirect_stderr(captured_err):
                compiled = compile(code, "<kernel_block>", "exec")
                exec(compiled, _globals)  # noqa: S102

            out = captured_out.getvalue()
            err = captured_err.getvalue()
            combined = out
            if err:
                combined += ("\n" if combined else "") + err
            combined = combined.rstrip()

            # 마커 라인 분리 보장: exec() 안 subprocess (cmd.exe 등) 가 trailing
            # newline 없이 fd 1 에 직접 쓰면, RESULT 마커가 그 partial line 과
            # 합쳐져 parent (execution_kernel) 의 literal 비교가 fail → success
            # 오보고. 항상 "\n" prefix 로 새 라인 보장.
            sys.stdout.write("\n" + RESULT_SUCCESS + "\n")
            if combined:
                sys.stdout.write(combined + "\n")
            sys.stdout.write(RESULT_DONE + "\n")

        except Exception:
            out = captured_out.getvalue()
            err_trace = traceback.format_exc()
            combined_out = out.rstrip()

            sys.stdout.write("\n" + RESULT_ERROR + "\n")
            if combined_out:
                sys.stdout.write(combined_out + "\n")
            sys.stdout.write(err_trace.rstrip() + "\n")
            sys.stdout.write(RESULT_DONE + "\n")

        # Win11 ForegroundLock 우회: step 코드가 pyautogui 등으로 SendInput 을
        # 호출했으면 Windows 가 SetForegroundWindow 권한을 이 subprocess 에 부여.
        # 이후 ohdo (parent) 의 raise/activate 시도가 거부되어 taskbar flash 만
        # 발생. AllowSetForegroundWindow 로 명시적 양도 — ohdo 의 다음 1회 통과.
        # 환경변수 OHDO_PARENT_PID 가 없거나 Windows 가 아니면 no-op (안전).
        _parent_pid = os.environ.get("OHDO_PARENT_PID")
        if _parent_pid and sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.user32.AllowSetForegroundWindow(int(_parent_pid))
            except Exception:
                pass

        sys.stdout.flush()


if __name__ == "__main__":
    _run_loop()
