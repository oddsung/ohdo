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
"""

import sys
import io
import traceback
import contextlib

# IPC 프로토콜 센티넬
SENTINEL_END = "<<<EXECUTE_END>>>"
RESULT_SUCCESS = "<<<SUCCESS>>>"
RESULT_ERROR = "<<<ERROR>>>"
RESULT_DONE = "<<<DONE>>>"
PING_CMD = "<<<PING>>>"
PONG_RESP = "<<<PONG>>>"

# 공유 실행 네임스페이스 (모든 블럭이 동일한 Python 컨텍스트를 공유)
_globals: dict = {
    "__name__": "__main__",
    "__builtins__": __builtins__,
}


def _run_loop():
    # UTF-8 강제 설정 (한글 출력 깨짐 방지)
    # 일부 환경 (3.6 미만, redirected stream) 에서 reconfigure 가 OSError/AttributeError
    # 던질 수 있으므로 폴백. 기능 자체는 best-effort.
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (OSError, AttributeError):
            pass
    if hasattr(sys.stdin, 'reconfigure'):
        try:
            sys.stdin.reconfigure(encoding='utf-8', errors='replace')
        except (OSError, AttributeError):
            pass

    while True:
        # 코드 블럭 수신 (SENTINEL_END까지 읽기)
        lines = []
        is_ping = False

        try:
            for raw_line in sys.stdin:
                stripped = raw_line.rstrip('\r\n')
                if stripped == SENTINEL_END:
                    break
                if stripped == PING_CMD:
                    is_ping = True
                    # PING은 즉시 PONG 응답 후 루프 재시작
                    break
                lines.append(raw_line)
        except EOFError:
            # stdin이 닫히면 프로세스 종료
            break

        if is_ping:
            sys.stdout.write(PONG_RESP + "\n" + RESULT_DONE + "\n")
            sys.stdout.flush()
            continue

        code = "".join(lines)
        if not code.strip():
            sys.stdout.write(RESULT_SUCCESS + "\n" + RESULT_DONE + "\n")
            sys.stdout.flush()
            continue

        # stdout/stderr 캡처하여 exec 실행
        captured_out = io.StringIO()
        captured_err = io.StringIO()

        try:
            with contextlib.redirect_stdout(captured_out), \
                 contextlib.redirect_stderr(captured_err):
                compiled = compile(code, "<kernel_block>", "exec")
                exec(compiled, _globals)  # noqa: S102

            out = captured_out.getvalue()
            err = captured_err.getvalue()
            combined = out
            if err:
                combined += ("\n" if combined else "") + err
            combined = combined.rstrip()

            sys.stdout.write(RESULT_SUCCESS + "\n")
            if combined:
                sys.stdout.write(combined + "\n")
            sys.stdout.write(RESULT_DONE + "\n")

        except Exception:
            out = captured_out.getvalue()
            err_trace = traceback.format_exc()
            combined_out = out.rstrip()

            sys.stdout.write(RESULT_ERROR + "\n")
            if combined_out:
                sys.stdout.write(combined_out + "\n")
            sys.stdout.write(err_trace.rstrip() + "\n")
            sys.stdout.write(RESULT_DONE + "\n")

        sys.stdout.flush()


if __name__ == "__main__":
    _run_loop()