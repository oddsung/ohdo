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

import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx
from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem

# agent/ 폴더 안에서 스크립트로 직접 실행되는 경로와 PyInstaller 번들 모두를
# 지원하기 위해 버전은 이 파일 안에 둔다. agent/__init__.py 와 동기화 유지.
__version__ = "0.0.1"

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────

DEFAULT_SERVER_URL = "http://localhost:8000"
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
    """서버 /healthz 를 주기적으로 호출하는 백그라운드 워커."""

    def __init__(self, server_url: str, interval_seconds: int) -> None:
        self.server_url = server_url.rstrip("/")
        self.interval = max(5, interval_seconds)
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

    def _ping_once(self) -> None:
        url = f"{self.server_url}/healthz"
        started = time.monotonic()
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url)
            elapsed_ms = int((time.monotonic() - started) * 1000)

            if resp.status_code == 200:
                log.info(
                    "ping ok: %s status=200 elapsed=%dms body=%s",
                    url, elapsed_ms, resp.text[:200],
                )
            else:
                log.warning(
                    "ping non-200: %s status=%d elapsed=%dms",
                    url, resp.status_code, elapsed_ms,
                )
        except httpx.RequestError as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            log.error("ping failed: %s elapsed=%dms error=%s", url, elapsed_ms, exc)


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


def _quit(icon: Icon, _item: MenuItem, pinger: HealthPinger) -> None:
    log.info("menu: quit requested")
    pinger.stop()
    icon.stop()


# ──────────────────────────────────────────────
# 엔트리포인트
# ──────────────────────────────────────────────

def main() -> int:
    server_url = os.getenv("OHDO_SERVER_URL", DEFAULT_SERVER_URL)
    ping_seconds = int(os.getenv("OHDO_PING_SECONDS", str(DEFAULT_PING_SECONDS)))

    log.info(
        "ohdo agent starting: version=%s server=%s appdata=%s",
        __version__, server_url, APPDATA_DIR,
    )

    pinger = HealthPinger(server_url=server_url, interval_seconds=ping_seconds)
    pinger.start()

    menu = Menu(
        MenuItem(f"ohdo agent v{__version__}", None, enabled=False),
        MenuItem(f"server: {server_url}", None, enabled=False),
        Menu.SEPARATOR,
        MenuItem("Open Log Folder", _open_log_folder),
        MenuItem("Reload Config", _reload_config),
        Menu.SEPARATOR,
        MenuItem("Quit", lambda icon, item: _quit(icon, item, pinger)),
    )

    icon = Icon(
        name="ohdo-agent",
        icon=_make_icon_image(),
        title=f"ohdo agent v{__version__}",
        menu=menu,
    )

    try:
        icon.run()
    finally:
        pinger.stop()
        log.info("ohdo agent stopped at %s", datetime.now(timezone.utc).isoformat())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
