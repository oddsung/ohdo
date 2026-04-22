# ohdo agent

Windows PC 에 설치되어 클라우드 Control Plane 과 통신하는 경량 트레이 앱.

- 현재 단계: **M0 — 헬스체크 ping 만**
- 관련 설계: [docs/saas/architecture/02-m0-installer-and-backend.md](../docs/saas/architecture/02-m0-installer-and-backend.md)
- 전체 프로토콜 계획: [docs/saas/protocols/AGENT_PROTOCOL.md](../docs/saas/protocols/AGENT_PROTOCOL.md)
- 설치 전략: [docs/saas/installer/00-strategy.md](../docs/saas/installer/00-strategy.md)

## 로컬 개발 실행 (빌드 없이)

activation 없이 venv 의 python 을 직접 호출하는 방식 (PowerShell 실행정책 이슈 회피):

```pwsh
cd agent
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 서버 URL 지정 (기본 http://localhost:8000)
$env:OHDO_SERVER_URL = "http://localhost:8000"

.venv\Scripts\python.exe agent_main.py
```

### venv 를 활성화하고 싶을 때

```pwsh
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:OHDO_SERVER_URL = "http://localhost:8000"
python agent_main.py
```

> PowerShell 에서 `.venv\Scripts\activate` 는 cmd/bash 용이라 에러가 난다. `Activate.ps1` 을 명시적으로 호출.

- 트레이에 동그란 아이콘이 뜨면 성공.
- 아이콘 우클릭 → **Open Log Folder** 로 로그 파일 확인: `%APPDATA%\ohdo\agent.log`
- 30초마다 "ping ok" 또는 "ping failed" 가 로그에 쌓인다.

## 환경변수

| 이름 | 기본값 | 설명 |
|---|---|---|
| `OHDO_SERVER_URL` | `http://localhost:8000` | Control Plane base URL |
| `OHDO_PING_SECONDS` | `30` | 헬스체크 주기(초), 최소 5 |
| `OHDO_APPDATA` | `%APPDATA%\ohdo` | 로그/설정 폴더 오버라이드 |

## 인스톨러 빌드 (Windows 에서)

### 전제

- Python 3.10+ (64-bit)
- [Inno Setup 6+](https://jrsoftware.org/isinfo.php) 설치 — 기본 경로 `C:\Program Files (x86)\Inno Setup 6`

### 1단계: PyInstaller 번들

```pwsh
cd agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller

pyinstaller build.spec --clean --noconfirm
# → dist/ohdo-agent/ohdo-agent.exe + 동반 DLL 생성
```

`dist/ohdo-agent/ohdo-agent.exe` 를 직접 더블클릭해서 트레이에 뜨는지 먼저 확인. (이 단계에서 안 뜨면 인스톨러로 넘어가도 고장이다.)

### 2단계: Inno Setup 컴파일

```pwsh
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\ohdo-agent.iss
# → dist-installer/ohdo-agent-setup-0.0.1.exe 생성
```

### 3단계: 설치 테스트

- 생성된 `ohdo-agent-setup-0.0.1.exe` 를 실행
- 기본 설치 위치: `%ProgramFiles%\ohdo\agent`
- "Windows 시작 시 자동 실행" 체크박스는 기본 체크됨
- 설치 완료 후 재부팅하여 자동 실행 확인

### 트러블슈팅

**"PyInstaller 빌드는 되는데 exe 실행 시 창 없이 바로 꺼짐"**
- `console=False` 라 에러가 안 보임. `build.spec` 에서 `console=True` 로 바꿔서 빌드 후 cmd 에서 직접 실행 → stacktrace 확인.

**"Windows Defender 가 차단"**
- M0 에서는 코드 사이닝이 없어서 SmartScreen 경고가 뜬다. **추가 정보 → 실행** 으로 우회. 베타 오픈 전에 코드 사이닝 도입.

**"pystray 가 실행되지만 아이콘이 안 보임"**
- Windows 11 의 숨겨진 트레이 아이콘 영역 확인. 작업 표시줄 설정에서 "항상 표시" 로 전환.

**"ping failed: Connection refused"**
- `OHDO_SERVER_URL` 이 잘못되었거나 백엔드가 꺼져 있음. 백엔드 먼저 기동 ([packages/backend/README.md](../packages/backend/README.md)).

## 파일 구조

```
agent/
├── __init__.py           # 버전
├── agent_main.py         # 단일 파일 트레이 앱 (M0 범위)
├── requirements.txt      # pystray, Pillow, httpx
├── build.spec            # PyInstaller 스펙
├── installer/
│   └── ohdo-agent.iss    # Inno Setup 스크립트
├── .gitignore
└── README.md             # 이 파일
```

## 다음 마일스톤

- **M1**: Device Flow 인증 (`agent.hello`, 토큰 저장), WebSocket 연결, 트레이 메뉴에 "Sign In" 추가.
- **M2**: `core/` 모듈 번들링 → `execution.start` 수신 시 실제 워크플로우 실행.
