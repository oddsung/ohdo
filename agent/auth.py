"""ohdo Agent — Device Flow 클라이언트 + 자격증명(config.json) 입출력.

M1.3 범위:
- ``start_device_flow`` : POST /v0/agents/device_code 호출, 응답 파싱.
- ``poll_for_token`` : POST /v0/agents/device_token 을 interval 간격으로 반복
  호출, 승인되면 agent_token 등을 반환.
- ``load_credentials`` / ``save_credentials`` / ``clear_credentials`` :
  ``%APPDATA%/ohdo/config.json`` 에 인증 키만 읽고 쓰고 지운다. ``server_url``
  등 다른 키는 보존한다.

설계: docs/saas/architecture/05-m1.3-agent-device-flow-client.md
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("ohdo.agent.auth")


# ──────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class DeviceCodeInfo:
    """POST /v0/agents/device_code 응답."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class Credentials:
    """발급된 agent_token 과 식별자. config.json 에 그대로 저장되는 필드."""

    agent_token: str
    agent_id: str
    user_id: str
    token_server_url: str
    signed_in_at: str  # ISO8601 UTC


# ──────────────────────────────────────────────
# 에러 계층
# ──────────────────────────────────────────────

class DeviceFlowError(RuntimeError):
    """Device Flow 전용 베이스 예외."""


class DeviceFlowExpired(DeviceFlowError):
    """서버가 expired_token 으로 응답."""


class DeviceFlowDenied(DeviceFlowError):
    """서버가 access_denied 로 응답."""


class DeviceFlowInvalid(DeviceFlowError):
    """서버가 invalid_grant 로 응답 (device_code 자체가 유효하지 않거나 이미 소비됨)."""


class DeviceFlowCancelled(DeviceFlowError):
    """``stop_event`` 로 폴링이 중단되었을 때."""


class DeviceFlowNetworkError(DeviceFlowError):
    """폴링 도중 연속 네트워크 오류."""


# ──────────────────────────────────────────────
# HTTP 유틸
# ──────────────────────────────────────────────

_HTTP_TIMEOUT = 15.0
_NETWORK_FAIL_THRESHOLD = 3


def _parse_rfc8628_error(resp: httpx.Response) -> str | None:
    """RFC 8628 §3.5 ``{"error": "..."}`` 디코드. FastAPI 는
    ``{"detail": {"error": "..."}}`` 로 감싼다 — 둘 다 대응.
    """
    try:
        body = resp.json()
    except ValueError:
        return None

    if not isinstance(body, dict):
        return None

    err = body.get("error")
    if isinstance(err, str):
        return err

    detail = body.get("detail")
    if isinstance(detail, dict):
        err = detail.get("error")
        if isinstance(err, str):
            return err
    elif isinstance(detail, str):
        # FastAPI 가 detail 을 문자열로 넘긴 경우
        return detail

    return None


# ──────────────────────────────────────────────
# Device Flow 단계
# ──────────────────────────────────────────────

