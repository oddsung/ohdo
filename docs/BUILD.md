<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Windows 설치본 빌드 가이드 (Phase E)

`desktop_v3` (Electron + React) 설치본을 만드는 절차. 설치본은 **Electron 앱 + frozen
Python 브리지**(api_server + core) 두 조각으로 구성되며, Python 이 설치되지 않은 PC 에서도
동작한다 (handoff §46/§64).

```
ohdo-0.1.0-setup.exe (NSIS)
└─ 설치 후
   ├─ ohdo.exe                         # Electron 메인
   └─ resources/pybridge/ohdo-bridge.exe   # PyInstaller onedir 로 freeze 된 FastAPI 브리지
```

Electron 메인이 시작 시 `ohdo-bridge.exe --port <p> --data-dir <userData>/data
--config-dir <userData>/config` 를 spawn 하고 stdout 의 `OHDO_API_READY {json}` 한 줄을
기다려 포트/토큰을 확정한다 (`src/main/index.ts`).

> **검증 상태 (2026-05-31, handoff §64)**: 이 개발 환경(Windows)에서 1~3단계를 실제로 돌려
> ① freeze 성공 ② frozen `ohdo-bridge.exe` 단독 부팅 + `/health`·`/sessions`·`/environment`
> 응답 확인 ③ `electron-builder --dir` 로 `resources/pybridge/ohdo-bridge.exe` 동봉 확인(exit 0)
> 까지 통과했다. **GUI 실행 + NSIS 설치본 실측은 사용자 머신 필요** (이 환경은 GUI 불가).

---

## 0. 사전 준비 (1회)

