import ctypes
import ctypes.wintypes
import time
import pyautogui
from pywinauto import Application

# DPI Awareness 설정 (좌표 정확도 확보)
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        pass

pyautogui.FAILSAFE = False # 마우스 모서리 이동 시 중단 방지

try:
    # DBeaver 응용 프로그램 연결 및 윈도우 지정
    app = Application(backend="uia").connect(title_re=".*DBeaver.*", timeout=10)
    win = app.window(title_re=".*DBeaver.*")
    
    # 지정된 UI 요소(Pane) 찾기
    element = win.child_window(class_name="SWT_Window0", control_type="Pane", found_index=0)

    # 대상 창을 최상위로 가져오기
    hwnd = win.handle
    ctypes.windll.user32.ShowWindow(hwnd, 9) # SW_RESTORE: 창 복원
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.5) # 창 전환 대기

    # 요소의 좌표 계산
    rect = element.rectangle()
    center_x = (rect.left + rect.right) // 2
    center_y = (rect.top + rect.bottom) // 2
    print(f"클릭 좌표: ({center_x}, {center_y})")

    # 클릭 수행
    try:
        element.click_input() # 마우스 시뮬레이션 클릭
        print("요소 클릭 성공")
    except Exception as e:
        print(f"기본 클릭 실패, pyautogui로 재시도: {e}")
        pyautogui.click(center_x, center_y)

    # 3초 대기 요청 수행
    print("3초 대기 시작...")
    time.sleep(3)
    print("대기 완료")

except Exception as e:
    print(f"자동화 실행 중 오류 발생: {e}")