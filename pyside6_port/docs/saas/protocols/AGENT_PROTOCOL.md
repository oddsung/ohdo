# Agent ↔ Control Plane 프로토콜 (초안 v0)

- **상태**: Draft — 사용자 리뷰 대기
- **날짜**: 2026-04-22
- **버전**: `protocol/v0`

로컬 PC 에 설치된 **ohdo Agent** 와 클라우드 **Control Plane** 이 어떻게 통신하는지를 기술한다. 실제 구현 전에 "이 스펙이 말이 되는가" 에 대한 사용자 리뷰가 우선.

## 1. 전송 계층

| 용도 | 방향 | 방식 |
|---|---|---|
| 명령 수신 / 상태 보고 | Agent ⇄ Server | **WebSocket over TLS** (`wss://api.ohdo.ai/v0/agent`) |
| 대용량 업로드 (스크린샷·로그 파일) | Agent → S3/R2 | **HTTPS, pre-signed URL** — 서버가 미리 발급한 URL 로 직접 PUT |
| 설치·업데이트·초기 등록 | Agent → Server | HTTPS REST |

**WS 기본값**: 하트비트 20초, 재연결 지수 백오프 (1s → 60s), 재연결 시 마지막 `event_id` 로 **재동기화**.

## 2. 인증 — OAuth Device Flow 응용

Agent 가 처음 깔릴 때 사용자는 브라우저가 있을 뿐 토큰 복붙은 하고 싶지 않다. 아래 흐름은 GitHub CLI·Google TV 등에서 검증된 패턴이다.

```
1. Agent 기동 → 토큰 없음 → REST POST /v0/agents/device_code
    응답: { device_code, user_code: "ABCD-1234", verification_uri: "https://app.ohdo.ai/link" }
2. Agent 가 트레이에서 "브라우저를 열어 ABCD-1234 입력" 알림
3. 사용자 로그인된 브라우저에서 코드 입력 → 승인
4. Agent 가 /v0/agents/device_token 을 폴링 → { agent_token, agent_id }
5. 이후 모든 WS/REST 호출에 Authorization: Bearer <agent_token>
```

- `agent_token` 은 기기별 장기 토큰 (재발급 가능, 사용자가 대시보드에서 revoke 가능).
- 서버는 `agent_id` 와 사용자·워크스페이스를 1:N 매핑.

## 3. WebSocket 메시지 포맷

모든 프레임은 JSON, 최상위 필드:

```json
{
  "v": 0,
  "type": "<message_type>",
  "id": "<uuid>",
  "ts": "<ISO-8601>",
  "payload": { ... }
}
```

- `v`: 프로토콜 버전. 서버가 클라이언트보다 높으면 downgrade, 낮으면 Agent 에 업데이트 요청.
- `id`: 멱등성·순서 보장용. Agent → Server 응답은 원본 `id` 를 `in_reply_to` 로 에코.

### 3.1 메시지 타입

| 방향 | `type` | 목적 |
|---|---|---|
| Agent → Server | `agent.hello` | 버전, OS, 디스플레이 수, 설치된 Python 경로 등 등록 |
| Agent → Server | `agent.heartbeat` | 20초 주기 생존 신호 + 리소스 (CPU/메모리) |
| Server → Agent | `execution.start` | 세션 ID + 스텝 범위를 지정하여 실행 지시 |
| Agent → Server | `execution.accepted` | 실행 큐에 올림 |
| Agent → Server | `execution.progress` | 스텝별 진행 (started/finished + step_id) |
| Agent → Server | `execution.log` | stdout/stderr 라인 스트리밍 (버퍼링 권장) |
| Agent → Server | `execution.capture` | 스크린샷 업로드 완료 통지 (S3 key 포함) |
| Agent → Server | `execution.result` | 최종 `ExecutionReport` 전체 |
| Server → Agent | `execution.cancel` | 현재 실행 중지 (워크플로우엔진 `stop()`) |
| Server → Agent | `config.update` | 설정 핫 리로드 (로그 레벨 등) |
| Server → Agent | `agent.upgrade` | 신규 버전 다운로드 URL + 서명 |

