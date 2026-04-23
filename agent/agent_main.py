"""ohdo Agent — 트레이 아이콘 + 헬스체크 ping 루프.

M0 범위: 백그라운드 스레드가 30초마다 ``OHDO_SERVER_URL/healthz`` 를 호출하고
결과를 ``%APPDATA%/ohdo/agent.log`` 에 기록한다. 트레이 메뉴에서 로그 폴더
열기 / 종료 가능.

로컬 실행:
    python agent_main.py

환경변수:
    OHDO_SERVER_URL   — 서버 URL. 기본 http://localhost:8000
    OHDO_PING_SECONDS — ping 주기(초). 기본 30
    OHDO_APPDATA      — 로그/설정 폴더. 기본 %APPDATA%/ohdo 또는 ~/.ohdo
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx
from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem

# agent_main.py 는 스크립트로 직접 실행되기도 하고 (``python agent_main.py``)
# PyInstaller 번들의 엔트리포인트로 실행되기도 한다. 두 경우 모두 `auth.py` 는
# 같은 폴더의 sibling 으로 존재하므로 sibling import 를 우선 시도하고, 혹시
# 패키지 컨텍스트 (``python -m agent.agent_main``) 로 실행되면 패키지 경로로도
# 찾는다. 이 이중 시도는 M0 의 ``from agent import __version__`` 실패 교훈을
# 반영한 것.
try:
    import auth as agent_auth  # type: ignore[no-redef]
    import ws_client as agent_ws  # type: ignore[no-redef]
except ImportError:  # pragma: no cover
    from agent import auth as agent_auth  # type: ignore[no-redef]
    from agent import ws_client as agent_ws  # type: ignore[no-redef]

# agent/ 폴더 안에서 스크립트로 직접 실행되는 경로와 PyInstaller 번들 모두를
# 지원하기 위해 버전은 이 파일 안에 둔다. agent/__init__.py 와 동기화 유지.
__version__ = "0.0.1"

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────

# 기본값은 Railway 에 배포된 Control Plane. 설치된 agent 가 추가 설정 없이도
# 클라우드와 통신하도록 하기 위함. 로컬 개발 시에는 OHDO_SERVER_URL 환경변수로
# 오버라이드. M1 Device Flow 는 %APPDATA%/ohdo/config.json 에 값을 쓴다.
DEFAULT_SERVER_URL = "https://ohdo-production.up.railway.app"
DEFAULT_PING_SECONDS = 30


def _resolve_appdata_dir() -> Path:
    """로그·설정 폴더 경로. Windows 는 %APPDATA%/ohdo, 그 외는 ~/.ohdo."""
    override = os.getenv("OHDO_APPDATA")
    if override:
        return Path(override)

    if sys.platform == "win32":
        base = os.getenv("APPDATA")
        if base:
            return Path(base) / "ohdo"

    return Path.home() / ".ohdo"


APPDATA_DIR: Path = _resolve_appdata_dir()
LOG_FILE: Path = APPDATA_DIR / "agent.log"
CONFIG_FILE: Path = APPDATA_DIR / "config.json"


def _load_config() -> dict:
    """``%APPDATA%/ohdo/config.json`` 을 읽어 dict 반환. 없으면 빈 dict."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def resolve_server_url() -> str:
    """서버 URL 해석 우선순위: 환경변수 > config.json > 기본값."""
    if env_url := os.getenv("OHDO_SERVER_URL"):
        return env_url
    cfg = _load_config()
    if url := cfg.get("server_url"):
        return str(url)
    return DEFAULT_SERVER_URL


# ──────────────────────────────────────────────
# 로깅
# ──────────────────────────────────────────────

def _setup_logging() -> logging.Logger:
    APPDATA_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("ohdo.agent")
    logger.setLevel(logging.INFO)
    # 중복 핸들러 방지 (핫리로드 등)
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    # 콘솔에도 출력 (개발 중 편의)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    return logger


log = _setup_logging()


# ──────────────────────────────────────────────
# 헬스체크 ping 루프
# ──────────────────────────────────────────────

