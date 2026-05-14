# ADR 0003: 사용자 비밀 정보 (ID/PW/API 키) 는 vault 로 분리하고, AI/세션/로그/export 어디에도 평문이 남지 않게 한다

- **상태**: Accepted (2026-05-13 — Phase 1 PR-1 구현 진행 중)
- **최초 작성일**: 2026-05-13
- **결정자**: @toytiger
- **관련 문서**: [설계 — Phase 1+2 데이터 흐름·삽입점](../architecture/24-secrets-phase-1-2.md), [handoff.md §6 #5](../../handoff.md), [ADR 0001](0001-preserve-existing-core.md) (wrap-first 정책)

## 컨텍스트

ohdo 는 사용자가 자연어로 RPA 작업을 지시하면 AI 가 Python 코드를 생성·실행한다. 실제 자동화 시나리오에서 **사용자는 로그인 ID / 비밀번호 / API 키를 채팅에 그대로 타이핑한다** (예: "Gmail 로그인 ID `me@x.com` PW `MyP@ss!` 로 로그인해줘"). 이 평문이 현재 6 단계로 누출된다:

| # | 위치 | 누출 형태 | 현재 코드 |
|---|---|---|---|
| 1 | UI 입력 | 사용자가 채팅창에 평문 타이핑 | [ui_v2/main_window_v2.py:_send_request](../../../ui_v2/main_window_v2.py) (line 2274) |
| 2 | AI 전송 | prompt 그대로 외부 모델 (Gemini/DeepSeek/OpenAI) 로 송신 | [core/prompt_builder.py:build_step_prompt_split](../../../core/prompt_builder.py) → [app_service.py:694](../../../core/app_service.py) |
| 3 | 생성 코드 | AI 가 `pyautogui.write("MyP@ss!")` 같은 평문 박힌 코드 반환 — `Step.generated_code` 에 저장 | [app_service.py:generate_step](../../../core/app_service.py) (line 637+) |
| 4 | 세션 JSON | `data/sessions/*.json` 의 `user_request` + `generated_code` 평문 영구 저장 | [core/session_manager.py](../../../core/session_manager.py) save |
| 5 | 콘솔/로그 | 실행 시 `print(pw)` 같은 출력이 콘솔/로그에 노출 | [core/kernel_worker.py](../../../core/kernel_worker.py) stdout pipeline |
| 6 | Export | 워크플로우 export 시 main.py 안에 평문 박혀 다른 환경/공유로 누출 | [app_service.py:export_workflow](../../../core/app_service.py) (line 221) |

추가 압박:
- **system_context 절대 규칙 #8** ([config/prompts.json](../../../config/prompts.json)) 이 "사용자가 지정한 입력값 (ID, 비밀번호, 텍스트 등) 은 따옴표 안의 내용을 절대 변경하지 마세요" 라고 명시 — AI 에게 **평문 그대로 박으라**고 지시 중. 이 규칙 자체가 시크릿에 한해서는 반전되어야 함.
- handoff §6 #5: "API key 저장 위치 — 현재 `settings.json` 평문. OS keyring 으로 옮길지 결정 대기. v1.0 공개 전 결정 권장". AI 어댑터 api_key 도 같은 vault 로 통합 가능.
- commercial_review.md GO/NO-GO 게이트 #1 (저장소 public 공개 직전 보안 점검) 의 차단 요인.

## 결정

**1. 비밀 정보는 OS keyring 기반 vault 로 분리한다.** 사용자가 채팅에 평문으로 입력하더라도, AI / 세션 / 로그 / export 어디에도 평문이 남지 않는다.

### 데이터 모델 — `{{secret:label}}` placeholder

- 사용자 메시지·생성 코드·세션 JSON 의 비밀 영역은 항상 `{{secret:<label>}}` 토큰으로 저장.
- 실제 값은 OS keyring (Windows Credential Manager / macOS Keychain / Linux Secret Service) 에 `ohdo:secret:<label>` 키로 저장.
- AI 에는 placeholder 만 노출 — 외부 모델로 평문이 전혀 가지 않음 (현재 누출 경로 #2 차단).

### 다층 방어 (Defense in Depth)

```
사용자 입력 ──[A1 정규식+entropy 감지]──→ ⚠ 토스트 → [A2 시크릿 입력 UI] → vault 등록 + placeholder 치환
                                                                              │
                                                                              ▼
                                                      [C1 prompt_builder placeholder 통과] ─→ AI
                                                                              │
                                                                  AIResponse.code (placeholder 유지)
                                                                              │
                                                            [C2 G7 정적 분석] 평문 키 패턴 감지 시 재생성
                                                                              │
                                                                              ▼
                                                      [B3 session JSON 저장 — placeholder 만]
                                                                              │
                                                                              ▼
                                                      [D1 kernel 실행 — runtime 주입] env / get_secret()
                                                                              │
                                                                              ▼
                                                      [D2 콘솔 마스킹 — best effort]
                                                                              │
                                                                              ▼
                                                      [E1 export — .env.example 분리]
```

### 신규 모듈 (ADR 0001 wrap-first 준수)

- **`core/secrets.py`** — `SecretsVault` 추상 + `KeyringVault` (default) + `EncryptedFileVault` (fallback, 헤드리스/CI). API: `set(label, value)`, `get(label)`, `list()`, `delete(label)`, `migrate_from_session(session)`.
- **`core/secrets_detector.py`** — `detect(text) -> list[Match]`. 정규식 (`password\s*[:=]`, JWT `eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`, AWS `AKIA[0-9A-Z]{16}`, 등) + Shannon entropy 임계 (>4.5, 길이 ≥20).
- **`core/secrets_redact.py`** — `to_placeholders(text, vault) -> (placeholder_text, label_map)`, `from_placeholders(text, vault) -> resolved_text`. prompt 와 export 양쪽 path 에서 재사용.

기존 파일 수정 범위 (ADR 0001 조건 4 가지 만족):
- `core/app_service.py:generate_step` — placeholder 통과 + G7 정적 분석 후크 (현 정적 분석 path 의 새 룰)
- `core/prompt_builder.py:build_step_prompt_split` — placeholder 그대로 전달 (변환 없음 — `app_service` 가 사전 변환)
- `core/kernel_worker.py` — exec 시 `os.environ[f"OHDO_SECRET_{label}"]` 주입 + 종료 시 제거
- `core/execution_kernel.py:start` — vault 핸들 전달
- `config/prompts.json:system_context` — 규칙 #8 에 단서 추가 + 신규 규칙 #21 (시크릿 패턴) 추가
- `ui_v2/main_window_v2.py:_send_request` — 사전 검출 + 모달 + placeholder 치환 + 시크릿 입력 UI

기존 ui/ (v1) 는 ADR 0001 wrap-first 로 1차 범위 제외 — v2 패턴 확정 후 v1 mirror.

### 구현 Phase

| Phase | 범위 | 목표 효과 | 의존성 |
|---|---|---|---|
| **1 (사용자 인지 + AI guard)** | A1 감지+⚠ 토스트, C1 prompt 가이드 강화 (#21 신규), C2 G7 평문 키 정적 분석 | "AI 가 평문 안 박도록" + 사용자가 위험 인지 (vault 없이도 즉시 효과) | 없음 (1일) |
| **2 (Vault 통합)** | B1 `core/secrets.py` (keyring), A2 시크릿 입력 UI, B3 session placeholder + 마이그레이션, D1 runtime 주입 | "평문이 디스크/AI 에 안 가는 구조 완성" | Phase 1 + `keyring` deps 추가 (2~3일) |
| **3 (SaaS 전 보강)** | B2 암호화 파일 fallback, D2 콘솔 마스킹, E1 export `.env.example`, 외부 vault provider 추상화 | "팀 사용 + 헤드리스 환경 대응 + 외부 vault" | Phase 2 + commercial_review GO/NO-GO 게이트 (2~3일) |

Phase 1 단독으로도 누출 경로 #2/#3 의 위험을 크게 낮춤. Phase 2 완료 시 #1~#4 완전 차단. Phase 3 으로 #5/#6 + 팀/SaaS 시나리오 대응.

### 의존성 정책

- **`keyring`** (Python lib, MIT) — Phase 2 도입. cross-platform (Windows Credential Manager / macOS Keychain / Linux Secret Service).
- **`cryptography`** (Apache-2.0/BSD) — Phase 3 EncryptedFileVault 도입. 이미 transitive dep 가능 (requests/urllib3 경유) — 명시 추가만.
- **외부 vault provider** (HashiCorp Vault, 1Password CLI 등) — Phase 3 의 `SecretsVault` 추상 확장점. v1.x 까진 keyring + 파일 fallback 만.

### 호환성 / 마이그레이션

- 기존 세션 JSON 평문 잔존 — 다음 중 하나:
  - **(a) 자동 마이그레이션**: 세션 로드 시 detector 가 평문 발견 → 사용자 확인 후 vault 등록 + 세션 재저장 (placeholder 로 in-place 치환). 옛 백업은 그대로 둠 — 사용자가 명시적으로 정리해야 함.
  - **(b) 수동 마이그레이션**: 1회용 CLI `ohdo migrate-secrets` 옵션 제공 (선택).
- 결정: **(a) 자동 + 사용자 확인** — Phase 2 의 B3 작업에 포함.

### 회귀 가드

- 신규 단위 테스트 (test_117~ 예정):
  - `secrets_detector.detect` — known 패턴 + entropy 임계 (true-positive/false-positive 균형)
  - `secrets_redact.to_placeholders` round-trip
  - `app_service.generate_step` 호출 시 `_ai.generate` 에 평문 0건 (mock AI 로 prompt 검증)
  - `app_service.export_workflow` 결과에 평문 0건 + `.env.example` 존재 (Phase 3)
  - G7 정적 분석 — 평문 키 패턴 (JWT/AWS/길이+entropy) 시 ⚠ + 재생성 prompt 에 인용
- 기존 scenarios suite 의 `test_71_d22_export_uses_app_service` 등 영향 — placeholder 처리 path 만 추가하므로 기존 contract 유지.

## 결과

### 장점

- 외부 AI 모델에 비밀 정보 송신 0건 — 모델 제공자 측 로그 보존·재학습 risk 차단 (현재 OpenAI/DeepSeek 등 제공자 정책상 input 30일 retention 가능).
- 사용자 메시지가 SaaS 로 옮겨가도 동일 패턴 — 백엔드 DB 에 placeholder 만, 시크릿은 사용자 디바이스 vault.
- handoff §6 #5 + commercial_review #1 + public 공개 #1 동시 해결.
- AI 가 평문 박는 환각 (rule #8 의 부작용) 을 G7 정적 분석으로 정량 측정 가능.

### 단점 및 대응

- vault unlock UX — keyring 은 OS 가 권한 관리해 별도 unlock 없음 (장점). EncryptedFileVault 는 앱 시작 시 1회 패스프레이즈 — 사용자 친화성 보강 필요 (Phase 3 사용성 작업).
- AI 가 placeholder 를 따르지 않고 평문 박는 경우 — G7 정적 분석 (Phase 1 C2) 으로 catch. 100% 아니지만 known 패턴은 잡힘. False-positive 는 사용자가 "그대로 진행" 선택 가능.
- 한국어 자연어에 "비번", "비밀번호", "토큰" 단어가 nontechnical 맥락에서 나오는 false-positive — A1 의 토스트는 차단이 아닌 **권장**으로만. 사용자가 무시 가능.
- 옛 세션 JSON 평문 잔존 — 자동 마이그레이션 + 사용자 확인 + 백업 안내로 완화.

## 미결정 / 후속 결정 후보

- **외부 vault (HashiCorp Vault, 1Password CLI)**: v1.x 까지 keyring 만. SaaS / 팀 사용 시점에 ADR 0004 로 다시 정함.
- **AI 어댑터 api_key vault 마이그레이션 범위**: 현재 `settings.json` 평문 — Phase 2 의 B1 vault 에 같이 옮길지 (사용자 시크릿과 같은 store), 별도 namespace 로 둘지. → 같은 vault, namespace 만 분리 (`ohdo:apikey:<engine>` vs `ohdo:secret:<label>`). 권장.
- **시크릿 만료 / rotation 알림**: 사용자가 API 키 갱신 시점 안내. v1.x 범위 외.
- **다중 vault provider 추상화 시점**: Phase 3 에서 외부 vault 추가 여부 결정 시 ADR 0004.

## 관련

- [설계 — Phase 1+2 데이터 흐름·삽입점·API·테스트 계획](../architecture/24-secrets-phase-1-2.md)
- [ADR 0001: wrap-first 정책](0001-preserve-existing-core.md)
- [ADR 0002: AppService + Storage Facade](0002-appservice-facade-approach.md)
- [handoff.md §6 #5](../../handoff.md) — keyring 결정 대기 → 본 ADR 로 해소
- [commercial_review.md](../../commercial_review.md) GO/NO-GO #1 — 본 ADR Phase 1+2 완료 시 #1 보안 게이트 1차 통과