### 3.2 예시 — `execution.start`

```json
{
  "v": 0, "type": "execution.start",
  "id": "7d3c...", "ts": "2026-04-22T12:34:56Z",
  "payload": {
    "execution_id": "exec_01HK...",
    "session_id": "sess_f9a...",
    "from_step": 1,
    "to_step": null,
    "ai_proxy": true,
    "capture_upload_urls": {
      "presign_endpoint": "https://api.ohdo.ai/v0/captures/presign"
    }
  }
}
```

### 3.3 예시 — `execution.result`

```json
{
  "v": 0, "type": "execution.result",
  "id": "a1b2...", "in_reply_to": "7d3c...",
  "ts": "2026-04-22T12:38:41Z",
  "payload": {
    "execution_id": "exec_01HK...",
    "total_steps": 4, "executed_steps": 4,
    "successful_steps": 3, "failed_steps": 1,
    "total_time_ms": 184213,
    "step_results": [
      {"step_id": 1, "success": true,  "duration_ms": 12042},
      {"step_id": 2, "success": true,  "duration_ms": 8190},
      {"step_id": 3, "success": false, "error": "ElementNotFound: ...",
       "error_capture_key": "captures/exec_01HK.../step3.png"},
      {"step_id": 4, "success": true,  "duration_ms": 24110}
    ]
  }
}
```

## 4. 기존 코드와의 매핑

[core/workflow_engine.py](../../../core/workflow_engine.py) 의 `ExecutionReport` / `StepResult` 는 이미 이 payload 와 거의 1:1. Agent 쪽에서는 **직렬화 레이어만** 새로 쓰면 된다 — 핵심 엔진은 수정 없음.

| 기존 클래스 | 프로토콜 매핑 |
|---|---|
| `WorkflowEngine.run_session()` | `execution.start` 수신 시 호출 |
| `WorkflowEngine.pause/resume/stop()` | `execution.cancel` 등에서 호출 |
| `ExecutionReport` | `execution.result` payload |
| `StepResult` | `execution.result.step_results[*]` |
| `CodeSandbox` stdout | `execution.log` 로 라인 스트림 |

이 매핑을 수행할 얇은 어댑터가 앞으로 추가될 `agent/runner.py` 의 주 역할.

## 5. 오류 처리

- **네트워크 단절**: Agent 는 로컬 큐에 이벤트를 누적, WS 재연결 후 `last_event_id` 기반으로 재전송.
- **버전 불일치**: `agent.hello` 응답이 `upgrade_required=true` 면 업그레이드 후 재기동.
- **인증 실패**: 401 수신 시 토큰 폐기 후 Device Flow 재시작.

## 6. 보안

- TLS 강제, 인증서 pinning 은 1차에서는 미적용 (추후 고려).
- 서버 → Agent 명령은 모두 서명된 payload (HMAC-SHA256, 서버 보유 키) — 토큰 탈취 시에도 실행 지시를 위조하지 못하게. (v0.1 에서 도입, v0 은 토큰 인증만)
- Agent 는 허용된 `session_id` 만 받아 실행 — 서버가 발급한 `execution.start` 외에는 어떤 외부 요청도 실행하지 않음.

## 7. 버전 관리 정책

- `v0`: MVP. 깨질 수 있음. 클로즈드 베타까지 허용.
- `v1`: Pro 정식 출시 시 고정. 이후 호환성 유지 (마이너 변경은 `payload` 내 optional 필드 추가만).

## 8. 미결 항목

- [ ] 실행 중 Agent ↔ UI (PyQt6 데스크톱) 간의 로컬 IPC 도 이 프로토콜을 재사용할지, 별도로 할지.
- [ ] 스케줄러가 Agent 가 오프라인일 때 실행 지시를 큐잉하고 복귀 시 배달하는 구체 전략 (At-least-once 보장).
- [ ] AI 프록시 경로: Agent 가 AI 호출을 로컬(CLI) 로 할지, 서버 프록시로 할지 실행 시작 시점에 결정하는 방식.
