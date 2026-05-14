# SPDX-License-Identifier: AGPL-3.0-or-later
"""사용자 비밀 정보 (ID/PW/API 키) vault.

[ADR 0003](../docs/saas/decisions/0003-secrets-handling.md) Phase 2-a.

설계 원칙:
  - **stateless façade** — vault 객체는 keyring/index 파일을 들고만 있고,
    호출자가 매번 set/get/delete 호출. 세션·UI 가 vault 인스턴스 1개 공유.
  - **namespace 분리** — `secret` (사용자 ID/PW/토큰) 와 `apikey` (AI 어댑터 키)
    가 같은 keyring service 안에서 prefix 로 격리. 한 vault 에서 둘 다 관리.
  - **list() 지원** — keyring 자체는 list API 없음. `data/vault_index.json` 에
    label 만 (값 X) 별도 저장. 값 손실 risk 없음 — 잃어버려도 index 만 재구축
    가능 (사용자가 옛 label 잊으면 manual).
  - **fail-safe** — get 은 미존재 시 ``None`` 반환 (raise X). 호출자가 placeholder
    미해결 path 처리.

쓰는 곳:
  - PR-3 (Phase 2-b): ``AppService`` 생성자 + ``ExecutionKernel.start`` env 주입.
  - PR-4 (Phase 2-c): ui_v2 시크릿 입력 / Settings 시크릿 관리 탭.
  - Phase 2 이후: AI 어댑터의 api_key 도 같은 vault namespace="apikey" 사용
    (settings.json 평문 → vault 마이그레이션 — handoff §6 #5 해소).
"""

from __future__ import annotations

import json
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = [
    "SecretLabel",
    "SecretsVault",
    "KeyringVault",
    "VAULT_INDEX_FILENAME",
    "SERVICE_NAME",
]


# ─────────────────────────────────────────────────────────
# 식별자
# ─────────────────────────────────────────────────────────


SERVICE_NAME: str = "ohdo.ai"
"""keyring service 이름. 모든 vault 작업은 이 service 하위에 저장."""

VAULT_INDEX_FILENAME: str = "vault_index.json"
"""label 인덱스 파일명 — ``data/`` 하위에 저장. 값 X, label 목록만."""

_LABEL_PATTERN: str = r"^[a-z0-9_]{1,32}$"


@dataclass(frozen=True)
class SecretLabel:
    """vault 안의 시크릿 식별자.

    label 은 `[a-z0-9_]{1,32}` 패턴 (placeholder `{{secret:<label>}}` 와 일관).
    namespace 는 ``"secret"`` (사용자) 또는 ``"apikey"`` (AI 어댑터).
    """

    label: str
    namespace: str = "secret"

    def __post_init__(self) -> None:
        import re

        if not re.match(_LABEL_PATTERN, self.label):
            raise ValueError(
                f"잘못된 label: '{self.label}' (허용 패턴 {_LABEL_PATTERN} — 소문자/숫자/_, 1~32자)"
            )
        if self.namespace not in {"secret", "apikey"}:
            raise ValueError(f"알 수 없는 namespace: '{self.namespace}' (허용: secret | apikey)")

    @property
    def keyring_key(self) -> str:
        """keyring `username` 인자로 사용할 namespace prefix 포함 키."""
        return f"{self.namespace}:{self.label}"


# ─────────────────────────────────────────────────────────
# 추상 vault
# ─────────────────────────────────────────────────────────


class SecretsVault(ABC):
    """vault 구현 추상.

    구현체:
      - ``KeyringVault`` (default) — OS keyring 기반. Phase 2.
      - ``EncryptedFileVault`` (Phase 3) — 헤드리스/CI 환경 fallback.
    """

    @abstractmethod
    def set(self, label: SecretLabel, value: str) -> None:
        """label 에 value 저장. 같은 label 존재 시 overwrite."""

    @abstractmethod
    def get(self, label: SecretLabel) -> Optional[str]:
        """미존재 시 ``None``. 절대 raise 안 함 (호출자가 미해결 path 대응)."""

    @abstractmethod
    def delete(self, label: SecretLabel) -> bool:
        """삭제 성공 시 True, 미존재 / 실패 시 False."""

    @abstractmethod
    def list(self, namespace: str = "secret") -> list[SecretLabel]:
        """등록된 label 목록 (값 X). 정렬: label 알파벳 순."""

    def get_for_env(self, labels: list[SecretLabel]) -> dict[str, str]:
        """runtime 주입용 환경변수 매핑 — D1 의 핵심 helper.

        keyring 값을 환경변수 ``OHDO_SECRET_<label>`` 형식으로 변환.
        미존재 label 은 skip (warning log). 호출자 (ExecutionKernel.start) 가
        subprocess env 에 merge.
        """
        env: dict[str, str] = {}
        for lab in labels:
            val = self.get(lab)
            if val is None:
                logger.warning(
                    "secrets.get_for_env: label '%s' (namespace=%s) 미존재 — skip",
                    lab.label,
                    lab.namespace,
                )
                continue
            env[f"OHDO_SECRET_{lab.label}"] = val
        return env


