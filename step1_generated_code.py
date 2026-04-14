import ctypes
import ctypes.wintypes
import time
import pyautogui
from pywinauto import Application
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# === Step 1: 📌 선택된 요소: [Pane] (ID: 2167116) 클릭하고 3초 대기. (시작) ===

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

# === Step 1: 📌 선택된 요소: [Pane] (ID: 2167116) 클릭하고 3초 대기. (끝) ===


# === 웹 요소 클릭 표준 함수 정의 (규칙 준수) ===
def find_and_click(driver, locators, timeout=10):
    last_err = None
    for strategy, value in locators:
        try:
            by_map = {'id': By.ID, 'css': By.CSS_SELECTOR, 'xpath': By.XPATH}
            if strategy == 'title':
                by, val = By.XPATH, f'//*[@title="{value}"]'
            elif strategy == 'text':
                by, val = By.XPATH, f'//*[not(self::script)][not(self::style)][normalize-space(.)="{value}"]'
            else:
                by, val = by_map.get(strategy, By.XPATH), value
            el = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, val)))
            rect = driver.execute_script('var r=arguments[0].getBoundingClientRect(); return {x:r.x,y:r.y};', el)
            if rect['x'] < 0 or rect['y'] < 0:
                driver.execute_script('arguments[0].click()', el)
            else:
                try: el.click()
                except Exception: driver.execute_script('arguments[0].click()', el)
            return el
        except Exception as e:
            last_err = e
    raise Exception(f'클릭 실패: {locators} / {last_err}')


# === Step 2: 웹브라우저 실행 후 'work.wooyang.co.kr' 접속 후 3초 대기. (시작) ===

try:
    print("브라우저 실행 중...")
    # Chrome 옵션 설정 (브라우저 유지)
    chrome_options = Options()
    chrome_options.add_experimental_option('detach', True) # 스크립트 종료 후 브라우저 유지 설정

    # WebDriver 실행
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    # URL 접속
    target_url = "work.wooyang.co.kr"
    if not target_url.startswith("http"): target_url = "http://" + target_url
    driver.get(target_url)
    print(f"'{target_url}' 접속 성공")

    # 3초 대기 수행
    print("3초 대기 시작...")
    time.sleep(3)
    print("대기 완료")

except Exception as e:
    print(f"웹 자동화 실행 중 오류 발생: {e}")

# === Step 2: 웹브라우저 실행 후 'work.wooyang.co.kr' 접속 후 3초 대기. (끝) ===