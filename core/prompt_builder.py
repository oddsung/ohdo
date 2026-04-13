"""
프롬프트 빌더

세션 컨텍스트를 기반으로 AI에게 전송할 프롬프트를 구성합니다.

핵심 원칙:
- 사용자 요청을 프롬프트 최상단에 배치 (AI가 무시하지 못하도록)
- 시스템 지시문은 간결하게 맨 끝에 배치
- "코드를 반드시 생성하라"는 지시를 반복 강조
"""

import json
import logging
import platform
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PromptBuilder:
    """
    AI 프롬프트 컨텍스트 빌더.

    프롬프트 구조 (우선순위 순):
    1. 사용자 요청 (최상단 - 가장 중요)
    2. 컨텍스트 (이전 코드/스텝)
    3. 시스템 지시 (코드 생성 규칙)
    """

    def __init__(self, prompts_config: Optional[dict] = None):
        if prompts_config is None:
            prompts_file = Path(__file__).parent.parent / "config" / "prompts.json"
            if prompts_file.exists():
                with open(prompts_file, "r", encoding="utf-8") as f:
                    prompts_config = json.load(f)
            else:
                prompts_config = {}

        self.templates = prompts_config
        self.system_context = self.templates.get("system_context", "")
        self.error_recovery_template = self.templates.get("error_recovery", "")

    def build_step_prompt(
        self,
        session,
        user_request: str,
        image_paths: Optional[list[str]] = None,
        error_context: Optional[str] = None,
        window_context: Optional[str] = None,
        element_context: Optional[str] = None,
        max_history_steps: int = 5,
        project_type: str = "desktop",
        is_browser_element: bool = False
    ) -> str:
        """
        단계별 대화 프롬프트를 생성합니다.

        프롬프트 구조:
          [1] 사용자 요청 (가장 먼저!)
          [2] 이전 컨텍스트 (코드/스텝)
          [3] 코드 생성 규칙 (끝에 배치)
        """
        parts = []

        # ═══════════════════════════════════════════
        # [1] 사용자 요청을 최상단에 배치 (가장 중요!)
        # ═══════════════════════════════════════════
        parts.append(f'다음 요청에 대한 Python 코드를 즉시 작성하세요: "{user_request}"')
        parts.append("※ 요청에 포함된 ID, 비밀번호, 입력 텍스트 등 따옴표 안의 값은 공백 추가나 변경 없이 코드에 정확히 그대로 사용하세요. (@, #, % 등 특수문자로 시작하는 값 포함)")
        parts.append("※ 코드 내 주석(#으로 시작하는 줄)은 반드시 한 줄로만 작성하세요. 주석 안에 줄바꿈(\\n)을 포함하면 Python 문법 오류가 발생합니다.")
        parts.append("")

        # ═══════════════════════════════════════════
        # [2] 컨텍스트 (이전 스텝/코드)
        # ═══════════════════════════════════════════
        current_code, is_manually_edited = self._get_current_code(session)
        completed_summary = self._build_steps_summary(session, max_history_steps)

        if current_code:
            parts.append("## 현재까지 작성된 누적 코드 (이전 모든 스텝의 동작이 담겨 있음):")
            parts.append(f"```python\n{current_code}\n```")
            parts.append("")
            if is_manually_edited:
                edit_diff = self._get_last_edit_diff(session)
                parts.append("## [중요] 사용자가 위 코드를 직접 수정했습니다. 아래 변경사항을 반드시 유지하세요:")
                if edit_diff:
                    parts.append("```diff")
                    parts.append(edit_diff)
                    parts.append("```")
                    parts.append("위 diff의 '+' 줄이 최종 값입니다. '-' 줄(이전 값)로 절대 되돌리지 마세요.")
                else:
                    parts.append("위 코드의 모든 문자열 값(send_keys 인자, 비밀번호, ID, URL 등)을 한 글자도 변경하지 말고 그대로 복사하세요.")
            else:
                parts.append("⚠ 핵심 규칙: 위 코드는 이전 모든 스텝의 동작을 순서대로 포함한 누적 코드입니다.")
                parts.append("반드시 위 코드의 모든 동작을 그대로 유지하면서, 새 요청의 동작을 기존 흐름의 마지막에 추가하세요.")
                parts.append("절대로 이전 단계의 코드를 삭제하거나 주석으로 대체하거나 요약하지 마세요.")
            parts.append("새 기능은 기존 코드가 완전히 실행된 후 이어서 실행되도록 추가해야 합니다.")
            parts.append("")

        is_macos = platform.system() == "Darwin"

        if project_type == "auto" and not current_code:
            parts.append("## 통합 코드 생성 규칙 (매우 중요):")
            if is_macos:
                parts.append("하나의 자동화 세션 안에서 데스크톱 제어(AppleScript/pyautogui)와 웹 브라우저 제어(Selenium)를 얼마든지 섞어서 자유롭게 파이썬 코드를 작성하세요.")
            else:
                parts.append("하나의 자동화 세션 안에서 데스크톱 제어(pywinauto)와 웹 브라우저 제어(Selenium)를 얼마든지 섞어서 자유롭게 파이썬 코드를 작성하세요.")
            parts.append("만약 사용자의 첫 요청 의도가 너무 모호하여(예: '클릭해줘') 자동화 대상을 명확히 알 수 없다면, Python 코드를 전혀 생성하지 말고 의도를 묻는 질문(답변)만 하세요.")
            parts.append("요청이 명확하다면 즉시 파이썬 코드를 작성하세요.")
            parts.append("")

        if completed_summary:
            parts.append(f"## 이전 스텝 요약:\n{completed_summary}")
            parts.append("")

        # 이미지 첨부
        if image_paths:
            parts.append(f"## 첨부 이미지 ({len(image_paths)}장)")
            parts.append("화면 캡처를 참고하여 코드를 작성하세요.")
            parts.append("")

        # UI 자동화 가이드 (OS별 분기)
        parts.append(f"## 현재 실행 환경: {platform.system()} {platform.release()}")
        parts.append("")
        parts.extend(self._build_automation_guide(is_macos))
        parts.append("")

        # 윈도우 컨트롤 정보 (있을 경우)
        if window_context:
            parts.append(window_context)
            parts.append("")
            parts.append("위 컨트롤 정보를 활용하여 pywinauto로 자동화 코드를 작성하세요.")
            parts.append("")

        # 선택된 UI 요소 정보 (피커로 선택한 경우)
        if element_context:
            parts.append(element_context)
            parts.append("")
            if is_browser_element:
                parts.append("위 선택된 UI 요소 정보를 활용하여 해당 요소를 조작하는 Selenium 코드를 작성하세요.")
                parts.append("⚠️ 웹 요소 클릭 시 반드시 find_and_click() 함수를 정의하고 사용하세요.")
                parts.append("   - off-canvas(화면 밖, x<0) 요소는 element.click()이 ElementClickInterceptedException을 발생시킵니다.")
                parts.append("   - find_and_click()은 뷰포트 좌표를 확인하여 off-canvas 요소를 JS click으로 자동 처리합니다.")
                parts.append("   - 대기 조건은 visibility_of_element_located가 아닌 presence_of_element_located를 사용하세요.")
                parts.append("     (off-canvas 요소는 visibility 조건을 영원히 만족하지 못해 TimeoutException 발생)")
            else:
                parts.append("위 선택된 UI 요소 정보를 활용하여 해당 요소를 조작하는 pywinauto 코드를 작성하세요.")
            parts.append("제공된 예시 코드를 참고하되, 요청 내용에 맞게 수정하세요.")
            parts.append("")

        # 에러 복구
        if error_context:
            parts.append(f"## 에러 발생 - 수정된 코드 필요:")
            parts.append(f"```\n{error_context}\n```")
            parts.append("이 에러를 해결하는 수정된 전체 코드를 작성하세요.")
            parts.append("")

        # ═══════════════════════════════════════════
        # [3] 코드 생성 규칙 (간결하게)
        # ═══════════════════════════════════════════
        parts.append("## 규칙:")
        parts.append("- 반드시 ```python 코드블록을 포함하세요")
        parts.append("- 코드는 즉시 실행 가능한 완전한 형태로 작성하세요")
        parts.append("- import문, try/except, print()를 포함하세요")
        parts.append("- 설명은 2~3줄로 짧게, 한국어로 작성하세요")
        parts.append("- 질문하지 말고 바로 코드를 생성하세요")
        if current_code:
            parts.append("- [중요] 이전 스텝의 모든 코드(함수 호출, 변수, 로직)를 빠짐없이 유지하세요")
            parts.append("- [중요] 새 동작은 기존 함수 내 마지막 실행 순서에 추가하세요. 별도 함수로 분리하지 마세요")

        full_prompt = "\n".join(parts)
        logger.debug(f"프롬프트 생성 완료 ({len(full_prompt)}자)")
        return full_prompt

    def _build_automation_guide(self, is_macos: bool) -> list[str]:
        """OS별 UI 자동화 가이드를 생성합니다."""
        parts = []
        parts.append("## UI 자동화 접근법 (우선순위 순):")

        if is_macos:
            # ── macOS 가이드 ──
            parts.append("1. **AppleScript (osascript)** (최우선): macOS 앱 제어")
            parts.append("   - subprocess.run(['osascript', '-e', script])로 AppleScript 실행")
            parts.append("   - 앱 실행: tell application \"앱이름\" to activate")
            parts.append("   - 텍스트 입력: tell application \"System Events\" to keystroke \"텍스트\"")
            parts.append("   - 메뉴 클릭: tell application \"System Events\" to click menu item \"항목\" of menu \"메뉴\" of menu bar 1 of process \"앱\"")
            parts.append("   - 🌟중요: AppleScript에서 한글 입력 시 keystroke를 사용하세요 (pyautogui.typewrite는 IME 영향을 받음)")
            parts.append("2. **Selenium** (웹 자동화): Chrome 브라우저 제어")
            self._append_selenium_guide(parts)
            parts.append("3. **pyautogui** (대안): 이미지 매칭 또는 좌표 클릭")
            parts.append("   - pyautogui.click(x, y) 또는 locateOnScreen('image.png')")
            parts.append("   - 🌟중요: macOS에서 pyautogui.typewrite()는 한글 IME가 활성화되면 한글로 입력됩니다.")
            parts.append("     영문 입력이 필요하면 AppleScript keystroke를 사용하세요.")
            parts.append("4. **subprocess**: 프로그램 실행")
            parts.append("   - subprocess.Popen(['open', '-a', '앱이름'])으로 앱 실행")
            parts.append("   - subprocess.Popen(['open', 'https://url'])으로 기본 브라우저에서 URL 열기")
        else:
            # ── Windows 가이드 ──
            parts.append("1. **pywinauto** (최우선): 윈도우 컨트롤 제어 (버튼 클릭, 메뉴 선택, 텍스트 입력)")
            parts.append("   - 일반적인 앱: app = Application(backend='uia').connect(title='...')")
            parts.append("   - 🌟중요(UWP 앱 주의) Windows 11 메모장 등 UWP 앱은 Application.start() 사용을 지양하세요.")
            parts.append("     대신 subprocess.Popen()으로 먼저 실행 후 약간 대기하고, Desktop(backend='uia').window(title_re='...', found_index=0, visible_only=True)를 사용하여 바탕화면 전체에서 가시적인 윈도우를 찾아 연결하세요. (반드시 found_index=0 과 visible_only=True 포함)")
            parts.append("   - 🌟중요: UWP 앱(메모장 등) 내부의 메뉴나 버튼을 찾을 때 child_window()에 여러 요소가 매칭되는 오류가 잦습니다. 항상 child_window(title='...', control_type='...', found_index=0).invoke() 또는 click_input() 형태로 found_index=0을 필수로 넣으세요.")
            parts.append("2. **Selenium** (웹 자동화): Chrome 브라우저 제어")
            self._append_selenium_guide(parts)
            parts.append("3. **pyautogui** (대안): 이미지 매칭 또는 좌표 클릭")
            parts.append("   - pyautogui.click(x, y) 또는 locateOnScreen('image.png')")
            parts.append("4. **subprocess**: 프로그램 실행")
            parts.append("   - 🌟중요(작업 디렉토리): Program Files 등에 설치된 프로그램은 반드시 cwd 파라미터를 사용하세요:")
            parts.append("     ```python")
            parts.append("     import subprocess, os")
            parts.append("     exe_path = r'C:\\Program Files\\...\\program.exe'")
            parts.append("     subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))")
            parts.append("     ```")
            parts.append("   - cwd를 설정하지 않으면 프로그램이 DLL이나 설정 파일을 찾지 못해 실행되지 않을 수 있습니다.")
            parts.append("   - 메모장(notepad.exe) 같은 Windows 기본 프로그램은 cwd 없이도 실행 가능합니다.")

        return parts

    def _append_selenium_guide(self, parts: list[str]):
        """Selenium 웹 자동화 가이드 (공통)"""
        parts.append("   - 🌟중요(브라우저 유지): 반드시 detach 옵션을 사용하세요:")
        parts.append("     ```python")
        parts.append("     from selenium.webdriver.chrome.options import Options")
        parts.append("     options = Options()")
        parts.append("     options.add_experimental_option('detach', True)  # 스크립트 종료 후 브라우저 유지")
        parts.append("     driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)")
        parts.append("     ```")
        parts.append("   - detach=True가 없으면 스크립트가 끝날 때 Chrome이 자동으로 닫힙니다.")
        parts.append("   - 다음 스텝에서 이미 열린 브라우저를 재사용하려면 driver 객체를 유지하거나,")
        parts.append("     Chrome 실행 시 --remote-debugging-port=9222 옵션 추가 후 connect로 재연결하세요.")
        parts.append("   - 🌟중요(요소 찾기 핵심 규칙 — 모든 웹 환경 공통):")
        parts.append("     ① XPath로 텍스트 검색 시 반드시 script/style 태그 제외하세요:")
        parts.append("        잘못된 예: //*[contains(text(), 'RPA')]  ← <script> 태그의 JS 문자열도 매칭되어 클릭 실패!")
        parts.append("        올바른 예: //*[not(self::script)][not(self::style)][contains(text(), 'RPA')]")
        parts.append("     ② 버튼 클릭 후 나타나는 드롭다운/서브메뉴는 visibility_of_element_located를 사용하세요:")
        parts.append("        잘못된 예: wait.until(EC.presence_of_element_located(...))  ← hidden 요소도 즉시 반환!")
        parts.append("        올바른 예: wait.until(EC.visibility_of_element_located(...))  ← 실제 화면에 보일 때까지 대기")
        parts.append("     ③ 비인터랙티브 텍스트 요소(<span>, <div>, <li> 등) 클릭 시 JavaScript click을 사용하세요:")
        parts.append("        element = wait.until(EC.visibility_of_element_located((By.XPATH, '//*[not(self::script)][not(self::style)][contains(text(), \"메뉴명\")]')))")
        parts.append("        driver.execute_script(\"arguments[0].click()\", element)  # JS click으로 안정적 클릭")
        parts.append("     ④ <button>, <a>, <input> 같은 인터랙티브 요소는 element_to_be_clickable + .click()을 사용하세요:")
        parts.append("        element = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), \"확인\")]')))")
        parts.append("        element.click()")
        parts.append("     ⑤ 로케이터 안정성 우선순위: id속성 > title속성 > aria-label > 텍스트내용")
        parts.append("        - title 속성: 사이드바·트리 메뉴에서 필수 (텍스트가 <span> 자식에 있어 text() XPath가 실패하는 구조)")
        parts.append("          //*[@title=\"메뉴명\"]   ← zTree, axBoot 등 SPA 프레임워크 메뉴에서 가장 안정적")
        parts.append("     ⑥ 웹 요소 클릭 표준 함수: 모든 웹 자동화 코드에 아래 find_and_click()을 항상 포함하세요.")
        parts.append("        off-canvas(화면 밖 x<0) 요소도 JS click으로 자동 처리되므로 클릭 실패가 없습니다:")
        parts.append("        ```python")
        parts.append("        def find_and_click(driver, locators, timeout=10):")
        parts.append("            from selenium.webdriver.support.ui import WebDriverWait")
        parts.append("            from selenium.webdriver.support import expected_conditions as EC")
        parts.append("            from selenium.webdriver.common.by import By")
        parts.append("            last_err = None")
        parts.append("            for strategy, value in locators:")
        parts.append("                try:")
        parts.append("                    by_map = {'id': By.ID, 'css': By.CSS_SELECTOR, 'xpath': By.XPATH}")
        parts.append("                    if strategy == 'title':")
        parts.append("                        by, val = By.XPATH, f'//*[@title=\"{value}\"]'")
        parts.append("                    elif strategy == 'text':")
        parts.append("                        by, val = By.XPATH, f'//*[not(self::script)][not(self::style)][normalize-space(.)=\"{value}\"]'")
        parts.append("                    else:")
        parts.append("                        by, val = by_map.get(strategy, By.XPATH), value")
        parts.append("                    el = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, val)))")
        parts.append("                    rect = driver.execute_script(")
        parts.append("                        'var r=arguments[0].getBoundingClientRect(); return {x:r.x,y:r.y};', el)")
        parts.append("                    if rect['x'] < 0 or rect['y'] < 0:")
        parts.append("                        driver.execute_script('arguments[0].click()', el)")
        parts.append("                    else:")
        parts.append("                        try: el.click()")
        parts.append("                        except Exception: driver.execute_script('arguments[0].click()', el)")
        parts.append("                    return el")
        parts.append("                except Exception as e:")
        parts.append("                    last_err = e")
        parts.append("            raise Exception(f'클릭 실패: {locators} / {last_err}')")
        parts.append("        ```")
        parts.append("        사용 예: find_and_click(driver, [('title', '사용자코드 관리'), ('text', '사용자코드 관리')])")

    def build_object_analysis_prompt(self, image_description: str = "") -> str:
        """객체 분석용 프롬프트를 생성합니다."""
        template = self.templates.get("object_analysis", "")
        parts = [template]
        if image_description:
            parts.append(f"\n추가 정보: {image_description}")
        return "\n".join(parts)

    def build_error_recovery_prompt(
        self,
        error_message: str,
        current_code: str
    ) -> str:
        """에러 복구용 프롬프트를 생성합니다."""
        parts = [
            f"코드 실행 중 오류가 발생했습니다. 수정된 전체 코드를 ```python 블록으로 작성하세요.",
            "",
            f"## 에러:",
            f"```\n{error_message}\n```",
            "",
            f"## 현재 코드:",
            f"```python\n{current_code}\n```",
            "",
            "## 규칙:",
            "- 반드시 ```python 코드블록을 포함하세요",
            "- 에러를 해결한 전체 코드를 반환하세요",
        ]
        return "\n".join(parts)

    def build_project_export_prompt(
        self,
        project_name: str,
        project_description: str,
        project_type: str,
        full_code: str,
        packages_list: str
    ) -> str:
        """프로젝트 내보내기용 README 생성 프롬프트"""
        template = self.templates.get("project_export", "")
        if template:
            return template.format(
                project_name=project_name,
                project_description=project_description,
                project_type=project_type,
                full_code=full_code,
                packages_list=packages_list
            )
        return ""

    def _build_steps_summary(self, session, max_steps: int = 5) -> str:
        """이전 스텝들의 요약 텍스트를 생성합니다."""
        steps = session.steps
        if not steps:
            return ""

        recent_steps = steps[-max_steps:]
        summary_lines = []

        for step_data in recent_steps:
            step = step_data if isinstance(step_data, dict) else {}
            step_id = step.get("step_id", "?")
            status = step.get("status", "unknown")
            conv = step.get("conversation", [])

            user_msg = ""
            for msg in conv:
                m = msg if isinstance(msg, dict) else {}
                if m.get("role") == "user":
                    user_msg = m.get("content", "")[:100]
                    break

            status_icon = "✅" if status == "completed" else "❌" if status == "failed" else "⏳"
            summary_lines.append(f"- 스텝 {step_id} {status_icon}: {user_msg}")

        return "\n".join(summary_lines)

    def _get_current_code(self, session) -> tuple[str, bool]:
        """
        세션의 누적 코드와 수동 편집 여부를 반환합니다.

        step_code가 진짜 delta(새로 추가된 코드만)인 경우에만 경계 주석 조합을 사용합니다.
        step_code가 누적 코드(전체 반복 저장)인 경우에는 마지막 generated_code를 그대로 반환합니다.
        """
        steps = session.steps
        if not steps:
            return "", False

        # 마지막 스텝의 수동 편집 여부 확인
        manually_edited = False
        for step_data in reversed(steps):
            step = step_data if isinstance(step_data, dict) else {}
            if step.get("generated_code", "").strip():
                manually_edited = bool(step.get("manually_edited", False))
                break

        # step_code가 delta인지 누적 코드인지 판단:
        # step_code 총합이 마지막 generated_code보다 50% 이상 크면 누적 코드로 판단
        from core.import_manager import extract_imports, merge_imports, assemble_script

        last_gc = ""
        for step_data in reversed(steps):
            s = step_data if isinstance(step_data, dict) else {}
            if s.get("generated_code", "").strip():
                last_gc = s["generated_code"]
                break

        total_step_code_len = sum(
            len((s if isinstance(s, dict) else {}).get("step_code", ""))
            for s in steps
        )
        last_gc_len = len(last_gc)
        step_codes_are_deltas = (last_gc_len == 0 or total_step_code_len <= last_gc_len * 1.5)

        if step_codes_are_deltas:
            all_imports = []
            step_entries = []

            for step_data in steps:
                step = step_data if isinstance(step_data, dict) else {}
                step_imports = step.get("step_imports", [])
                step_code = step.get("step_code", "")

                if not step_code:
                    code = step.get("generated_code", "")
                    if code:
                        step_imports, step_code = extract_imports(code)
                    else:
                        continue

                all_imports.append(step_imports)

                task_name = ""
                for msg in step.get("conversation", []):
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        task_name = msg.get("content", "")
                        break
                if not task_name:
                    task_name = f"작업 {step.get('step_id', '?')}"

                step_entries.append((step.get("step_id", 0), task_name, step_code))

            if step_entries:
                merged = merge_imports(all_imports)
                return assemble_script(merged, step_entries), manually_edited

        # 폴백: step_code가 누적 코드이거나 없는 경우 → 마지막 generated_code 반환
        if last_gc.strip():
            return last_gc, manually_edited

        return "", False

    def _get_last_edit_diff(self, session) -> str:
        """
        수동 편집된 마지막 스텝의 변경 내역을 diff 형태로 반환합니다.
        변경된 줄만 '- 이전값' / '+ 새값' 형식으로 표시합니다.
        """
        for step_data in reversed(session.steps):
            step = step_data if isinstance(step_data, dict) else {}
            if not step.get("manually_edited"):
                continue
            old_code = step.get("edit_original_code", "")
            new_code = step.get("generated_code", "")
            if not old_code or not new_code:
                return ""

            old_lines = old_code.splitlines()
            new_lines = new_code.splitlines()
            diff_lines = []
            for old_line, new_line in zip(old_lines, new_lines):
                if old_line != new_line:
                    diff_lines.append(f"- {old_line.rstrip()}")
                    diff_lines.append(f"+ {new_line.rstrip()}")
            # 줄 수 차이가 나는 경우 추가/삭제된 줄 표시
            for line in old_lines[len(new_lines):]:
                diff_lines.append(f"- {line.rstrip()}")
            for line in new_lines[len(old_lines):]:
                diff_lines.append(f"+ {line.rstrip()}")

            return "\n".join(diff_lines)

        return ""