class HealthPinger:
    """서버 헬스체크를 주기적으로 호출하는 백그라운드 워커.

    M1.4 부터는 ``AuthState`` 의 현재 credentials 를 매 tick 마다 조회해:
    - 로그인 상태 (+ 발급받은 서버가 현재 ping 대상과 일치) 면
      ``GET /v0/agents/me`` 를 ``Authorization: Bearer`` 헤더와 함께 호출.
      401 수신 시 ``on_unauthorized`` 콜백을 1회 호출하고 다음 tick 부터는
      자동으로 익명 폴백.
    - 로그인 안 됐거나 서버 mismatch 면 기존 ``GET /healthz`` 호출.
    """

    def __init__(
        self,
        server_url: str,
        interval_seconds: int,
        auth_state: AuthState | None = None,
        on_unauthorized=None,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.interval = max(5, interval_seconds)
        self.auth_state = auth_state
        # 401 수신 시 호출되는 side-effect 콜백. icon 이 생성된 뒤 세팅하는 경우가
        # 있어 생성자 인자 대신 속성으로 나중에 갱신 가능.
        self.on_unauthorized = on_unauthorized
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._loop, name="ohdo-ping", daemon=True
        )
        self._thread.start()
        log.info("pinger started: url=%s interval=%ss", self.server_url, self.interval)

    def stop(self) -> None:
        self._stop.set()
        log.info("pinger stop requested")

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._ping_once()
            # 인터럽트 가능한 sleep
            self._stop.wait(self.interval)

    def _pick_route(self):
        """이번 tick 에 쓸 URL·헤더·타입 라벨을 결정.

        Returns (url, headers, mode) where mode is 'authenticated' | 'anonymous'.
        """
        if self.auth_state is not None:
            creds = self.auth_state.credentials
            if creds is not None and creds.token_server_url.rstrip("/") == self.server_url:
                return (
                    f"{self.server_url}/v0/agents/me",
                    {"Authorization": f"Bearer {creds.agent_token}"},
                    "authenticated",
                )
        return (f"{self.server_url}/healthz", {}, "anonymous")

    def _ping_once(self) -> None:
        url, headers, mode = self._pick_route()
        started = time.monotonic()
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, headers=headers)
            elapsed_ms = int((time.monotonic() - started) * 1000)

            if resp.status_code == 200:
                log.info(
                    "ping ok (%s): %s status=200 elapsed=%dms body=%s",
                    mode, url, elapsed_ms, resp.text[:200],
                )
                return

            if resp.status_code == 401 and mode == "authenticated":
                # 토큰이 revoke 되었거나 DB 에서 사라짐.
                err = None
                try:
                    err = resp.json().get("detail", {}).get("error")
                except ValueError:
                    pass
                log.warning(
                    "authenticated ping got 401 error=%r — clearing credentials",
                    err,
                )
                if callable(self.on_unauthorized):
                    try:
                        self.on_unauthorized()
                    except Exception as cb_exc:  # pragma: no cover
                        log.error("on_unauthorized callback raised: %s", cb_exc)
                return

            log.warning(
                "ping non-200 (%s): %s status=%d elapsed=%dms",
                mode, url, resp.status_code, elapsed_ms,
            )
        except httpx.RequestError as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            log.error(
                "ping failed (%s): %s elapsed=%dms error=%s",
                mode, url, elapsed_ms, exc,
            )


# ──────────────────────────────────────────────
# 트레이 아이콘
# ──────────────────────────────────────────────

