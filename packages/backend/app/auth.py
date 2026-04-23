"""인증 관련 유틸 — 토큰/코드 생성·해싱.

- ``generate_device_code()`` / ``generate_agent_token()``:
  ``secrets.token_urlsafe(32)`` 기반 prefix 포함 opaque 토큰. 최소 192 bit
  엔트로피 → 무차별 대입 내성 충분.
- ``generate_user_code()``: 사용자가 브라우저에 입력하는 짧은 코드. 혼동
  문자 (``I``, ``O``, ``0``, ``1``) 제외한 32 문자 알파벳으로 8 자리.
- ``hash_token()``: SHA-256 hex. agent_token 은 이미 고엔트로피라 bcrypt/argon2
  불필요 (brute force 대비 목적 아님).
"""

from __future__ import annotations

import hashlib
import secrets

DEVICE_CODE_PREFIX = "dev_"
AGENT_TOKEN_PREFIX = "ag_"

# 혼동 문자(I, O, 0, 1) 제외. 대문자 + 숫자.
_USER_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_device_code() -> str:
    """Agent 가 폴링에 사용하는 opaque 토큰."""
    return DEVICE_CODE_PREFIX + secrets.token_urlsafe(32)


def generate_agent_token() -> str:
    """기기별 장기 토큰. 발급 후 서버는 해시만 보관."""
    return AGENT_TOKEN_PREFIX + secrets.token_urlsafe(32)


def generate_user_code() -> str:
    """브라우저 입력용 짧은 코드. 예: ``ABCD-EFGH``.

    8 자리, 가운데 ``-`` 삽입. 알파벳 크기 32 → 검색 공간 32^8 ≈ 1.1e12.
    """
    raw = "".join(secrets.choice(_USER_CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_user_code(raw: str) -> str:
    """사용자 입력 정규화. 공백·하이픈 제거, 대문자화 후 ``XXXX-YYYY`` 형식으로.

    잘못된 길이면 원문 반환 (조회 실패로 이어져 404/invalid 처리됨).
    """
    cleaned = "".join(ch for ch in raw.upper() if ch.isalnum())
    if len(cleaned) != 8:
        return raw.strip().upper()
    return f"{cleaned[:4]}-{cleaned[4:]}"


def hash_token(token: str) -> str:
    """SHA-256 hex. agent_token / 필요 시 device_code 해싱에 사용."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
