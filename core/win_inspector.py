"""
Windows UI 인스펙터

pywinauto를 사용하여 실행 중인 윈도우와 UI 컨트롤을 검사합니다.
AI 코드 생성 시 윈도우 컨트롤 정보를 컨텍스트로 제공합니다.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# pywinauto가 없어도 앱 실행은 가능하도록 lazy import
_pywinauto_available = False
try:
    import pywinauto
    from pywinauto import Desktop
    _pywinauto_available = True
except ImportError:
    logger.warning("pywinauto가 설치되어 있지 않습니다. UI 인스펙터 기능이 비활성화됩니다.")


class WindowInspector:
    """
    Windows UI 인스펙터.

    현재 실행 중인 윈도우와 UI 컨트롤을 검사하여
    AI 코드 생성에 필요한 컨텍스트 정보를 제공합니다.
    """

    def __init__(self):
        self._backend = "uia"  # 기본: UI Automation (modern apps)

    @property
    def is_available(self) -> bool:
        return _pywinauto_available

    def list_windows(self) -> list[dict]:
        """
        현재 실행 중인 가시적 윈도우 목록을 반환합니다.

        Returns:
            [{title, handle, process_id, class_name, rect}, ...]
        """
        if not _pywinauto_available:
            return []

        try:
            desktop = Desktop(backend=self._backend)
            windows = []

            for win in desktop.windows():
                try:
                    title = win.window_text()
                    if not title or not win.is_visible():
                        continue

                    rect = win.rectangle()
                    windows.append({
                        "title": title,
                        "handle": win.handle,
                        "class_name": win.class_name(),
                        "rect": {
                            "left": rect.left,
                            "top": rect.top,
                            "right": rect.right,
                            "bottom": rect.bottom,
                            "width": rect.width(),
                            "height": rect.height()
                        }
                    })
                except Exception:
                    continue

            return windows

        except Exception as e:
            logger.error(f"윈도우 목록 조회 실패: {e}")
            return []

    def inspect_window(
        self,
        title: str = None,
        handle: int = None,
        max_depth: int = 3,
        max_controls: int = 50
    ) -> dict:
        """
        특정 윈도우의 UI 컨트롤 트리를 추출합니다.

        Args:
            title: 윈도우 제목 (부분 매칭)
            handle: 윈도우 핸들
            max_depth: 탐색 깊이 제한
            max_controls: 최대 컨트롤 수 제한

        Returns:
            {window_title, controls: [{type, name, automation_id, rect, children}, ...]}
        """
        if not _pywinauto_available:
            return {"error": "pywinauto가 설치되어 있지 않습니다."}

        try:
            app = pywinauto.Application(backend=self._backend)

            if handle:
                app.connect(handle=handle)
            elif title:
                app.connect(title_re=f".*{title}.*", timeout=3)
            else:
                return {"error": "title 또는 handle을 지정해주세요."}

            window = app.top_window()
            window_title = window.window_text()

            controls = []
            self._collect_controls(window, controls, depth=0,
                                   max_depth=max_depth,
                                   max_controls=max_controls)

            return {
                "window_title": window_title,
                "window_class": window.class_name(),
                "window_rect": self._rect_to_dict(window.rectangle()),
                "control_count": len(controls),
                "controls": controls
            }

        except pywinauto.findwindows.ElementNotFoundError:
            return {"error": f"윈도우를 찾을 수 없습니다: {title or handle}"}
        except Exception as e:
            logger.error(f"윈도우 검사 실패: {e}")
            return {"error": str(e)}

    def inspect_foreground_window(self, max_depth: int = 3, max_controls: int = 50) -> dict:
        """
        현재 포그라운드(최상위) 윈도우를 검사합니다.
        """
        if not _pywinauto_available:
            return {"error": "pywinauto가 설치되어 있지 않습니다."}

        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                return self.inspect_window(handle=hwnd,
                                          max_depth=max_depth,
                                          max_controls=max_controls)
            return {"error": "포그라운드 윈도우를 가져올 수 없습니다."}
        except Exception as e:
            return {"error": str(e)}

    def get_control_info_text(self, window_info: dict) -> str:
        """
        윈도우 검사 결과를 AI 프롬프트에 포함할 텍스트로 변환합니다.
        """
        if "error" in window_info:
            return f"[윈도우 검사 오류: {window_info['error']}]"

        lines = [
            f"## 대상 윈도우: {window_info.get('window_title', '?')}",
            f"클래스: {window_info.get('window_class', '?')}",
            f"컨트롤 수: {window_info.get('control_count', 0)}",
            "",
            "### UI 컨트롤 목록:"
        ]

        for ctrl in window_info.get("controls", []):
            indent = "  " * ctrl.get("depth", 0)
            ctrl_type = ctrl.get("control_type", "Unknown")
            name = ctrl.get("name", "")
            auto_id = ctrl.get("automation_id", "")
            rect = ctrl.get("rect", {})

            display = f"{indent}- [{ctrl_type}]"
            if name:
                display += f' "{name}"'
            if auto_id:
                display += f" (id={auto_id})"
            if rect:
                display += f" @ ({rect.get('left', 0)},{rect.get('top', 0)})"

            lines.append(display)

        return "\n".join(lines)

    def get_element_info_text(self, element_info: dict) -> str:
        """
        피커로 선택된 단일 요소 정보를 AI 프롬프트에 포함할 텍스트로 변환합니다.
        브라우저 요소면 Selenium, 데스크톱 요소면 pywinauto 코드 예시를 생성합니다.
        """
        is_browser = element_info.get("is_browser", False)
        browser_type = element_info.get("browser_type", "")

        if is_browser:
            return self._get_browser_element_info_text(element_info)
        else:
            return self._get_desktop_element_info_text(element_info)

    def _get_browser_element_info_text(self, element_info: dict) -> str:
        """브라우저 요소 → Selenium 코드 생성"""
        ctrl_type = element_info.get("control_type", "Unknown")
        name = element_info.get("name", "")
        auto_id = element_info.get("automation_id", "")
        class_name = element_info.get("class_name", "")
        rect = element_info.get("rect", {})
        parent_title = element_info.get("parent_window_title", "")
        browser_type = element_info.get("browser_type", "Browser")
        # 피커에서 미리 구성된 로케이터 후보 (있으면 우선 사용)
        picker_locators: list[tuple[str, str]] = element_info.get("locator_candidates", [])

        lines = [
            f"## 선택된 UI 요소 (브라우저: {browser_type})",
            f"- **타입**: {ctrl_type}",
            f"- **자동화 방식**: Selenium (DOM 직접 제어)",
        ]
        if name:
            lines.append(f'- **텍스트/이름**: "{name}"')
        if auto_id:
            lines.append(f"- **HTML ID**: {auto_id}")
        if class_name:
            lines.append(f"- **클래스**: {class_name}")
        if rect:
            lines.append(
                f"- **위치**: ({rect.get('left', 0)}, {rect.get('top', 0)}) "
                f"{rect.get('width', 0)}×{rect.get('height', 0)}"
            )
        if parent_title:
            lines.append(f"- **브라우저 창 제목**: {parent_title}")

        lines.append("")
        lines.append("### 코드 생성 컨텍스트:")
        lines.append("> **브라우저 요소**: pywinauto 대신 **Selenium**을 사용하세요.")
        lines.append("> Selenium은 좌표 클릭 없이 DOM 요소를 직접 제어하므로 훨씬 안정적입니다.")
        lines.append("")

        # control_type에 따른 클릭 전략 분류
        # - 직접 클릭 가능한 인터랙티브 요소: element_to_be_clickable + .click()
        # - 텍스트/정적 요소 (<span>, <div> 등): presence_of_element_located + JS click
        #   이유: <span> 같은 비인터랙티브 요소는 element_to_be_clickable 조건을 만족하지 못해 TimeoutException 발생
        # - 입력 요소: element_to_be_clickable + .send_keys()
        CLICK_TYPES = {"Button", "CheckBox", "RadioButton", "Hyperlink", "ComboBox", "ListItem", "MenuItem", "TabItem"}
        INPUT_TYPES = {"Edit", "Document"}
        JS_CLICK_TYPES = {"Text", "Group", "Static", "Header", "Image", "Custom", "Pane", "Unknown"}

        if ctrl_type in CLICK_TYPES:
            click_strategy = "direct"
        elif ctrl_type in INPUT_TYPES:
            click_strategy = "input"
        else:
            # Text, Group, Static 등 비인터랙티브 요소 → JS click
            click_strategy = "js"

        # 로케이터 후보 목록 생성 (피커 제공 우선, 없으면 name/id로 직접 구성)
        if picker_locators:
            locator_items = [f'("{s}", "{v.replace(chr(34), chr(92)+chr(34))}")' for s, v in picker_locators]
        else:
            locator_items = []
            if auto_id:
                locator_items.append(f'("id", "{auto_id}")')
            if name:
                safe_name = name.replace('"', '\\"').replace("'", "\\'")
                locator_items.append(f'("title", "{safe_name}")')
                locator_items.append(f'("text", "{safe_name}")')
            if not locator_items:
                locator_items.append('("css", "")  # 개발자 도구로 선택자 확인 후 수정')

        locators_str = ",\n    ".join(locator_items)

        lines.append("```python")
        lines.append("from selenium import webdriver")
        lines.append("from selenium.webdriver.common.by import By")
        lines.append("from selenium.webdriver.support.ui import WebDriverWait")
        lines.append("from selenium.webdriver.support import expected_conditions as EC")
        lines.append("from selenium.webdriver.chrome.options import Options")
        lines.append("")
        lines.append("# 방법 1: 새 브라우저 열기")
        lines.append("options = Options()")
        lines.append("options.add_experimental_option('detach', True)")
        lines.append("driver = webdriver.Chrome(options=options)")
        lines.append("")
        lines.append("# 방법 2: 이미 열린 브라우저에 연결")
        lines.append("# options.add_experimental_option('debuggerAddress', 'localhost:9222')")
        lines.append("# driver = webdriver.Chrome(options=options)")
        lines.append("")
        lines.append("")
        lines.append("def find_and_click(driver, locators, timeout=10):")
        lines.append("    \"\"\"로케이터 우선순위 순으로 요소를 찾아 클릭. off-canvas 요소는 JS click으로 자동 처리.\"\"\"")
        lines.append("    from selenium.webdriver.support.ui import WebDriverWait")
        lines.append("    from selenium.webdriver.support import expected_conditions as EC")
        lines.append("    from selenium.webdriver.common.by import By")
        lines.append("    last_err = None")
        lines.append("    for strategy, value in locators:")
        lines.append("        try:")
        lines.append("            by_map = {'id': By.ID, 'css': By.CSS_SELECTOR, 'xpath': By.XPATH}")
        lines.append("            if strategy == 'title':")
        lines.append("                by, val = By.XPATH, f'//*[@title=\"{value}\"]'")
        lines.append("            elif strategy == 'text':")
        lines.append("                by, val = By.XPATH, f'//*[not(self::script)][not(self::style)][normalize-space(.)=\"{value}\"]'")
        lines.append("            else:")
        lines.append("                by, val = by_map.get(strategy, By.XPATH), value")
        lines.append("            el = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, val)))")
        lines.append("            rect = driver.execute_script(")
        lines.append("                'var r=arguments[0].getBoundingClientRect(); return {x:r.x,y:r.y};', el)")
        lines.append("            if rect['x'] < 0 or rect['y'] < 0:")
        lines.append("                driver.execute_script('arguments[0].click()', el)")
        lines.append("            else:")
        lines.append("                try: el.click()")
        lines.append("                except Exception: driver.execute_script('arguments[0].click()', el)")
        lines.append("            return el")
        lines.append("        except Exception as e:")
        lines.append("            last_err = e")
        lines.append("    raise Exception(f'클릭 실패: {locators} / {last_err}')")
        lines.append("")
        lines.append("")

        if click_strategy == "input":
            lines.append("# 입력 요소")
            if auto_id:
                lines.append(f'element = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "{auto_id}")))')
            elif name:
                safe_name = name.replace('"', '\\"')
                lines.append(f'element = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, \'//*[@title="{safe_name}" or normalize-space(.)="{safe_name}"]\')))')
            else:
                lines.append('element = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "")))')
            lines.append("element.clear()")
            lines.append('element.send_keys("입력할 텍스트")')
        else:
            lines.append(f"# 클릭할 요소: {name or auto_id or '(선택자 직접 지정 필요)'}")
            lines.append(f"find_and_click(driver, [")
            lines.append(f"    {locators_str},")
            lines.append(f"])")

        lines.append("```")

        return "\n".join(lines)

    def _get_desktop_element_info_text(self, element_info: dict) -> str:
        """데스크톱 요소 → pywinauto 코드 생성 (기존 로직)"""
        ctrl_type = element_info.get("control_type", "Unknown")
        name = element_info.get("name", "")
        auto_id = element_info.get("automation_id", "")
        class_name = element_info.get("class_name", "")
        rect = element_info.get("rect", {})
        parent_title = element_info.get("parent_window_title", "")
        parent_class = element_info.get("parent_window_class", "")
        screen_x = element_info.get("screen_x", 0)
        screen_y = element_info.get("screen_y", 0)

        # Owner-drawn 감지: UIA/Win32에서 요소 식별 정보가 없는 경우
        # (예: Delphi FastReport TToolBar의 owner-drawn 버튼)
        # 이 경우 pywinauto child_window()로 찾을 수 없으므로 좌표 기반 클릭 사용
        is_owner_drawn = (not name and not auto_id and
                          ctrl_type in ("Window", "Pane", "TitleBar", "Custom", "")
                          and parent_title)
        if is_owner_drawn:
            return self._get_owner_drawn_element_info_text(
                element_info, ctrl_type, class_name, rect,
                parent_title, parent_class, screen_x, screen_y
            )

        # 백엔드 정보 (기본값: uia)
        detected_backend = element_info.get("detected_backend", "uia")
        recommended_backend = element_info.get("recommended_backend", "uia")

        lines = [
            "## 선택된 UI 요소 (데스크톱 앱)",
            f"- **타입**: {ctrl_type}",
            f"- **자동화 방식**: pywinauto",
        ]
        if name:
            lines.append(f'- **이름**: "{name}"')
        if auto_id:
            auto_id_is_dynamic = auto_id.isdigit()
            if auto_id_is_dynamic:
                lines.append(f"- **Automation ID**: {auto_id} ⚠️ 동적 ID (숫자만 → 윈도우 핸들, 매번 변경됨! 사용 금지)")
            else:
                lines.append(f"- **Automation ID**: {auto_id}")
        if class_name:
            lines.append(f"- **클래스**: {class_name}")
        if rect:
            lines.append(
                f"- **위치**: ({rect.get('left', 0)}, {rect.get('top', 0)}) "
                f"{rect.get('width', 0)}×{rect.get('height', 0)}"
            )

        # 백엔드 정보 표시
        lines.append(f"- **감지 백엔드**: {detected_backend}")
        lines.append(f"- **권장 백엔드**: {recommended_backend}")

        if parent_title:
            lines.append("")
            lines.append(f"### 부모 윈도우: {parent_title}")
            if parent_class:
                lines.append(f"클래스: {parent_class}")

        lines.append("")
        lines.append("### 코드 생성 컨텍스트:")

        # 권한 관련 중요 안내
        lines.append("> **⚠️ 권한 주의사항**: 대상 앱이 관리자 권한으로 실행 중이면:")
        lines.append("> - `click()` (WM 메시지): 권한 오류 발생")
        lines.append("> - `click_input()` (마우스 시뮬레이션): 권한 오류 발생")
        lines.append("> - `pyautogui.click(x, y)` (입력 시뮬레이션): **정상 동작** (UIPI 우회)")
        lines.append("> - 단, pyautogui는 **실행 시점의 요소 좌표**를 동적으로 가져와야 정확함")
        if recommended_backend == "win32":
            lines.append(f"> - 이 요소는 `{detected_backend}` 방식으로 감지됨. `backend=\"win32\"` 사용 필수.")
        lines.append("")

        # 요소 접근 코드 생성
        if recommended_backend == "win32":
            if name and class_name:
                element_selector = f'win.child_window(title="{name}", class_name="{class_name}")'
            elif class_name:
                element_selector = f'win.child_window(class_name="{class_name}", found_index=0)'
            elif name:
                element_selector = f'win.child_window(title="{name}")'
            else:
                element_selector = 'win.child_window(found_index=0)'
        else:
            # auto_id가 순수 숫자이면 윈도우 핸들(동적 값)일 가능성이 높음 → 불안정
            auto_id_is_dynamic = auto_id and auto_id.isdigit()

            if name and ctrl_type:
                element_selector = f'win.child_window(title="{name}", control_type="{ctrl_type}", found_index=0)'
            elif auto_id and not auto_id_is_dynamic:
                # 안정적인 auto_id (문자 포함: "btnOK", "txtName" 등)
                element_selector = f'win.child_window(auto_id="{auto_id}", control_type="{ctrl_type}")'
            elif class_name and ctrl_type:
                # auto_id가 동적이거나 없을 때 → class_name + control_type 조합 (안정적)
                element_selector = f'win.child_window(class_name="{class_name}", control_type="{ctrl_type}", found_index=0)'
            elif class_name:
                element_selector = f'win.child_window(class_name="{class_name}", found_index=0)'
            elif name:
                element_selector = f'win.child_window(title="{name}", found_index=0)'
            elif auto_id:
                # 동적 auto_id라도 다른 대안이 전혀 없으면 최후 수단으로 사용
                element_selector = f'win.child_window(auto_id="{auto_id}", control_type="{ctrl_type}")'
            else:
                element_selector = f'win.child_window(control_type="{ctrl_type}", found_index=0)'

        # 연결 코드 조각
        if parent_title:
            connect_line = f'Application(backend="{recommended_backend}").connect(title="{parent_title}", timeout=10)'
            window_line = f'app.window(title="{parent_title}")'
        else:
            connect_line = f'Application(backend="{recommended_backend}").connect(title="...", timeout=10)'
            window_line = 'app.top_window()'

        lines.append("```python")
        lines.append("import ctypes")
        lines.append("import ctypes.wintypes")
        lines.append("import time")
        lines.append("import pyautogui")
        lines.append("from pywinauto import Application")
        lines.append("")
        lines.append("# ★ DPI Awareness 설정 (pywinauto 좌표와 pyautogui 좌표 일치 보장)")
        lines.append("# 이 스크립트를 호출한 프로세스와 동일한 DPI 모드로 맞춤")
        lines.append("try:")
        lines.append("    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))")
        lines.append("except Exception:")
        lines.append("    try:")
        lines.append("        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE")
        lines.append("    except Exception:")
        lines.append("        pass")
        lines.append("")
        lines.append("pyautogui.FAILSAFE = False  # 모서리 이동에 의한 abort 방지")
        lines.append("")
        lines.append(f"app = {connect_line}")
        lines.append(f"win = {window_line}")
        lines.append(f"element = {element_selector}")
        lines.append("")
        lines.append("# 실행 시점의 요소 위치를 동적으로 계산")
        lines.append("rect = element.rectangle()")
        lines.append("center_x = (rect.left + rect.right) // 2")
        lines.append("center_y = (rect.top + rect.bottom) // 2")
        lines.append("print(f'요소 위치: ({center_x}, {center_y})  크기: {rect.width()}x{rect.height()}')")
        lines.append("")
        lines.append("# 대상 창을 최상위로 가져오기 (관리자 창이면 일부 실패할 수 있음)")
        lines.append("user32 = ctypes.windll.user32")
        lines.append("hwnd = win.handle")
        lines.append("user32.ShowWindow(hwnd, 9)     # SW_RESTORE")
        lines.append("user32.BringWindowToTop(hwnd)")
        lines.append("try:")
        lines.append("    user32.SetForegroundWindow(hwnd)")
        lines.append("except Exception:")
        lines.append("    pass")
        lines.append("time.sleep(0.5)  # 창 전환 대기")
        lines.append("")
        lines.append("# 클릭 좌표에 실제로 있는 창 확인")
        lines.append("pt = ctypes.wintypes.POINT(center_x, center_y)")
        lines.append("hwnd_at_pt = user32.WindowFromPoint(pt)")
        lines.append("buf = ctypes.create_unicode_buffer(256)")
        lines.append("user32.GetWindowTextW(hwnd_at_pt, buf, 256)")
        lines.append("print(f'클릭 좌표의 창: \"{buf.value}\" (hwnd={hex(hwnd_at_pt)}, 대상={hex(hwnd)})')")
        lines.append("if hwnd_at_pt != hwnd:")
        lines.append("    # 자식 창일 수 있으니 최상위 부모 확인")
        lines.append("    root = user32.GetAncestor(hwnd_at_pt, 2)  # GA_ROOT=2")
        lines.append("    if root != hwnd:")
        lines.append("        print('경고: 클릭 좌표에 다른 창이 있습니다. 대상 창이 가려져 있을 수 있습니다.')")
        lines.append("")
        lines.append("# 클릭 시도")
        lines.append("try:")
        lines.append("    element.click()  # WM 메시지 방식 (관리자 앱이면 실패)")
        lines.append("    print('클릭 성공 (WM 메시지)')")
        lines.append("except Exception as e:")
        lines.append('    if "rights" in str(e).lower() or "privilege" in str(e).lower():')
        lines.append("        print(f'WM 클릭 불가 (관리자 권한 앱): {e}')")
        lines.append("        print('pyautogui SendInput 방식으로 재시도...')")
        lines.append("        pyautogui.click(center_x, center_y)")
        lines.append("        print('pyautogui 클릭 완료')")
        lines.append("    else:")
        lines.append("        raise")
        lines.append("```")

        return "\n".join(lines)

    def _get_owner_drawn_element_info_text(
        self, element_info: dict, ctrl_type: str, class_name: str,
        rect: dict, parent_title: str, parent_class: str,
        screen_x: int, screen_y: int
    ) -> str:
        """
        Owner-drawn 컨트롤용 코드 생성.

        UIA/Win32에서 요소 식별 정보가 없는 경우 (예: Delphi FastReport TToolBar 버튼).
        pywinauto child_window()로 찾을 수 없으므로, 부모 윈도우를 전면으로 가져온 뒤
        pyautogui 좌표 기반으로 직접 클릭하는 코드를 생성합니다.
        """
        detected_backend = element_info.get("detected_backend", "uia")

        lines = [
            "## 선택된 UI 요소 (데스크톱 앱 — Owner-drawn 컨트롤)",
            f"- **타입**: {ctrl_type} (owner-drawn: UIA/Win32 자식으로 노출되지 않음)",
            f"- **자동화 방식**: pyautogui 좌표 기반 클릭",
        ]
        if class_name:
            lines.append(f"- **클래스**: {class_name}")
        if rect:
            lines.append(
                f"- **위치**: ({rect.get('left', 0)}, {rect.get('top', 0)}) "
                f"{rect.get('width', 0)}×{rect.get('height', 0)}"
            )
        lines.append(f"- **클릭 좌표 (스크린)**: ({screen_x}, {screen_y})")
        lines.append(f"- **감지 백엔드**: {detected_backend}")

        if parent_title:
            lines.append("")
            lines.append(f"### 부모 윈도우: {parent_title}")
            if parent_class:
                lines.append(f"클래스: {parent_class}")

        lines.append("")
        lines.append("### 코드 생성 컨텍스트:")
        lines.append("> **⚠️ Owner-drawn 컨트롤**: 이 요소는 UIA 접근성 트리에 노출되지 않습니다.")
        lines.append("> `child_window()` 로 찾을 수 없으므로, 부모 윈도우를 전면으로 가져온 뒤")
        lines.append("> **pyautogui 좌표 클릭**으로 조작해야 합니다.")
        lines.append("> - 부모 윈도우를 `SetForegroundWindow`로 활성화")
        lines.append("> - 요소의 스크린 좌표로 `pyautogui.click()` 실행")
        lines.append("")

        # 코드 예시 — 부모 윈도우를 전면으로 가져오고 좌표 클릭
        lines.append("```python")
        lines.append("import ctypes")
        lines.append("import ctypes.wintypes")
        lines.append("import time")
        lines.append("import pyautogui")
        lines.append("from pywinauto.findwindows import find_windows")
        lines.append("")
        lines.append("# ★ DPI Awareness 설정")
        lines.append("try:")
        lines.append("    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))")
        lines.append("except Exception:")
        lines.append("    try:")
        lines.append("        ctypes.windll.shcore.SetProcessDpiAwareness(2)")
        lines.append("    except Exception:")
        lines.append("        pass")
        lines.append("")
        lines.append("pyautogui.FAILSAFE = False")
        lines.append("")
        lines.append("user32 = ctypes.windll.user32")
        lines.append("buf = ctypes.create_unicode_buffer(256)")
        lines.append("")
        lines.append(f"# 부모 윈도우 '{parent_title}' 를 전면으로 가져오기")
        lines.append(f"target_title = \"{parent_title}\"")
        lines.append("target_hwnd = None")
        lines.append("for hwnd in find_windows(visible_only=True):")
        lines.append("    user32.GetWindowTextW(hwnd, buf, 256)")
        lines.append("    if buf.value == target_title:")
        lines.append("        target_hwnd = hwnd")
        lines.append("        break")
        lines.append("")
        lines.append("if target_hwnd:")
        lines.append("    user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE")
        lines.append("    user32.BringWindowToTop(target_hwnd)")
        lines.append("    try:")
        lines.append("        user32.SetForegroundWindow(target_hwnd)")
        lines.append("    except Exception:")
        lines.append("        pass")
        lines.append("    time.sleep(0.5)")
        lines.append("")
        lines.append(f"    # Owner-drawn 요소 좌표 클릭 (스크린 좌표)")
        lines.append(f"    click_x, click_y = {screen_x}, {screen_y}")
        lines.append("    print(f'Owner-drawn 요소 좌표 클릭: ({click_x}, {click_y})')")
        lines.append("    pyautogui.click(click_x, click_y)")
        lines.append("    print('클릭 완료')")
        lines.append("else:")
        lines.append(f"    print(f'윈도우를 찾지 못했습니다: {{target_title}}')")
        lines.append("```")

        return "\n".join(lines)

    def _collect_controls(self, element, controls: list, depth: int,
                          max_depth: int, max_controls: int):
        """재귀적으로 UI 컨트롤을 수집합니다."""
        if depth > max_depth or len(controls) >= max_controls:
            return

        try:
            children = element.children()
        except Exception:
            return

        for child in children:
            if len(controls) >= max_controls:
                break

            try:
                name = child.window_text() or ""
                ctrl_type = ""
                auto_id = ""

                try:
                    ctrl_type = child.element_info.control_type or ""
                except Exception:
                    ctrl_type = child.class_name() or ""

                try:
                    auto_id = child.element_info.automation_id or ""
                except Exception:
                    pass

                # 의미 있는 컨트롤만 수집 (이름이나 타입이 있는 것)
                if name or ctrl_type in (
                    "Button", "MenuItem", "Edit", "ComboBox",
                    "TabItem", "CheckBox", "RadioButton", "ListItem",
                    "TreeItem", "Menu", "MenuBar", "ToolBar",
                    "Hyperlink", "Text", "Image"
                ):
                    rect = self._rect_to_dict(child.rectangle())
                    controls.append({
                        "control_type": ctrl_type,
                        "name": name[:100],  # 긴 텍스트 제한
                        "automation_id": auto_id,
                        "class_name": child.class_name(),
                        "rect": rect,
                        "depth": depth
                    })

                # 하위 탐색
                self._collect_controls(child, controls, depth + 1,
                                      max_depth, max_controls)

            except Exception:
                continue

    @staticmethod
    def _rect_to_dict(rect) -> dict:
        """pywinauto Rect를 dict로 변환"""
        try:
            return {
                "left": rect.left,
                "top": rect.top,
                "right": rect.right,
                "bottom": rect.bottom,
                "width": rect.width(),
                "height": rect.height()
            }
        except Exception:
            return {}
