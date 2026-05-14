# SPDX-License-Identifier: AGPL-3.0-or-later
"""Windows Credential Manager 일반 자격 증명 (CRED_TYPE_GENERIC) 읽기 wrapper.

[ADR 0003](../docs/saas/decisions/0003-secrets-handling.md) Phase 2-c PR-8.

목적:
    사용자가 이미 Windows 자격 증명 관리자 (제어판 → 자격 증명 관리자 →
    Windows 자격 증명) 에 저장해 둔 로그인 정보를 ohdo vault 로 import 할 수
    있게 함. 같은 정보를 두 번 등록할 필요 없음.

설계 원칙:
  - **read-only** — Credential Manager 에 직접 set/delete 하지 않음. 가져온 값은
    ohdo 자체 vault (KeyringVault) 에 저장. 사용자의 시스템 credential 은
    그대로 둠 (실수로 덮어쓰거나 삭제할 위험 회피).
  - **type filter** — CRED_TYPE_GENERIC (1) 만 노출. RDP (CRED_TYPE_DOMAIN_PASSWORD=2)
    같은 도메인 자격 증명은 노출 X.
  - **fail-safe** — 비 Windows / win32cred 미설치 / 권한 부족 시 빈 list 반환,
    raise X.
  - **secret value 는 lazy** — list_credentials() 는 metadata 만 반환. 값은
    명시적으로 ``read_credential(target_name)`` 호출 시에만 read — UI 가 import
    확정 시점에만 평문 접근.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = [
    "WindowsCredentialMeta",
    "is_available",
    "list_credentials",
    "read_credential",
    "CRED_TYPE_GENERIC",
]


# Win32 CredentialType enum
CRED_TYPE_GENERIC = 1
CRED_TYPE_DOMAIN_PASSWORD = 2
CRED_TYPE_DOMAIN_CERTIFICATE = 3
CRED_TYPE_DOMAIN_VISIBLE_PASSWORD = 4


@dataclass(frozen=True)
class WindowsCredentialMeta:
    """단일 자격 증명 metadata — 값 제외 (lazy read).

    Attributes:
        target_name: Credential Manager 에서 보이는 이름 (예: ``git:https://github.com``)
        user_name: 사용자명. ``None`` 일 수 있음 (cookie 등)
        cred_type: ``CRED_TYPE_*`` 상수. 일반 자격 증명은 1.
        comment: optional 설명 (대부분 None).
        last_written_ts: 마지막 수정 시간 (unix epoch).
    """

    target_name: str
    user_name: Optional[str]
    cred_type: int
    comment: Optional[str] = None
    last_written_ts: float = 0.0

    def suggested_label(self) -> str:
        """vault 등록 시 기본 label 제안 — target_name 을 정규화.

        예: ``git:https://github.com`` → ``github_com`` (or ``git_github_com``)
        규칙: lowercase, 영숫자 + ``_`` 만, 32자 이하.
        """
        import re

        # 'git:https://github.com' → 'github.com' 추출 시도 (host 부분만)
        s = self.target_name
        # 가장 마지막 / 또는 = 다음 부분 (host)
        for sep in ("://", ":", "/"):
            if sep in s:
                s = s.split(sep)[-1]
        # 영숫자 + . 만 유지 → . 를 _
        s = re.sub(r"[^A-Za-z0-9_]", "_", s.lower())
        # 연속된 _ 단축 + 앞뒤 _ 제거
        s = re.sub(r"_+", "_", s).strip("_")
        # 빈 문자열이면 fallback
        if not s:
            s = "credential"
        return s[:32]


def is_available() -> bool:
    """Windows + win32cred 사용 가능 여부."""
    if sys.platform != "win32":
        return False
    try:
        import win32cred  # noqa: F401

        return True
    except ImportError:
        return False


def list_credentials(
    *,
    type_filter: Optional[int] = CRED_TYPE_GENERIC,
) -> list[WindowsCredentialMeta]:
    """일반 자격 증명 목록 (값 제외 metadata).

    Args:
        type_filter: ``CRED_TYPE_*`` 중 하나. ``None`` 이면 모든 타입 반환.
            기본은 ``CRED_TYPE_GENERIC`` (일반 자격 증명) — RDP 같은 도메인
            자격 증명은 제외.

    Returns:
        list[WindowsCredentialMeta]. 비 Windows / 권한 부족 시 빈 list.
    """
    if not is_available():
        return []

    try:
        import win32cred
    except ImportError:
        return []

    try:
        # 두 번째 인자 0 = no flags
        raw_creds = win32cred.CredEnumerate(None, 0)
    except Exception as exc:  # pywintypes.error 등
        logger.warning("CredEnumerate 실패 — 빈 list 반환: %s", exc)
        return []

    out: list[WindowsCredentialMeta] = []
    for c in raw_creds or []:
        try:
            ctype = int(c.get("Type", 0))
            if type_filter is not None and ctype != type_filter:
                continue
            target = c.get("TargetName") or ""
            if not target:
                continue
            user = c.get("UserName")
            comment = c.get("Comment")
            # LastWritten 은 pywintypes 의 FILETIME — 시도해 보고 실패 시 0
            try:
                ts = float(c.get("LastWritten").timestamp())  # type: ignore[attr-defined]
            except Exception:
                ts = 0.0
            out.append(
                WindowsCredentialMeta(
                    target_name=target,
                    user_name=user if isinstance(user, str) else None,
                    cred_type=ctype,
                    comment=comment if isinstance(comment, str) else None,
                    last_written_ts=ts,
                )
            )
        except Exception as exc:  # noqa: BLE001 — 개별 항목 실패가 전체 막지 X
            logger.debug("자격 증명 메타 파싱 실패 (skip): %s", exc)
            continue

    # target_name 알파벳 순
    out.sort(key=lambda x: x.target_name.lower())
    return out


def read_credential(target_name: str) -> Optional[str]:
    """target_name 의 자격 증명에서 평문 값 (CredentialBlob) 읽기.

    UI 가 사용자의 import 확정 시점에만 호출 — 평문이 메모리에 잠시만 머무름.

    Returns:
        평문 비밀번호 (UTF-16 LE 디코딩). 없거나 권한 없으면 ``None``.
    """
    if not is_available() or not target_name:
        return None

    try:
        import win32cred
    except ImportError:
        return None

    try:
        cred = win32cred.CredRead(target_name, CRED_TYPE_GENERIC, 0)
    except Exception as exc:
        logger.debug("CredRead('%s') 실패: %s", target_name, exc)
        return None

    blob = cred.get("CredentialBlob") if cred else None
    if blob is None:
        return None

    # CredentialBlob 은 bytes (UTF-16 LE 인코딩). pywin32 의 CredRead 가 이미
    # 디코드해 str 으로 줄 수도 있음 — 두 케이스 모두 대응.
    if isinstance(blob, str):
        return blob
    if isinstance(blob, (bytes, bytearray)):
        try:
            return blob.decode("utf-16-le", errors="replace").rstrip("\x00")
        except Exception:
            return None
    return None
