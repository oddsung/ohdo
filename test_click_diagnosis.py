#!/usr/bin/env python3
"""
Preview 창 내부 요소의 top_level_parent() 확인 테스트
+ owner-drawn 감지 로직 검증
"""

import ctypes
import ctypes.wintypes
import time

try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

from pywinauto import Desktop
from pywinauto.findwindows import find_windows

user32 = ctypes.windll.user32

def log(msg):
    t = time.strftime("%H:%M:%S")
    print(f"[{t}] {msg}")


def main():
    log("Preview 요소의 top_level_parent() 테스트")
    log("=" * 60)

    # Preview 창 찾기
    buf = ctypes.create_unicode_buffer(256)
    preview_hwnd = None
    for hwnd in find_windows(visible_only=True):
        user32.GetWindowTextW(hwnd, buf, 256)
        if "preview" in buf.value.lower():
            preview_hwnd = hwnd
            log(f"Preview 창 발견: '{buf.value}' hwnd={hex(hwnd)}")
            break

    if not preview_hwnd:
        log("Preview 창 없음")
        return

    # Preview를 전면으로
    user32.ShowWindow(preview_hwnd, 9)
    user32.BringWindowToTop(preview_hwnd)
    try:
        user32.SetForegroundWindow(preview_hwnd)
    except:
        pass
    time.sleep(1)

    # Preview 윈도우의 여러 좌표에서 from_point 테스트
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(preview_hwnd, ctypes.byref(rect))

    # 테스트 좌표들 (Preview 창 내부)
    test_points = [
        ("툴바 왼쪽 (인쇄버튼 영역)", 30, 38),
        ("툴바 중앙 (Close 버튼 근처)", 440, 38),
        ("미리보기 영역 (본문)", 500, 400),
        ("상단 제목바", 500, 10),
    ]

    log(f"\nPreview 영역: ({rect.left},{rect.top})-({rect.right},{rect.bottom})")
    log(f"")

    for desc, x, y in test_points:
        log(f"--- 테스트: {desc} ({x}, {y}) ---")

        # UIA from_point
        try:
            desktop_uia = Desktop(backend='uia')
            elem = desktop_uia.from_point(x, y)
            if elem:
                try:
                    ctrl_type = elem.element_info.control_type or "?"
                except:
                    ctrl_type = "?"
                name = ""
                try:
                    name = elem.window_text() or ""
                except:
                    pass
                cls = ""
                try:
                    cls = elem.class_name() or ""
                except:
                    pass
                auto_id = ""
                try:
                    auto_id = elem.element_info.automation_id or ""
                except:
                    pass

                log(f"  UIA: [{ctrl_type}] name='{name}' class='{cls}' auto_id='{auto_id}'")

                # top_level_parent
                try:
                    top = elem.top_level_parent()
                    if top:
                        top_title = top.window_text() or ""
                        top_cls = top.class_name() or ""
                        log(f"  top_level_parent: '{top_title}' (class={top_cls})")
                    else:
                        log(f"  top_level_parent: None")
                except Exception as e:
                    log(f"  top_level_parent 오류: {e}")

                # owner-drawn 판단
                is_owner_drawn = (not name and not auto_id and
                                  ctrl_type in ("Window", "Pane", "TitleBar", "Custom", ""))
                log(f"  → owner-drawn 판단: {is_owner_drawn}")
            else:
                log(f"  UIA: None")
        except Exception as e:
            log(f"  UIA 오류: {e}")

        # Win32 from_point
        try:
            desktop_win32 = Desktop(backend='win32')
            elem32 = desktop_win32.from_point(x, y)
            if elem32:
                cls32 = ""
                try:
                    cls32 = elem32.class_name() or ""
                except:
                    pass
                name32 = ""
                try:
                    name32 = elem32.window_text() or ""
                except:
                    pass
                log(f"  Win32: name='{name32}' class='{cls32}'")
        except Exception as e:
            log(f"  Win32 오류: {e}")

        log("")

    log("=" * 60)
    log("테스트 완료")


if __name__ == "__main__":
    main()
