# Architecture: 시크릿 처리 Phase 1 + 2 — 데이터 흐름, 삽입점, API, 테스트 계획

- **상태**: Design (구현 대기)
- **날짜**: 2026-05-13
- **관련 ADR**: [0003 — 시크릿 처리 정책](../decisions/0003-secrets-handling.md)
- **범위**: Phase 1 (A1 + C1 + C2) + Phase 2 (B1 + A2 + B3 + D1). Phase 3 은 본 문서 끝의 "후속" 섹션에만 언급.

본 문서는 ADR 0003 의 결정을 실제 코드에서 어디에 어떻게 박을지 정확한 file:line 단위로 정리한다. 구현 PR 시 이 문서가 단일 reference.

## 1. 데이터 흐름 (Phase 2 완료 기준)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  UI (ui_v2/main_window_v2.py)                                           │
│                                                                         │
│  사용자 채팅 입력 "ID: me@x.com PW: MyP@ss!"                              │
│       │                                                                 │
│       ▼                                                                 │
│  _on_send_message (line 2216)                                           │
│       │  text_raw = self.message_edit.toPlainText()                     │
│       │                                                                 │
│       ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │ [A1] secrets_detector.detect(text_raw)                      │        │
│  │   → matches: [Match(span, kind="password", entropy=4.7), …] │        │
│  └─────────────────────────────────────────────────────────────┘        │
│       │                                                                 │
│       ▼ matches 비어있지 않으면                                          │
│  ⚠ SecretAdvisoryDialog                                                │
│   ├─ [🔒 시크릿으로 등록] → A2 SecretInputDialog → vault.set(label, val)│
│   │                       → text = secrets_redact.replace(text_raw,    │
│   │                                                       matches,     │
│   │                                                       label_map)   │
│   ├─ [그대로 전송]        → text = text_raw (사용자 명시 무시)         │
│   └─ [취소]              → return (메시지 안 보냄)                     │
│       │                                                                 │
│       ▼                                                                 │
│  _send_request(text, images, elements) (line 2274)                      │
│       │                                                                 │
└───────┼─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  AppService.generate_step (core/app_service.py:637)                     │
│                                                                         │
│  user_request (placeholder 포함 — {{secret:gmail_pw}})                  │
│       │                                                                 │
│       ▼                                                                 │
│  [C1] prompt_builder.build_step_prompt_split (line 694)                 │
│   placeholder 그대로 prompt 에 들어감 — 사전 변환 X                     │
│   system_context #21 신규 규칙: "{{secret:xxx}} 패턴은 get_secret('xxx')│
│   로 참조하라. 평문 박지 마라"                                          │
│       │                                                                 │
│       ▼                                                                 │
│  AIEngineManager.generate(prompt) (line 709)                            │
│       │   외부 AI 모델 (Gemini/DeepSeek/OpenAI) — 평문 0건 전송          │
│       │                                                                 │
│       ▼                                                                 │
│  AIResponse.code (placeholder + get_secret 패턴 유지)                   │
│       │                                                                 │
│       ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │ [C2] G7 정적 분석 (code_quality 모듈 — 신규 룰)             │        │
│  │   detect_hardcoded_secrets(code)                            │        │
│  │     - JWT (eyJ...), AWS (AKIA...), 길이+entropy 임계         │        │
│  │     - 발견 시 ⚠ 카드 표시 + 재생성 prompt 에 인용             │        │
│  └─────────────────────────────────────────────────────────────┘        │
│       │                                                                 │
│       ▼                                                                 │
│  Step 생성 — generated_code 에 placeholder 만                           │
│       │                                                                 │
│       ▼                                                                 │
│  [B3] add_step → repo.save_session                                      │
│   data/sessions/<id>.json — user_request + generated_code 모두           │
│   placeholder 만 저장. 평문 0건                                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼ 사용자가 "실행" 클릭
┌─────────────────────────────────────────────────────────────────────────┐
│  ExecutionKernel.start (core/execution_kernel.py)                       │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │ [D1] vault.list_used_in(code) → labels                      │        │
│  │  for label in labels:                                       │        │
│  │      env[f"OHDO_SECRET_{label}"] = vault.get(label)         │        │
│  │  subprocess.Popen(..., env=env)                             │        │
│  └─────────────────────────────────────────────────────────────┘        │
│       │                                                                 │
│       ▼                                                                 │
│  kernel_worker.exec(code)                                               │
│   - code 안 `{{secret:gmail_pw}}` placeholder → get_secret() 헬퍼가     │
│     `os.environ['OHDO_SECRET_gmail_pw']` 읽어 평문 반환                  │
│   - placeholder 자체는 코드 안에 문자열로 안 들어감 — AI 가 항상         │
│     `pw = get_secret('gmail_pw')` 패턴 생성하도록 system_context 강제   │
│                                                                         │
│  finally: env 에서 OHDO_SECRET_* 삭제 (best effort — Python GC 보장 X)  │
└─────────────────────────────────────────────────────────────────────────┘
```

## 2. 신규 모듈 — API 표면

### 2.1 `core/secrets.py`

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""사용자 비밀 정보 (ID/PW/API 키) vault.

[ADR 0003](../docs/saas/decisions/0003-secrets-handling.md) 참조.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SecretLabel:
    """vault 안의 시크릿 식별자. label 은 `[a-z0-9_]{1,32}` 패턴."""
    label: str
    namespace: str = "secret"  # "secret" (사용자) vs "apikey" (AI 어댑터)


class SecretsVault(ABC):
    """vault 구현 추상. KeyringVault (default) / EncryptedFileVault (fallback)."""

    @abstractmethod
    def set(self, label: SecretLabel, value: str) -> None: ...

    @abstractmethod
    def get(self, label: SecretLabel) -> Optional[str]:
        """미존재 시 None. 절대 raise 안 함 (호출자가 placeholder 미해결 대응)."""

    @abstractmethod
    def delete(self, label: SecretLabel) -> bool: ...

    @abstractmethod
    def list(self, namespace: str = "secret") -> list[SecretLabel]: ...

    def get_for_env(self, labels: list[SecretLabel]) -> dict[str, str]:
        """runtime 주입용 — {f"OHDO_SECRET_{label.label}": value}.

        D1 의 핵심 helper. 미존재 label 은 skip (warning log).
        """
        env: dict[str, str] = {}
        for lab in labels:
            val = self.get(lab)
            if val is not None:
                env[f"OHDO_SECRET_{lab.label}"] = val
        return env


class KeyringVault(SecretsVault):
    """`keyring` 라이브러리 기반 — Windows Credential Manager / macOS
    Keychain / Linux Secret Service 자동 분기.
    """

    SERVICE_NAME = "ohdo.ai"

    def __init__(self) -> None:
        import keyring  # noqa: F401 — fail-fast on missing dep
        self._keyring = keyring

    def _full_key(self, label: SecretLabel) -> str:
        return f"{label.namespace}:{label.label}"

    def set(self, label: SecretLabel, value: str) -> None:
        self._keyring.set_password(self.SERVICE_NAME, self._full_key(label), value)

    def get(self, label: SecretLabel) -> Optional[str]:
        return self._keyring.get_password(self.SERVICE_NAME, self._full_key(label))

    def delete(self, label: SecretLabel) -> bool:
        try:
            self._keyring.delete_password(self.SERVICE_NAME, self._full_key(label))
            return True
        except self._keyring.errors.PasswordDeleteError:
            return False

    def list(self, namespace: str = "secret") -> list[SecretLabel]:
        """keyring 은 list API 없음 — 사용자 입력 history 를
        `data/vault_index.json` 에 별도 저장 (값 X, label 만).
        """
        ...  # 구현은 IndexedKeyringVault 로 wrap
```

