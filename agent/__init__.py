"""ohdo Local Agent.

Windows PC 에 설치되어 클라우드 Control Plane 과 통신하는 경량 트레이 앱.

0.3.0 (M2.9): embedded Python 에 pip + pywinauto/pyautogui/selenium/mss
사전 설치. 설치본에서 데스크톱·웹 자동화 기본 라이브러리 바로 사용 가능.
M2.6 의 실제 화면 스크린샷도 mss 로 활성화.

0.2.0 (M2.8): embedded Python 3.12 동반 → user code subprocess 가
번들 exe 를 재귀 spawn 하던 M2.7 문제 해소. 이제 설치본에서 실 RPA
코드 실행 + mid-run cancel 이 정상 작동.

0.1.0 (M2): device flow 인증 + WS 핸드셰이크 + execution lifecycle
(start/accepted/progress/result/cancel) + log 스트리밍 + 에러 스크린샷 업로드.
"""

__version__ = "0.3.0"