| 도구 | 용도 | 확인 |
|------|------|------|
| [`uv`](https://docs.astral.sh/uv/) | Python 환경 + PyInstaller | `uv --version` |
| Node 20+ / npm | Electron 빌드 | `node --version` |

> ⚠️ **인터프리터는 `.venv` 다 (루트의 `venv/` 아님).** `venv/` 는 구버전 잔재로
> `fastapi`/`uvicorn` 등 브리지 의존성이 빠져 있어 `api_server` 테스트가 깨진다.
> 모든 명령은 `.venv` 기준이며, `uv sync` 가 `.venv` 를 관리한다.

PyInstaller 는 `[project.optional-dependencies]` 의 `build` extra 로 선언돼 있다:

```powershell
# 프로젝트 루트에서
uv sync --extra build          # .venv 에 pyinstaller 설치 (+ 평소 dev 도구는 --extra dev 동반 권장)
cd desktop_v3
npm install                    # Electron / electron-builder / 의존성 (최초 1회, electron ~136MB 다운로드)
cd ..
```

---

## 1. Python 브리지 freeze

프로젝트 **루트**에서 (spec 이 `os.getcwd()` 를 루트로 가정):

```powershell
uv run --extra build pyinstaller desktop_v3/build/ohdo-bridge.spec --noconfirm
```

산출물: `dist/ohdo-bridge/` (onedir — `ohdo-bridge.exe` + `_internal/`).

**freeze 직후 단독 동작 검증** (Electron 없이 브리지만 떠보는 스모크 테스트):

```powershell
$env:OHDO_API_TOKEN = "smoketest"
dist\ohdo-bridge\ohdo-bridge.exe --port 9123
# 기대 출력 (1~2초 내):
#   OHDO_API_READY {"port": 9123, "token": "smoketest"}
#   INFO:     Application startup complete.
```

다른 터미널에서:

```powershell
curl.exe http://127.0.0.1:9123/health
# {"status":"ok",...,"auth_required":true}
curl.exe -H "Authorization: Bearer smoketest" http://127.0.0.1:9123/environment
# {"success":true,"system_info":{...}}   ← core 스캐너가 frozen 에서 동작
```

확인 후 `Ctrl+C` 또는 `taskkill /F /IM ohdo-bridge.exe`.

> ImportError 로 즉시 죽으면 hidden import 누락이다. 콘솔의 누락 모듈명을
> `desktop_v3/build/ohdo-bridge.spec` 의 `hiddenimports` 에 추가하고 다시 freeze.
> (배포명과 import 모듈명이 다른 경우 주의 — 예: PyPI `pywinpty` → import 는 `winpty`.)

---

## 2. 브리지를 동봉 위치로 복사

> ⚠️ **`build/pybridge/` 가 이전 freeze 잔재인 채로 3단계(dist)로 가지 말 것** — 옛 spec
> 산출물에는 `_internal/config/settings.json`(빌드 머신 API 키)이 들어 있을 수 있다
> (2026-08-13 §84 에서 실제로 근접사고). §1 재freeze 후 반드시 이 복사 단계를 다시 수행하고,
> `_internal/config/` 에 `default_settings.json`+`prompts.json` 만 있는지 확인.

`electron-builder` 가 `extraResources` 로 `build/pybridge` → `resources/pybridge` 를 동봉한다.
`dist/ohdo-bridge/` **내용물**을 `desktop_v3/build/pybridge/` 에 넣는다 (폴더가 아니라 내용물 —
결과가 `desktop_v3/build/pybridge/ohdo-bridge.exe` 가 되어야 함):

```powershell
Remove-Item desktop_v3\build\pybridge -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory desktop_v3\build\pybridge | Out-Null
Copy-Item dist\ohdo-bridge\* desktop_v3\build\pybridge\ -Recurse -Force
Test-Path desktop_v3\build\pybridge\ohdo-bridge.exe   # → True
```

`build/pybridge/` 와 `dist/` 는 `.gitignore` 대상이라 커밋되지 않는다.

---

## 3. Electron 설치본 빌드

```powershell
cd desktop_v3
npm run dist          # → release/ohdo-0.1.0-setup.exe (NSIS 설치본)
# 또는 설치본 없이 폴더만:
npm run dist:dir      # → release/win-unpacked/ohdo.exe
```

산출물: `desktop_v3/release/` (gitignore 대상).

---

## 4. 실측 체크리스트 (설치본 GUI — 이 개발 환경에선 불가, 사용자 머신 필요)

- [ ] 설치본 실행 → 메인 창 + 브리지 spawn 성공 (작업관리자에 `ohdo-bridge.exe`).
- [ ] 세션 생성 → 자연어 요청 → AI 코드 생성 (CLI AI 엔진이 설치/로그인 돼 있어야 함).
- [ ] 세션이 `%APPDATA%\ohdo\data` 에 저장되는지 (번들 내부 아님).
- [ ] 설정 다이얼로그에서 값 변경 → `%APPDATA%\ohdo\config\settings.json` 에 기록되는지
      (handoff §81 — 번들 내부 `_internal/config` 아님. API 키 입력 후 재설치해도 유지돼야 함).
- [ ] 설치본의 `resources/pybridge/_internal/config/` 에 `settings.json` 이 **없는지**
      (있다면 빌드 머신의 API 키가 동봉된 것 — spec 회귀, 배포 금지).
- [ ] 앱 종료 시 `ohdo-bridge.exe` 도 함께 종료 (좀비 프로세스 없음).
- [ ] (repo public + 첫 릴리스 후) 구버전 설치 → 앱 시작 ~10초 뒤 업데이트 배너 →
      "재시작하여 업데이트" → 새 버전으로 재기동 (handoff §82 electron-updater).
- [ ] §58~§63 기능 실측 (온보딩 / 캡처 / 시크릿 / 녹화 review 등) — `pending_gui_verification`.

---

## 5. 알려진 한계 / 후속 작업

- **코드 서명 없음**: 설치/첫 실행 시 Windows SmartScreen 경고가 뜬다. **2026-08-13 배포
  재결정(handoff §81): v1.0 은 의도적으로 미서명 출시** — README 에 경고 안내 문구를 넣고,
  서명(SignPath OSS / Azure Trusted Signing / OV)은 사용자 확보 후 도입.
- ~~자동 업데이트 미구성~~ → **도입 (handoff §82)**: `electron-updater` + GitHub Releases
  provider (`build.publish` = github oddsung/ohdo). packaged 앱이 시작 10초 후 + 4시간 간격으로
  `latest.yml` 을 확인해 자동 다운로드 → renderer 배너("재시작하여 업데이트") → `quitAndInstall`
  (배너 무시 시 앱 종료 때 자동 설치). 미서명(§81)이라도 동작. dev 는 자동 skip.
  **repo 가 private 인 동안엔 확인이 404 로 조용히 실패** — public 전환 + 첫 릴리스 후 활성화.
  릴리스 업로드: `npm run dist:publish` (`GH_TOKEN` env 필요 — setup.exe + latest.yml + blockmap
  을 GitHub Release 에 올림. `npm run dist` 는 `--publish never` 로 로컬 빌드만).
- ~~설정(config) 영속성~~ → **해결 (handoff §81)**: 브리지 `--config-dir` 지원 —
  `settings.json` 읽기/쓰기는 `%APPDATA%\ohdo\config\` (first-run 시 디렉터리 생성 + 기존
  settings.json 1회 이관, 환경 스캔 캐시도 동일 위치). `default_settings.json`/`prompts.json`
  은 개발자 유지 콘텐츠라 항상 번들에서 읽는다 (앱 업데이트가 새 프롬프트를 전달).
  spec 은 config 를 통째 동봉하지 않고 위 2개 파일만 명시 동봉 — **빌드 머신의
  `config/settings.json`(API 키 포함, gitignore 대상)이 설치본에 유출되지 않게** (test_247).
- **freeze 크기**: pandas/opencv/PySide6 제외에도 onedir 가 수백 MB. 필요 시 spec `excludes`
  추가로 다이어트 가능 (단, hidden import 깨지지 않게 검증 필수).

---

## 6. 트러블슈팅

- **`Cannot create symbolic link ... winCodeSign\...\darwin\...\libcrypto.dylib`**:
  electron-builder 가 `winCodeSign` 캐시(.7z)를 풀 때 macOS 용 dylib **심볼릭 링크**를
  만들려다 권한 부족으로 실패. Windows 에서 비관리자 계정은 기본적으로 symlink 생성 불가.
  대부분 재시도로 통과하지만(이 환경 검증 시 `--dir` 는 exit 0), NSIS 빌드가 막히면:
  **Windows 설정 → 개인 정보 및 보안 → 개발자용 → 개발자 모드 ON** (비관리자 symlink 허용)
  후 재빌드. 코드 서명을 안 하므로 darwin 도구 자체는 실제로 불필요.
- **frozen exe 가 `--port` 후 즉시 종료 + 콘솔에 ImportError**: hidden import 누락 →
  §1 의 단독 실행으로 누락 모듈 확인 후 spec 보강.
- **`ohdo-bridge.exe` not found (설치본 실행 시)**: 2단계 복사 누락 — `build/pybridge/` 가
  비어 있으면 `extraResources` 가 빈 폴더만 동봉한다. `Test-Path` 로 확인 후 재빌드.
- **포트 충돌**: 브리지는 8765 부터 +1 씩 최대 10회 fallback (`api_server/__main__.py`).
  Electron 도 빈 포트를 미리 골라 넘기므로 보통 문제 없음.

---

## 빌드 의존성 요약

- Python freeze: `pyinstaller>=6.0` (`pyproject.toml` `[project.optional-dependencies].build`).
- spec: `desktop_v3/build/ohdo-bridge.spec` (hidden import / datas / excludes).
- entry: `desktop_v3/build/bridge_entry.py` (`api_server.__main__.main` 호출).
- Electron: `desktop_v3/package.json` `build` 블록 (appId `ai.ohdo.desktop`, NSIS x64,
  extraResources `build/pybridge`→`pybridge`).
- spawn 분기: `desktop_v3/src/main/index.ts` `bridgeCommand()` (packaged/dev/`OHDO_PYTHON`).
</content>
</invoke>