`AppService` 생성자에 `secrets_vault: SecretsVault | None = None` 인자 추가 — 미주입 시 vault 의존 path 는 skip (Phase 1 만 활성).

### 2.2 `core/secrets_detector.py`

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""사용자 텍스트에서 비밀 정보 후보 감지."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SecretMatch:
    span: tuple[int, int]    # text 안 위치
    kind: str                # 'password' | 'jwt' | 'aws' | 'high_entropy' | …
    value: str               # 해당 부분 텍스트
    confidence: float        # 0.0 ~ 1.0
    suggested_label: str     # vault 등록 시 기본 label 제안 (예: 'gmail_pw')


# 패턴 — 한국어/영어 양쪽 커버
_PASSWORD_HINTS = re.compile(
    r"(?P<key>비밀번호|비번|패스워드|password|passwd|pwd|pw)\s*[:=]?\s*['\"]?(?P<val>\S{4,128})['\"]?",
    re.IGNORECASE,
)
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")
_AWS_AK = re.compile(r"AKIA[0-9A-Z]{16}")
_GH_PAT = re.compile(r"ghp_[A-Za-z0-9]{36}")
_OPENAI = re.compile(r"sk-[A-Za-z0-9]{20,}")
# 길이 20+ 의 url-safe / hex 토큰 (entropy 검사로 통과해야 match)
_GENERIC = re.compile(r"[A-Za-z0-9_\-/+=]{20,}")


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def detect(text: str, *, entropy_threshold: float = 4.5) -> list[SecretMatch]:
    """text 안 비밀 정보 후보 반환. false-positive 허용 — UI 가 확정."""
    matches: list[SecretMatch] = []
    # 명시 패턴들 — 높은 confidence
    for m in _PASSWORD_HINTS.finditer(text):
        matches.append(SecretMatch(
            span=m.span("val"), kind="password", value=m.group("val"),
            confidence=0.9,
            suggested_label=f"{m.group('key').lower()}_value",
        ))
    for kind, pat, conf in (
        ("jwt", _JWT, 0.95), ("aws_key", _AWS_AK, 0.99),
        ("github_pat", _GH_PAT, 0.99), ("openai_key", _OPENAI, 0.95),
    ):
        for m in pat.finditer(text):
            matches.append(SecretMatch(
                span=m.span(), kind=kind, value=m.group(),
                confidence=conf, suggested_label=f"{kind}_token",
            ))
    # 일반 high-entropy — 낮은 confidence (false-positive 많음)
    for m in _GENERIC.finditer(text):
        ent = _shannon_entropy(m.group())
        if ent >= entropy_threshold:
            # 이미 더 구체적 패턴에 잡힌 영역은 skip
            if any(_overlap(m.span(), x.span) for x in matches):
                continue
            matches.append(SecretMatch(
                span=m.span(), kind="high_entropy",
                value=m.group(), confidence=min(0.5 + (ent - entropy_threshold) / 4, 0.85),
                suggested_label="token",
            ))
    return matches


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return not (a[1] <= b[0] or b[1] <= a[0])
```

### 2.3 `core/secrets_redact.py`

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""user_request / generated_code 의 placeholder ↔ 평문 변환."""
from __future__ import annotations

import re

from core.secrets import SecretLabel, SecretsVault
from core.secrets_detector import SecretMatch

_PLACEHOLDER = re.compile(r"\{\{secret:([a-z0-9_]{1,32})\}\}")


def to_placeholder_text(
    text: str,
    matches: list[SecretMatch],
    label_map: dict[tuple[int, int], str],
) -> str:
    """matches 의 span 을 `{{secret:label}}` 로 치환. span 역순 처리 (인덱스 보존)."""
    out = text
    for m in sorted(matches, key=lambda x: -x.span[0]):
        if m.span not in label_map:
            continue
        label = label_map[m.span]
        out = out[: m.span[0]] + f"{{{{secret:{label}}}}}" + out[m.span[1]:]
    return out


def has_placeholders(text: str) -> bool:
    return bool(_PLACEHOLDER.search(text))


def extract_labels(text: str) -> list[SecretLabel]:
    """code/text 에 사용된 placeholder label 목록 (중복 제거)."""
    seen: set[str] = set()
    out: list[SecretLabel] = []
    for m in _PLACEHOLDER.finditer(text):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(SecretLabel(label=m.group(1)))
    return out


def resolve(text: str, vault: SecretsVault) -> tuple[str, list[str]]:
    """placeholder → 평문. **export / 디버깅 한정**. runtime 실행에선 D1 env 주입 사용.

    Returns:
        (resolved_text, unresolved_labels) — vault 미존재 label 은 placeholder 유지.
    """
    unresolved: list[str] = []

    def _sub(m: re.Match) -> str:
        label = SecretLabel(label=m.group(1))
        val = vault.get(label)
        if val is None:
            unresolved.append(m.group(1))
            return m.group(0)
        return val

    return _PLACEHOLDER.sub(_sub, text), unresolved
```