# ─────────────────────────────────────────────────────────
# Keyring 기반 구현 (default)
# ─────────────────────────────────────────────────────────


@dataclass
class _VaultIndex:
    """label 인덱스 — keyring 이 list API 없어 별도 저장.

    형식:
        {"secret": ["gmail_pw", "github_pat_token"], "apikey": ["openai"]}
    """

    secret: list[str] = field(default_factory=list)
    apikey: list[str] = field(default_factory=list)

    def add(self, namespace: str, label: str) -> None:
        bucket = getattr(self, namespace)
        if label not in bucket:
            bucket.append(label)
            bucket.sort()

    def remove(self, namespace: str, label: str) -> bool:
        bucket = getattr(self, namespace)
        if label in bucket:
            bucket.remove(label)
            return True
        return False

    def labels(self, namespace: str) -> list[str]:
        return list(getattr(self, namespace))

    def to_json(self) -> dict[str, list[str]]:
        return {"secret": list(self.secret), "apikey": list(self.apikey)}

    @classmethod
    def from_json(cls, data: dict[str, list[str]]) -> "_VaultIndex":
        return cls(
            secret=list(data.get("secret") or []),
            apikey=list(data.get("apikey") or []),
        )


class KeyringVault(SecretsVault):
    """OS keyring 기반 vault.

    - **Windows**: Credential Manager (WinVaultKeyring)
    - **macOS**: Keychain (macOS Keyring)
    - **Linux**: Secret Service / KWallet (D-Bus 필요)

    keyring 자체는 list API 없어 ``data/vault_index.json`` 에 label 만 별도 저장.
    값은 항상 keyring 안 (인덱스 파일에 평문 값 X).

    Thread-safety:
      keyring 호출은 보통 thread-safe (OS API 위임). 인덱스 파일 I/O 는 `Lock`
      으로 보호.
    """

    def __init__(
        self,
        index_path: Optional[Path] = None,
        *,
        service_name: str = SERVICE_NAME,
    ) -> None:
        # keyring fail-fast — 미설치 환경에서 명확히 실패
        import keyring  # noqa: F401 — import 자체가 availability check

        self._keyring = keyring
        self._service_name = service_name

        if index_path is None:
            project_root = Path(__file__).parent.parent
            index_path = project_root / "data" / VAULT_INDEX_FILENAME
        self._index_path = index_path
        self._index_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._index = self._load_index()

    # ── 인덱스 I/O ──

    def _load_index(self) -> _VaultIndex:
        if not self._index_path.exists():
            return _VaultIndex()
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            return _VaultIndex.from_json(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "KeyringVault: 인덱스 파일 로드 실패 (%s) — 빈 인덱스로 시작. "
                "기존 시크릿은 keyring 에는 보존됨.",
                exc,
            )
            return _VaultIndex()

    def _save_index(self) -> None:
        try:
            self._index_path.write_text(
                json.dumps(self._index.to_json(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("KeyringVault: 인덱스 파일 저장 실패: %s", exc)

    # ── SecretsVault API ──

    def set(self, label: SecretLabel, value: str) -> None:
        with self._lock:
            self._keyring.set_password(self._service_name, label.keyring_key, value)
            self._index.add(label.namespace, label.label)
            self._save_index()

    def get(self, label: SecretLabel) -> Optional[str]:
        try:
            return self._keyring.get_password(self._service_name, label.keyring_key)
        except Exception as exc:
            # keyring backend 자체 실패 (D-Bus down 등) — fail-safe 로 None
            logger.warning(
                "KeyringVault.get('%s'): backend 호출 실패 — None 반환 (%s)",
                label.keyring_key,
                exc,
            )
            return None

    def delete(self, label: SecretLabel) -> bool:
        with self._lock:
            try:
                self._keyring.delete_password(self._service_name, label.keyring_key)
            except Exception as exc:
                # 이미 없는 경우 keyring 이 raise — fail-safe 로 False
                logger.debug(
                    "KeyringVault.delete('%s'): %s",
                    label.keyring_key,
                    exc,
                )
                # 인덱스만 정리해도 의미 — 어쨌든 호출 후엔 미존재 상태
                removed = self._index.remove(label.namespace, label.label)
                if removed:
                    self._save_index()
                return False
            removed = self._index.remove(label.namespace, label.label)
            if removed:
                self._save_index()
            return True

    def list(self, namespace: str = "secret") -> list[SecretLabel]:
        if namespace not in {"secret", "apikey"}:
            raise ValueError(f"알 수 없는 namespace: '{namespace}'")
        return [
            SecretLabel(label=lab, namespace=namespace) for lab in self._index.labels(namespace)
        ]