def start_device_flow(
    server_url: str,
    *,
    agent_name: str | None,
    hostname: str,
    platform: str,
    agent_version: str,
) -> DeviceCodeInfo:
    """Device Flow 를 시작한다. 서버가 발급한 코드들을 반환."""
    url = server_url.rstrip("/") + "/v0/agents/device_code"
    payload = {
        "agent_name": agent_name,
        "hostname": hostname,
        "platform": platform,
        "agent_version": agent_version,
    }

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.post(url, json=payload)
    except httpx.RequestError as exc:
        logger.error("start_device_flow network error: %s", exc)
        raise DeviceFlowNetworkError(str(exc)) from exc

    if resp.status_code != 200:
        logger.error(
            "start_device_flow unexpected status=%s body=%s",
            resp.status_code, resp.text[:300],
        )
        raise DeviceFlowError(
            f"device_code request failed: HTTP {resp.status_code}"
        )

    data = resp.json()
    try:
        info = DeviceCodeInfo(
            device_code=data["device_code"],
            user_code=data["user_code"],
            verification_uri=data["verification_uri"],
            verification_uri_complete=data["verification_uri_complete"],
            expires_in=int(data["expires_in"]),
            interval=int(data["interval"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.error("start_device_flow malformed response: %s body=%s", exc, data)
        raise DeviceFlowError("malformed device_code response") from exc

    logger.info(
        "device flow started: user_code=%s verification_uri=%s expires_in=%d interval=%d",
        info.user_code, info.verification_uri, info.expires_in, info.interval,
    )
    return info


def poll_for_token(
    server_url: str,
    device_code: str,
    *,
    interval: int,
    expires_in: int,
    stop_event: threading.Event | None = None,
) -> Credentials:
    """사용자가 /link 에서 승인할 때까지 주기적으로 토큰 교환 시도.

    서버가 expired_token 을 돌려줄 때까지 (또는 ``stop_event`` 가 설정될
    때까지) 계속한다. 클라이언트 쪽 추가 상한은 두지 않는다 — 서버가
    ``expires_in`` 에 맞춰 정확히 만료를 알려준다.
    """
    url = server_url.rstrip("/") + "/v0/agents/device_token"
    interval = max(1, interval)
    deadline = time.monotonic() + max(60, expires_in) + interval
    consecutive_network_errors = 0

    while True:
        if stop_event is not None and stop_event.is_set():
            logger.info("poll_for_token cancelled by stop_event")
            raise DeviceFlowCancelled("cancelled")

        if time.monotonic() > deadline:
            # 서버가 expired_token 을 아직 안 보냈지만 클라이언트 측 안전망.
            logger.warning("poll_for_token local deadline exceeded")
            raise DeviceFlowExpired("local deadline exceeded")

        try:
            with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
                resp = client.post(url, json={"device_code": device_code})
        except httpx.RequestError as exc:
            consecutive_network_errors += 1
            logger.warning(
                "poll_for_token network error #%d: %s",
                consecutive_network_errors, exc,
            )
            if consecutive_network_errors >= _NETWORK_FAIL_THRESHOLD:
                raise DeviceFlowNetworkError(str(exc)) from exc
            _interruptible_sleep(interval, stop_event)
            continue

        consecutive_network_errors = 0

        if resp.status_code == 200:
            data = resp.json()
            try:
                creds = Credentials(
                    agent_token=data["agent_token"],
                    agent_id=str(data["agent_id"]),
                    user_id=str(data["user_id"]),
                    token_server_url=server_url.rstrip("/"),
                    signed_in_at=datetime.now(timezone.utc).isoformat(),
                )
            except (KeyError, TypeError) as exc:
                logger.error(
                    "poll_for_token malformed success response: %s body=%s",
                    exc, data,
                )
                raise DeviceFlowError("malformed device_token response") from exc
            logger.info(
                "device flow success: agent_id=%s user_id=%s",
                creds.agent_id, creds.user_id,
            )
            return creds

        if resp.status_code == 400:
            err = _parse_rfc8628_error(resp)
            if err == "authorization_pending":
                logger.debug("authorization_pending — sleeping %ds", interval)
                _interruptible_sleep(interval, stop_event)
                continue
            if err == "slow_down":
                # M1.2 에선 서버가 내보내지 않지만 RFC 를 따라 interval +5 로 대응.
                interval = interval + 5
                logger.info("slow_down received — new interval=%ds", interval)
                _interruptible_sleep(interval, stop_event)
                continue
            if err == "expired_token":
                raise DeviceFlowExpired("expired_token")
            if err == "access_denied":
                raise DeviceFlowDenied("access_denied")
            if err == "invalid_grant":
                raise DeviceFlowInvalid("invalid_grant")
            logger.error(
                "poll_for_token unknown 400 error=%r body=%s",
                err, resp.text[:300],
            )
            raise DeviceFlowError(f"unknown device_token error: {err!r}")

        logger.error(
            "poll_for_token unexpected status=%s body=%s",
            resp.status_code, resp.text[:300],
        )
        raise DeviceFlowError(
            f"device_token unexpected HTTP {resp.status_code}"
        )


def _interruptible_sleep(
    seconds: float, stop_event: threading.Event | None
) -> None:
    """``stop_event`` 가 세팅되면 즉시 깨어나는 sleep."""
    if stop_event is None:
        time.sleep(seconds)
    else:
        stop_event.wait(seconds)


# ──────────────────────────────────────────────
# Credential 저장소 (%APPDATA%/ohdo/config.json)
# ──────────────────────────────────────────────

# 인증 관련 키만 모아둔다. load/clear 가 이 목록을 다룬다.
_CREDENTIAL_KEYS = (
    "agent_token",
    "agent_id",
    "user_id",
    "token_server_url",
    "signed_in_at",
)


def _read_config(config_file) -> dict:
    """config.json 을 읽어 dict 로 반환. 파싱 실패·미존재 시 빈 dict."""
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("config read failed: %s — treating as empty", exc)
        return {}

    if not isinstance(data, dict):
        logger.warning("config root is not an object — treating as empty")
        return {}
    return data


def _write_config(config_file, data: dict) -> None:
    """config.json 을 원자적으로 교체. 부모 디렉터리 자동 생성."""
    config_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = config_file.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    tmp.replace(config_file)


def load_credentials(config_file) -> Credentials | None:
    """config.json 에서 자격증명을 읽어 Credentials 로 돌려준다.

    ``agent_token`` 이 비어 있으면 ``None`` 반환. 일부 키 누락은 "로그인
    안 됨" 으로 간주.
    """
    cfg = _read_config(config_file)
    token = cfg.get("agent_token")
    if not token:
        return None

    missing = [k for k in _CREDENTIAL_KEYS if k not in cfg or not cfg.get(k)]
    if missing:
        logger.warning(
            "config has partial credentials — missing=%s, treating as signed-out",
            missing,
        )
        return None

    try:
        return Credentials(
            agent_token=str(cfg["agent_token"]),
            agent_id=str(cfg["agent_id"]),
            user_id=str(cfg["user_id"]),
            token_server_url=str(cfg["token_server_url"]),
            signed_in_at=str(cfg["signed_in_at"]),
        )
    except (KeyError, TypeError) as exc:
        logger.warning("config credential fields invalid: %s", exc)
        return None


def save_credentials(config_file, creds: Credentials) -> None:
    """자격증명을 config.json 에 merge. 다른 키 (server_url 등) 는 보존."""
    cfg = _read_config(config_file)
    cfg.update(asdict(creds))
    _write_config(config_file, cfg)
    logger.info("credentials saved: agent_id=%s user_id=%s", creds.agent_id, creds.user_id)


def clear_credentials(config_file) -> None:
    """인증 관련 키만 제거. 나머지 (server_url 등) 는 그대로 둔다."""
    cfg = _read_config(config_file)
    removed = False
    for key in _CREDENTIAL_KEYS:
        if key in cfg:
            del cfg[key]
            removed = True
    if removed:
        _write_config(config_file, cfg)
        logger.info("credentials cleared")
    else:
        logger.debug("clear_credentials: no credentials present")