## 3. 기존 파일 수정 — 정확한 삽입점

### 3.1 `config/prompts.json:system_context`

**규칙 #8 (수정)** — 현재 "사용자가 지정한 입력값 (ID, 비밀번호, 텍스트 등) 은 따옴표 안의 내용을 절대 변경하지 마세요" 끝에 단서 추가:

> ...단, `{{secret:label}}` 형식의 placeholder 는 예외 — 규칙 #21 적용.

**규칙 #21 (신규 추가)**:

```
21. **비밀 정보 placeholder 처리 (보안)**:
    사용자 메시지 또는 element_context 에 `{{secret:<label>}}` 패턴이 있으면 그
    label 의 실제 값을 코드에 평문으로 박지 마세요. 항상 helper 로 참조:

    ```python
    from core.secrets_runtime import get_secret
    pw = get_secret('gmail_pw')          # vault → os.environ → 평문
    pyautogui.write(pw)
    ```

    🚨 절대 금지 (회귀 시 사용자 보안 사고):
    - ❌ `pyautogui.write("MyP@ss!")` — 평문 박힘
    - ❌ `pw = "MyP@ss!"; pyautogui.write(pw)` — 평문 박힘
    - ❌ `pyautogui.write("{{secret:gmail_pw}}")` — placeholder 문자열 그대로 입력됨

    ✅ 올바른 패턴:
    - ✅ `pw = get_secret('gmail_pw'); pyautogui.write(pw)` — runtime 주입
    - ✅ ASCII 분기 가이드 #13 도 동일 — `pw = get_secret(...)` 후 write/paste 분기

    AWS / OpenAI / GitHub PAT / JWT 등 토큰 패턴 (`AKIA...`, `sk-...`, `ghp_...`,
    `eyJ...`) 도 동일 — 코드에 박지 말고 vault 등록 + `get_secret()` 호출.
```