def _make_icon_image() -> Image.Image:
    """외부 파일 의존 없이 16색 톤의 트레이 아이콘을 만든다."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 진한 파란 배경 원
    draw.ellipse((4, 4, size - 4, size - 4), fill=(20, 80, 180, 255))

    # 중앙에 "O" 글자를 흉내 낸 흰 링
    draw.ellipse((18, 18, size - 18, size - 18), outline=(255, 255, 255, 255), width=5)

    return img


def _open_log_folder(_icon: Icon, _item: MenuItem) -> None:
    log.info("menu: open log folder %s", APPDATA_DIR)
    try:
        if sys.platform == "win32":
            os.startfile(str(APPDATA_DIR))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{APPDATA_DIR}"')
        else:
            os.system(f'xdg-open "{APPDATA_DIR}"')
    except Exception as exc:  # pragma: no cover — 플랫폼 의존
        log.error("failed to open folder: %s", exc)


def _reload_config(_icon: Icon, _item: MenuItem) -> None:
    """M0 는 스텁. M1 에서 토큰·서버URL 재로드 구현."""
    log.info("menu: reload config (M0 stub)")


def _quit(
    icon: Icon,
    _item: MenuItem,
    auth: AuthState,
    pinger: HealthPinger,
    ws_client: "agent_ws.WebSocketClient | None" = None,
) -> None:
    log.info("menu: quit requested")
    auth.cancel_polling()
    if ws_client is not None:
        ws_client.stop()
    pinger.stop()
    icon.stop()


# ──────────────────────────────────────────────
# 인증 상태 + Sign In/Out 핸들러 (M1.3)
# ──────────────────────────────────────────────

def _collect_agent_metadata() -> dict:
    """Device Flow 요청에 실어 보낼 부가 정보."""
    try:
        hostname = socket.gethostname()
    except OSError:
        hostname = "unknown"
    return {
        "agent_name": hostname,
        "hostname": hostname,
        "platform": sys.platform,  # win32 / darwin / linux
        "agent_version": __version__,
    }


class AuthState:
    """트레이에서 공유되는 인증 상태. 로그인/로그아웃/폴링을 관장."""

    def __init__(self, server_url: str) -> None:
        self._lock = threading.Lock()
        self.server_url = server_url.rstrip("/")
        self._creds: agent_auth.Credentials | None = agent_auth.load_credentials(CONFIG_FILE)
        self._stop_event: threading.Event | None = None
        self._polling_thread: threading.Thread | None = None

    # ── 읽기 ──
    @property
    def credentials(self) -> agent_auth.Credentials | None:
        with self._lock:
            return self._creds

    def is_signed_in(self) -> bool:
        with self._lock:
            return self._creds is not None

    def is_polling(self) -> bool:
        with self._lock:
            return self._polling_thread is not None and self._polling_thread.is_alive()

    def sign_in_label(self) -> str:
        if self.is_polling():
            return "Sign In (waiting for browser...)"
        return "Sign In"

    def sign_out_label(self) -> str:
        creds = self.credentials
        if creds is None:
            return "Sign Out"
        short_uid = creds.user_id.split("-", 1)[0]
        return f"Sign Out ({short_uid}...)"

    # ── 쓰기 ──
    def cancel_polling(self) -> None:
        with self._lock:
            if self._stop_event is not None:
                self._stop_event.set()

    def _set_creds(self, creds: agent_auth.Credentials | None) -> None:
        with self._lock:
            self._creds = creds

    def _set_polling(
        self, thread: threading.Thread | None, stop: threading.Event | None
    ) -> None:
        with self._lock:
            self._polling_thread = thread
            self._stop_event = stop

    def begin_sign_in(self, icon: Icon) -> None:
        """Sign In 클릭 핸들러. 별도 스레드에서 Device Flow 실행."""
        if self.is_signed_in():
            log.info("sign in requested but already signed in — ignoring")
            return
        if self.is_polling():
            log.info("sign in already in progress — ignoring")
            return

        stop = threading.Event()
        thread = threading.Thread(
            target=self._run_device_flow,
            args=(icon, stop),
            name="ohdo-device-flow",
            daemon=True,
        )
        self._set_polling(thread, stop)
        thread.start()
        icon.update_menu()

    def sign_out(self, icon: Icon) -> None:
        """Sign Out — config.json 의 인증 키만 제거."""
        self.cancel_polling()
        agent_auth.clear_credentials(CONFIG_FILE)
        self._set_creds(None)
        log.info("signed out")
        _safe_notify(icon, "Signed out", "ohdo agent")
        icon.update_menu()

    def handle_unauthorized(self, icon: Icon) -> None:
        """Pinger 가 401 을 받았을 때 호출. credentials 만 제거하고 anonymous 폴백.

        Sign Out 과 달리 사용자 액션이 아니라 서버측 revoke 추정이므로 별도 로그
        키워드와 메시지를 쓴다. 폴링 중이면 중단. 반복 호출되어도 idempotent.
        """
        if not self.is_signed_in():
            return
        self.cancel_polling()
        agent_auth.clear_credentials(CONFIG_FILE)
        self._set_creds(None)
        log.warning("session expired: credentials cleared due to 401")
        _safe_notify(
            icon,
            "Session expired — please Sign In again",
            "ohdo agent",
        )
        icon.update_menu()

    def _run_device_flow(self, icon: Icon, stop: threading.Event) -> None:
        meta = _collect_agent_metadata()
        log.info("device flow: begin against %s", self.server_url)
        try:
            info = agent_auth.start_device_flow(self.server_url, **meta)
        except agent_auth.DeviceFlowError as exc:
            log.error("device flow start failed: %s", exc)
            _safe_notify(icon, f"Sign In failed: {exc}", "ohdo agent")
            self._set_polling(None, None)
            icon.update_menu()
            return

        _safe_notify(
            icon,
            f"Browser opening — enter code {info.user_code} if prompted",
            "ohdo agent — Sign In",
        )

        try:
            webbrowser.open(info.verification_uri_complete, new=2)
        except Exception as exc:  # pragma: no cover — 플랫폼 의존
            log.warning("webbrowser.open failed: %s — user must open URL manually", exc)

        try:
            creds = agent_auth.poll_for_token(
                self.server_url,
                info.device_code,
                interval=info.interval,
                expires_in=info.expires_in,
                stop_event=stop,
            )
        except agent_auth.DeviceFlowCancelled:
            log.info("device flow cancelled")
            self._set_polling(None, None)
            icon.update_menu()
            return
        except agent_auth.DeviceFlowExpired:
            log.warning("device flow expired")
            _safe_notify(icon, "Sign In expired — try again", "ohdo agent")
            self._set_polling(None, None)
            icon.update_menu()
            return
        except agent_auth.DeviceFlowDenied:
            log.warning("device flow denied")
            _safe_notify(icon, "Sign In denied", "ohdo agent")
            self._set_polling(None, None)
            icon.update_menu()
            return
        except agent_auth.DeviceFlowError as exc:
            log.error("device flow failed: %s", exc)
            _safe_notify(icon, f"Sign In failed: {exc}", "ohdo agent")
            self._set_polling(None, None)
            icon.update_menu()
            return

        try:
            agent_auth.save_credentials(CONFIG_FILE, creds)
        except OSError as exc:
            log.error("failed to persist credentials: %s", exc)
            _safe_notify(icon, f"Could not save credentials: {exc}", "ohdo agent")
            self._set_polling(None, None)
            icon.update_menu()
            return

        self._set_creds(creds)
        self._set_polling(None, None)
        log.info(
            "signed in: agent_id=%s user_id=%s server=%s",
            creds.agent_id, creds.user_id, creds.token_server_url,
        )
        _safe_notify(
            icon,
            f"Signed in (user {creds.user_id.split('-', 1)[0]}...)",
            "ohdo agent",
        )
        icon.update_menu()


def _safe_notify(icon: Icon, message: str, title: str) -> None:
    """``icon.notify`` 를 안전하게 호출. 백엔드가 지원하지 않으면 로그만."""
    try:
        icon.notify(message, title)
    except Exception as exc:  # pragma: no cover — 플랫폼 의존
        log.debug("icon.notify unavailable: %s (message=%s)", exc, message)


# ──────────────────────────────────────────────
# 엔트리포인트
# ──────────────────────────────────────────────

def main() -> int:
    server_url = resolve_server_url()
    ping_seconds = int(os.getenv("OHDO_PING_SECONDS", str(DEFAULT_PING_SECONDS)))

    log.info(
        "ohdo agent starting: version=%s server=%s appdata=%s",
        __version__, server_url, APPDATA_DIR,
    )

    auth = AuthState(server_url=server_url)
    if auth.is_signed_in():
        creds = auth.credentials
        assert creds is not None
        log.info(
            "credentials loaded: agent_id=%s user_id=%s signed_in_at=%s",
            creds.agent_id, creds.user_id, creds.signed_in_at,
        )
    else:
        log.warning("no credentials found — Sign In required")

    pinger = HealthPinger(
        server_url=server_url,
        interval_seconds=ping_seconds,
        auth_state=auth,
    )
    # on_unauthorized 는 icon 이 필요한데 아직 생성 전이므로 아래에서 세팅.

    ws_client = agent_ws.WebSocketClient(
        server_url=server_url,
        auth_state=auth,
    )
    # on_unauthorized 도 icon 필요 → 아래에서 세팅.

    menu = Menu(
        MenuItem(f"ohdo agent v{__version__}", None, enabled=False),
        MenuItem(f"server: {server_url}", None, enabled=False),
        Menu.SEPARATOR,
        MenuItem(
            lambda _: auth.sign_in_label(),
            lambda icon, _item: auth.begin_sign_in(icon),
            enabled=lambda _: not auth.is_signed_in() and not auth.is_polling(),
        ),
        MenuItem(
            lambda _: auth.sign_out_label(),
            lambda icon, _item: auth.sign_out(icon),
            enabled=lambda _: auth.is_signed_in(),
        ),
        Menu.SEPARATOR,
        MenuItem("Open Log Folder", _open_log_folder),
        MenuItem("Reload Config", _reload_config),
        Menu.SEPARATOR,
        MenuItem("Quit", lambda icon, item: _quit(icon, item, auth, pinger, ws_client)),
    )

    icon = Icon(
        name="ohdo-agent",
        icon=_make_icon_image(),
        title=f"ohdo agent v{__version__}",
        menu=menu,
    )

    # icon 이 생성된 시점에 비로소 401 콜백을 연결하고 pinger/ws 를 띄운다.
    pinger.on_unauthorized = lambda: auth.handle_unauthorized(icon)
    pinger.start()

    ws_client.on_unauthorized = lambda: auth.handle_unauthorized(icon)
    ws_client.start()

    def _on_ready(icon: Icon) -> None:
        icon.visible = True
        if not auth.is_signed_in():
            _safe_notify(
                icon,
                "Right-click the tray icon and choose Sign In",
                "ohdo agent — Sign In required",
            )

    try:
        icon.run(setup=_on_ready)
    finally:
        auth.cancel_polling()
        ws_client.stop()
        pinger.stop()
        log.info("ohdo agent stopped at %s", datetime.now(timezone.utc).isoformat())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
