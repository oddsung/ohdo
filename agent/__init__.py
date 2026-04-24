"""ohdo Local Agent.

Windows PC 에 설치되어 클라우드 Control Plane 과 통신하는 경량 트레이 앱.

0.2.0 (M2.8): embedded Python 3.12 동반 → user code subprocess 가
번들 exe 를 재귀 spawn 하던 M2.7 문제 해소. 이제 설치본에서 실 RPA
코드 실행 + mid-run cancel 이 정상 작동.

0.1.0 (M2): device flow 인증 + WS 핸드셰이크 + execution lifecycle
(start/accepted/progress/result/cancel) + log 스트리밍 + 에러 스크린샷 업로드.
"""

__version__ = "0.2.0"