### 3.2 `core/prompt_builder.py:build_step_prompt_split`

**수정 없음** — placeholder 가 이미 user_request 안에 들어와 있으므로 그대로 통과. `system_context` 의 #21 신규 규칙이 AI 에게 처리 방법을 알려줌.

선택 보강 (Phase 2):
- `build_step_prompt_split` 의 결과를 반환 직전 sanity check: 만약 system_text/user_text 안에 detect()-match 가 남아있으면 (사용자가 ⚠ 무시하고 평문 전송 선택) `logger.warning("plaintext secret detected in prompt — A1 detector missed or user override")` 로 기록.

### 3.3 `core/app_service.py:generate_step` (line 637)

생성자 (line ~80) 에 `secrets_vault: SecretsVault | None = None` 추가.

**A: prompt 직전** (line ~694 `build_step_prompt_split` 호출 직전):

```python
# user_request 가 placeholder 포함이면 그대로 통과 (system_context #21 의존).
# placeholder 미해결 (vault 미주입) 도 OK — AI 가 코드 안에 placeholder 그대로
# 둠 → runtime D1 가 처리.
```

(주석만 추가 — 동작 변경 X)

**B: AI 응답 후, Step 생성 직전** (line 727 `if not response.success:` 이전):

```python
# C2: G7 정적 분석 — 평문 키 패턴 감지
from core.secrets_detector import detect
plaintext_matches = detect(response.code or "")
if plaintext_matches:
    # 카드에 ⚠ 표시 — 신규 warning 종류 'hardcoded_secret'
    # G7-D 재생성 흐름과 동일 — previous_warnings 에 추가
    response = response  # warning 정보를 어디에 담을지는 구현 시 결정
    # 옵션 1) response.warnings 필드 (신규)
    # 옵션 2) Step.warnings (기존 G7 path 와 통합)
```

