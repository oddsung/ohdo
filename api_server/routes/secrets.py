# SPDX-License-Identifier: AGPL-3.0-or-later
"""시크릿 볼트 (handoff §61, 백로그 #21) — 사용자 비밀(ID/PW/토큰) CRUD 브리지.

core ADR0003 의 ``AppService.secrets_vault`` (KeyringVault, OS keyring 기반) 를 노출한다.
core 0줄 — 공개 vault API (set/get/delete/list) 위임만. **보안: 시크릿 값은 절대 renderer
로 반환하지 않는다** (label 목록만). 값은 keyring 에만, 실행 시 kernel_worker 의 get_secret()
helper 가 ``OHDO_SECRET_<label>`` env 로 읽는다(이미 배선됨 — deps.get_kernel push_secrets).

namespace 는 "secret"(사용자 비밀)만 다룬다. "apikey"(AI 어댑터 키)는 설정 다이얼로그(§47)
가 별도 관리. vault 미가용(keyring 미설치/headless) 시 available=False 로 graceful.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api_server.deps import get_app_service, require_token

router = APIRouter()

_NAMESPACE = "secret"


class SetSecretRequest(BaseModel):
    """시크릿 등록/덮어쓰기 — label 은 [a-z0-9_]{1,32} (SecretLabel 패턴)."""

    label: str
    value: str


class ScanTextRequest(BaseModel):
    """전송 전 평문 시크릿 감지 (handoff §62, 백로그 #21b)."""

    text: str


def _vault(request: Request):
    """현재 AppService 의 secrets_vault (없으면 None)."""
    return get_app_service(request.app).secrets_vault


@router.get("/secrets")
def list_secrets(request: Request, _: None = Depends(require_token)) -> dict:
    """등록된 시크릿 label 목록 (값 X). vault 미가용 시 available=False + 빈 목록.

    ``{"available": bool, "labels": ["gmail_pw", ...]}``.
    """
    vault = _vault(request)
    if vault is None:
        return {"available": False, "labels": []}
    try:
        labels = [lab.label for lab in vault.list(namespace=_NAMESPACE)]
    except Exception as exc:  # noqa: BLE001 — backend 실패는 빈 목록으로 graceful
        return {"available": True, "labels": [], "error": str(exc)}
    return {"available": True, "labels": labels}


@router.post("/secrets")
def set_secret(
    body: SetSecretRequest, request: Request, _: None = Depends(require_token)
) -> dict:
    """시크릿 등록/덮어쓰기. label 패턴 위반 400, vault 미가용 503.

    값은 keyring 에만 저장 — 응답에 값을 포함하지 않는다.
    """
    vault = _vault(request)
    if vault is None:
        raise HTTPException(status_code=503, detail="시크릿 볼트를 사용할 수 없습니다 (keyring 미설치).")
    if not body.value:
        raise HTTPException(status_code=400, detail="값이 비어 있습니다.")

    from core.secrets import SecretLabel

    try:
        label = SecretLabel(label=body.label, namespace=_NAMESPACE)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        vault.set(label, body.value)
    except Exception as exc:  # noqa: BLE001 — keyring set 실패
        raise HTTPException(status_code=500, detail=f"시크릿 저장 실패: {exc}")
    return {"success": True, "label": body.label}


@router.post("/secrets/scan")
def scan_text(body: ScanTextRequest, _: None = Depends(require_token)) -> dict:
    """텍스트에서 평문 시크릿 후보 감지 (handoff §62, 백로그 #21b).

    core ``secrets_detector.detect`` 위임 (core 0줄). **매치 값(value)은 응답에 포함하지
    않는다** — span/kind/confidence/suggested_label + 미리보기(앞 2자 + 마스킹)만. 프런트가
    전송 전 "평문 대신 시크릿 등록" 권고에 사용. vault 무관(감지는 항상 가능).

    ``{"matches": [{"start","end","kind","confidence","suggested_label","preview"}, ...]}``.
    """
    from core.secrets_detector import detect

    try:
        found = detect(body.text or "")
    except Exception as exc:  # noqa: BLE001 — 감지 실패는 빈 결과로 graceful
        return {"matches": [], "error": str(exc)}

    matches = []
    for m in found:
        val = m.value or ""
        # 값 자체는 절대 노출하지 않음 — 길이 힌트 + 앞 2자만 미리보기.
        preview = (val[:2] + "•" * max(0, len(val) - 2)) if val else ""
        matches.append(
            {
                "start": m.span[0],
                "end": m.span[1],
                "kind": m.kind,
                "confidence": round(float(m.confidence), 3),
                "suggested_label": m.suggested_label,
                "preview": preview[:32],
            }
        )
    return {"matches": matches}


@router.delete("/secrets/{label}")
def delete_secret(label: str, request: Request, _: None = Depends(require_token)) -> dict:
    """시크릿 삭제. vault 미가용 503, label 패턴 위반 400. 미존재는 success=False(404 아님)."""
    vault = _vault(request)
    if vault is None:
        raise HTTPException(status_code=503, detail="시크릿 볼트를 사용할 수 없습니다 (keyring 미설치).")

    from core.secrets import SecretLabel

    try:
        sl = SecretLabel(label=label, namespace=_NAMESPACE)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        ok = vault.delete(sl)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"시크릿 삭제 실패: {exc}")
    return {"success": bool(ok), "label": label}
