# SPDX-License-Identifier: AGPL-3.0-or-later
"""ohdo Local Agent.

Windows PC 에 설치되어 클라우드 Control Plane 과 통신하는 경량 트레이 앱.

0.4.0 (M2.10): per-session `requirements` 자동설치. session_snapshot 에
`requirements: [...]` 를 넣으면 agent 가 pip install --target 으로
`%APPDATA%/ohdo/packages/<sha256>/` 에 설치 후 sys.path 주입. 콘텐츠 해시
캐시로 재실행 시 skip.

0.3.1 (M2.9.1): 캡처 업로드 복구. agent 런타임에 mss 가 없어 실 스크린샷 저장
에 실패하던 문제 수정. runner 가 자체 `_capture_desktop_png` 로 PNG 저장 후
업로드. core 의 `_capture_error_screen` 경로는 `screenshot_on_error=False` 로 비활성.

0.3.0 (M2.9): embedded Python 에 pip + pywinauto/pyautogui/selenium/mss
사전 설치. 설치본에서 데스크톱·웹 자동화 기본 라이브러리 바로 사용 가능.

0.2.0 (M2.8): embedded Python 3.12 동반 → user code subprocess 가
번들 exe 를 재귀 spawn 하던 M2.7 문제 해소. 이제 설치본에서 실 RPA
코드 실행 + mid-run cancel 이 정상 작동.

0.1.0 (M2): device flow 인증 + WS 핸드셰이크 + execution lifecycle
(start/accepted/progress/result/cancel) + log 스트리밍 + 에러 스크린샷 업로드.
"""

__version__ = "0.4.0"