**C: Step 생성 시점** (line ~750+ Step 인스턴스화):

```python
# generated_code 가 placeholder 만 포함하도록 — AI 가 평문 박았으면 위 C2 에서
# warning 처리. (B3 의 핵심 — Step 저장 path 가 placeholder 보존)
```

### 3.4 `core/execution_kernel.py:start`

생성자에 `secrets_vault: SecretsVault | None = None` 추가. `start()` 안에서:

```python
# D1: runtime 주입
if self._vault is not None:
    from core.secrets_redact import extract_labels
    code = self._get_full_code_to_execute()  # library + steps
    labels = extract_labels(code)
    env_extra = self._vault.get_for_env(labels)
    # 기존 env 에 merge (OHDO_PARENT_PID + OHDO_SECRET_* 공존)
    env = {**os.environ, "OHDO_PARENT_PID": str(os.getpid()), **env_extra}
else:
    env = {**os.environ, "OHDO_PARENT_PID": str(os.getpid())}

subprocess.Popen(..., env=env)
```

### 3.5 `core/kernel_worker.py`

**A: get_secret helper inject** — subprocess 시작 시 자동으로 `core.secrets_runtime` 모듈을 globals 에 주입 (또는 prelude 코드로 prepend):

```python
# prelude — exec 전에 globals 에 한 번만 주입
PRELUDE = """
import os as _os
def get_secret(label):
    val = _os.environ.get(f'OHDO_SECRET_{label}')
    if val is None:
        raise RuntimeError(
            f"secret '{label}' not in vault — "
            "ohdo Settings → 시크릿 관리에서 등록하세요."
        )
    return val
"""
```

**B: finally 절** (exec 종료 후):

```python
finally:
    # AllowSetForegroundWindow (기존 §4.5 fix 유지)
    if sys.platform == "win32":
        ctypes.windll.user32.AllowSetForegroundWindow(parent_pid)
    # D1 cleanup — 환경변수 제거 (best effort)
    for k in list(os.environ):
        if k.startswith("OHDO_SECRET_"):
            del os.environ[k]
```

### 3.6 `ui_v2/main_window_v2.py`

**A: `_on_send_message` (line 2216)** — `_send_request` 호출 전에 detector + 모달 분기:

```python
def _on_send_message(self) -> None:
    text_raw = self.message_edit.toPlainText().strip()
    if not text_raw:
        return

    # A1 + A2: 시크릿 감지 → 모달
    from core.secrets_detector import detect
    matches = detect(text_raw)
    if matches and self._vault is not None:
        text, cancelled = self._prompt_secret_advisory(text_raw, matches)
        if cancelled:
            return
    else:
        text = text_raw

    # 기존 path
    self._send_request(text, images=self._pending_images, elements=self._pending_elements)
    ...
```

**B: `_prompt_secret_advisory` (신규)**:

```python
def _prompt_secret_advisory(
    self, text: str, matches: list["SecretMatch"]
) -> tuple[str, bool]:
    """⚠ 모달 + 시크릿 입력 UI. Returns (placeholder_text, cancelled)."""
    # SecretAdvisoryDialog — matches 리스트 표시 + 각 행 옆 [🔒 등록] 버튼
    # 사용자가 [그대로 전송] 누르면 (text, False) 반환
    # 사용자가 [취소] 누르면 ("", True) 반환
    # 사용자가 [🔒 등록] 누르면 label 입력 후 vault.set + placeholder 치환
    ...
```

**C: 시크릿 관리 UI (Settings 메뉴 추가)** — 기존 SettingsDialog 에 "시크릿" 탭 추가. vault.list() → 표 (label, namespace, 최근 사용). [삭제] / [라벨 변경] / [+ 추가] 버튼.

