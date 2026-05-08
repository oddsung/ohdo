# SPDX-License-Identifier: AGPL-3.0-or-later
"""
브라우저(Chrome/Selenium) RPA 테스트 케이스

Selenium 기반 웹 자동화 기능을 테스트합니다:
- ChromeDriver 연결
- 페이지 탐색
- 요소 찾기/클릭
- JavaScript 실행
- WindowInspector의 브라우저 요소 코드 생성

실행:
    cd ai_rpa_solution
    python -m tests.test_runner --suite browser
"""

from tests.test_runner import TestCase


class BrowserTest(TestCase):
    suite = "browser"

    def __init__(self):
        super().__init__()
        self._driver = None

    def _create_driver(self):
        """Chrome WebDriver 생성"""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        options = Options()
        options.add_experimental_option("detach", True)
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        try:
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            service = Service(ChromeDriverManager().install())
            self._driver = webdriver.Chrome(service=service, options=options)
        except ImportError:
            # webdriver_manager 없으면 기본 ChromeDriver 사용
            self._driver = webdriver.Chrome(options=options)

        return self._driver

    def _quit_driver(self):
        """드라이버 종료"""
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    def setup(self):
        self.require_package("selenium")

    def teardown(self):
        self._quit_driver()

    # ── 테스트 메서드 ──

    def test_01_open_browser(self):
        """Chrome 브라우저 열기 및 페이지 로드"""
        self.step("ChromeDriver 생성")
        driver = self._create_driver()
        self.assert_not_none(driver, "WebDriver가 생성되어야 합니다")

        self.step("Google 페이지 로드")
        driver.get("https://www.google.com")
        self.wait(2.0, "페이지 로드 대기")

        self.step("페이지 제목 확인")
        title = driver.title
        self.log(f"페이지 제목: {title}")
        self.assert_true(len(title) > 0, "페이지 제목이 있어야 합니다")
        self.capture("browser_google")

    def test_02_find_elements(self):
        """Selenium으로 요소 찾기"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        driver = self._create_driver()
        driver.get("https://www.google.com")
        self.wait(2.0)

        self.step("검색창 요소 찾기")
        wait = WebDriverWait(driver, 10)
        try:
            search_box = wait.until(EC.presence_of_element_located((By.NAME, "q")))
            self.assert_not_none(search_box, "Google 검색창이 있어야 합니다")
            self.log("검색창 발견")
        except Exception:
            # Google이 차단하는 경우 대비
            search_box = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "textarea, input[type='text']"))
            )
            self.assert_not_none(search_box, "검색 입력 요소가 있어야 합니다")

        self.step("텍스트 입력")
        search_box.send_keys("RPA automation test")
        self.wait(0.5)
        self.capture("browser_search_typed")

    def test_03_javascript_execution(self):
        """JavaScript 실행 테스트"""
        driver = self._create_driver()
        driver.get("https://www.google.com")
        self.wait(2.0)

        self.step("JavaScript로 제목 가져오기")
        js_title = driver.execute_script("return document.title;")
        self.assert_true(len(js_title) > 0, "JS로 제목을 가져올 수 있어야 합니다")
        self.log(f"JS 제목: {js_title}")

        self.step("JavaScript로 요소 생성")
        driver.execute_script("""
            var div = document.createElement('div');
            div.id = 'rpa-test-div';
            div.textContent = 'RPA Test Element';
            div.style.cssText = 'position:fixed;top:10px;right:10px;background:yellow;padding:10px;z-index:9999;';
            document.body.appendChild(div);
        """)
        self.wait(0.5)

        from selenium.webdriver.common.by import By

        test_div = driver.find_element(By.ID, "rpa-test-div")
        self.assert_equal(test_div.text, "RPA Test Element", "JS로 생성한 요소 텍스트 확인")
        self.capture("browser_js_element")

    def test_04_win_inspector_browser_code_gen(self):
        """WindowInspector의 브라우저 요소 코드 생성 검증 (로직만 테스트)"""
        self.step("WindowInspector 로드")
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core.win_inspector import WindowInspector

        inspector = WindowInspector()

        self.step("브라우저 요소 → Selenium 코드 생성 테스트")
        # 브라우저 요소 시뮬레이션 데이터
        browser_element = {
            "control_type": "Button",
            "name": "로그인",
            "automation_id": "loginBtn",
            "class_name": "button",
            "rect": {"left": 100, "top": 200, "width": 80, "height": 30},
            "parent_window_title": "Google Chrome",
            "is_browser": True,
            "browser_type": "Chrome",
        }
        text = inspector.get_element_info_text(browser_element)
        self.assert_contains(text, "Selenium", "브라우저 요소는 Selenium 코드를 생성해야 합니다")
        self.assert_contains(text, "loginBtn", "automation_id가 포함되어야 합니다")
        self.log(f"생성된 Selenium 코드 길이: {len(text)}자")

        self.step("비인터랙티브 요소 → JS click 코드 생성 테스트")
        text_element = {
            "control_type": "Text",
            "name": "메뉴항목",
            "automation_id": "",
            "class_name": "span",
            "rect": {"left": 50, "top": 100, "width": 60, "height": 20},
            "parent_window_title": "Google Chrome",
            "is_browser": True,
            "browser_type": "Chrome",
        }
        text = inspector.get_element_info_text(text_element)
        self.assert_contains(text, "execute_script", "Text 요소는 JS click을 사용해야 합니다")
        self.assert_contains(
            text, "visibility_of_element_located", "visibility 대기를 사용해야 합니다"
        )

        self.step("데스크톱 요소 → pywinauto 코드 생성 테스트")
        desktop_element = {
            "control_type": "Button",
            "name": "확인",
            "automation_id": "btnOK",
            "class_name": "Button",
            "rect": {"left": 300, "top": 400, "width": 80, "height": 30},
            "parent_window_title": "설정",
            "is_browser": False,
            "detected_backend": "uia",
            "recommended_backend": "uia",
        }
        text = inspector.get_element_info_text(desktop_element)
        self.assert_contains(text, "pywinauto", "데스크톱 요소는 pywinauto 코드를 생성해야 합니다")
        self.assert_contains(text, "btnOK", "automation_id가 포함되어야 합니다")


if __name__ == "__main__":
    from tests.test_runner import TestRunner

    runner = TestRunner(suite_name="browser")
    runner.add_test_class(BrowserTest)
    result = runner.run()
    runner.save_results(result)