### 3.7 i18n catalog (locale/{en,ko}.json)

신규 키 (Phase 2 작업 시 catalog 동시 추가 — handoff §21 i18n 패턴 준수):

| 키 | ko | en |
|---|---|---|
| `dialog.secret_advisory.title` | 비밀 정보 감지 | Sensitive data detected |
| `dialog.secret_advisory.body` | 입력에 비밀번호 또는 토큰으로 보이는 값이 있어요. | Your message contains what looks like a password or token. |
| `btn.register_as_secret` | 🔒 시크릿으로 등록 | 🔒 Register as secret |
| `btn.send_as_is` | 그대로 전송 | Send anyway |
| `btn.cancel` | 취소 | Cancel |
| `settings.secrets.tab` | 시크릿 | Secrets |
| `settings.secrets.add` | + 추가 | + Add |
| `settings.secrets.empty` | 등록된 시크릿이 없습니다 | No secrets registered |
| `toast.secret_registered` | 시크릿 등록됨: {label} | Secret registered: {label} |

## 4. 마이그레이션 — 기존 세션 평문 잔존 처리

**자동 마이그레이션 (Phase 2)** — 세션 로드 시:

```python
# AppService.get_session — 로드 직후
from core.secrets_detector import detect
plaintext_found = []
for step in session.steps:
    matches = detect(step.user_request) + detect(step.generated_code or "")
    if matches:
        plaintext_found.append((step.step_id, matches))

if plaintext_found:
    # UI 에 신호 → 사용자 확인 모달
    # 사용자 [마이그레이션 실행] → vault.set + 세션 in-place 치환 + 재저장
    # 사용자 [나중에] → flag 만 켜고 표시
    # 사용자 [무시] → 세션 metadata 에 "migration_skipped" 기록
```

옛 백업 (`tmp/conversations/`, `data/sessions.bak/`) 은 손대지 않음 — 사용자가 명시적으로 삭제.

## 5. 테스트 계획 (test_117~)

### Phase 1

| # | 테스트 | 검증 |
|---|---|---|
| test_117 | `secrets_detector.detect` known 패턴 | password/JWT/AWS/OpenAI/GH PAT 각각 매칭 + span 정확 |
| test_118 | `secrets_detector.detect` false-positive | 평범한 한국어 문장 ("비밀번호를 까먹었어요") → password match 안 됨 (값 부분 없음) |
| test_119 | `secrets_detector.detect` entropy threshold | 길지만 entropy 낮은 ("aaaaaaa...") skip, 높은 random hex match |
| test_120 | system_context #21 키워드 존재 | `'{{secret:' in system_context and 'get_secret' in system_context` |
| test_121 | `AppService.generate_step` G7 정적 분석 활성화 | mock AI 가 `pyautogui.write("MyP@ss!")` 반환 시 warnings 에 `hardcoded_secret` 포함 |

### Phase 2

| # | 테스트 | 검증 |
|---|---|---|
| test_122 | `KeyringVault` set/get round-trip | tmp keyring backend (pytest-keyring) 으로 set 후 get 일치 |
| test_123 | `secrets_redact.to_placeholder_text` 역순 처리 | 여러 match 가 같은 text 에 있을 때 span 인덱스 보존 |
| test_124 | `secrets_redact.extract_labels` 중복 제거 | 같은 label 여러 번 등장 시 1회만 반환 |
| test_125 | `AppService.generate_step` placeholder 미변환 통과 | user_request 에 `{{secret:gmail_pw}}` 포함 시 prompt 에 그대로 전달 (mock AI 의 input 검증) |
| test_126 | `AppService.generate_step` 평문 0건 (mock AI) | user_request 에 시크릿 등록 후 placeholder 치환된 입력 → `_ai.generate` 의 prompt 인자에 평문 안 들어감 |
| test_127 | `add_step` 저장 시 placeholder 유지 | session.json 의 `user_request` / `generated_code` 가 placeholder 만 |
| test_128 | `ExecutionKernel.start` env 주입 | mock subprocess 의 env 에 `OHDO_SECRET_xxx` 존재 + 값 일치 |
| test_129 | `kernel_worker.PRELUDE` get_secret helper | exec 시 `get_secret('xxx')` 가 환경변수 읽음 |
| test_130 | `secrets_runtime.get_secret` 미존재 RuntimeError | 환경변수 미존재 시 명확한 메시지 + 사용자 안내 |
| test_131 | 마이그레이션 — 평문 detect → vault | 평문 박힌 세션 로드 시 plaintext_found 리스트 채워짐 |

기존 scenarios (73개) 영향 — `test_71_d22_export_uses_app_service` 등 export path 는 Phase 3 에서 `.env.example` 분리 시점에만 영향 (Phase 1+2 범위 외).

## 6. PR 분할 (구현 시점)

- **PR-1 (Phase 1, 1일)**: secrets_detector 모듈, system_context #21, app_service G7 후크, test_117~121.
- **PR-2 (Phase 2-a, 1일)**: core/secrets.py + KeyringVault + secrets_redact 모듈, `keyring` deps 추가, test_122~124.
- **PR-3 (Phase 2-b, 1일)**: AppService/Kernel 통합 (D1 runtime 주입 + B3 session placeholder), test_125~130 + i18n catalog.
- **PR-4 (Phase 2-c, 1일)**: ui_v2 시크릿 advisory + 입력 UI + Settings 탭 + 마이그레이션 모달, test_131.

각 PR baseline (core + scenarios) 그린 유지. PR-3 의 ExecutionKernel 변경은 §4.5 ForegroundLock fix (`OHDO_PARENT_PID`) 와 함께 env 처리되도록 주의.

## 7. Phase 3 (참고만 — 본 PR 범위 외)

- `EncryptedFileVault` (cryptography 라이브러리) — keyring 사용 불가 환경 fallback
- `kernel_worker` 콘솔 마스킹 — exec stdout 캡처에서 vault 값 검색 후 `***` 치환 (best-effort)
- `export_workflow` — placeholder → `.env.example` + `os.environ['SECRET_xxx']` 패턴 + `python-dotenv` 의존 + `.gitignore` 자동 포함
- 외부 vault provider (HashiCorp Vault, 1Password CLI, AWS Secrets Manager) — `SecretsVault` 추상 확장점

Phase 3 시작 시 ADR 0004 (외부 vault provider) 별도 작성.

## 8. 위험 / 미해결 질문

- **keyring 의존성 (Phase 2)**: Linux 서버 / CI 환경에서 D-Bus / Secret Service 없음 — `KeyringVault` init 실패. 자동으로 `EncryptedFileVault` fallback 또는 사용자에게 명시 모드 선택. Phase 3 작업으로 미룸. v1.x (Windows desktop) 까지는 keyring 만 — 우선순위 OK.
- **`get_secret()` helper 모듈 경로**: subprocess 안에서 `from core.secrets_runtime import get_secret` 할 때 `sys.path` 에 ohdo root 가 있어야 함. 현재 kernel_worker 가 PRELUDE 로 직접 `def get_secret(label):` 주입하면 의존성 0 — 권장.
- **AI 가 placeholder 무시하고 평문 박는 빈도**: G7 정적 분석 (C2) 으로 catch — Phase 1 완료 후 실 데이터로 정량 측정. 임계 이상이면 prompt 보강 또는 model-specific 분기 (handoff §22 C 의 환각 대응 트랙).
- **시크릿 라벨 충돌**: 사용자가 같은 label 로 다른 값을 등록하려 할 때 — Settings UI 에서 명시 confirm 모달.
- **사용자가 ⚠ 무시하고 [그대로 전송] 선택 시 — 모델별 retention 정책 안내**: 첫 사용 시 onboarding 토스트 ("Gemini/OpenAI 등은 입력을 N일 보존할 수 있습니다") 추가 검토. UX 결정 — 본 ADR 범위 외.

---

본 문서는 ADR 0003 의 구현 단일 reference. PR 작성 시 본 문서의 §3 (삽입점) + §5 (테스트) 를 체크리스트로 사용.
