"""
독립 picker detection 진단 스크립트

picker GUI 없이 element_picker 의 detection 로직만 단독 실행. 콘솔에 상세 출력.

사용법:
    1. Chrome 띄워서 자동화하고 싶은 탭이 보이게 둠
    2. 이 스크립트를 PowerShell 에서 실행:
       ./.venv/Scripts/python.exe scripts/diag_picker_detection.py
    3. "5초 후 검사" 메시지 보이면 cursor 를 Chrome 탭 위로 이동
    4. 5초 후 자동으로 검사 → 콘솔에 상세 출력

이 스크립트가 정상 출력 = detection 로직 OK.
이 스크립트가 실패 출력 = detection 로직 자체 문제.

실행 결과를 그대로 공유해주시면 정확한 원인 파악 가능.
"""

import sys
import time
import ctypes
from pathlib import Path

# 프로젝트 루트를 path 에 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    if sys.platform != "win32":
        print("이 스크립트는 Windows 전용입니다.")
        return 1

    import ctypes.wintypes
    user32 = ctypes.windll.user32

    print("=" * 70)
    print("Element Picker Detection 진단")
    print("=" * 70)
    print()
    print("⏳ 5초 후 cursor 위치의 element 를 detection 합니다.")
    print("   → 그 사이에 cursor 를 Chrome 탭 위로 이동시키세요.")
    print()
    for i in range(5, 0, -1):
        print(f"   {i}...", flush=True)
        time.sleep(1)
    print()
    print("⚡ 검사 시작!")
    print()

    # 현재 cursor 위치
    pt = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    x, y = pt.x, pt.y
    print(f"[1] Cursor 위치 (물리 좌표): ({x}, {y})")
    print()

    # element_picker 의 detection 로직 import
    print("[2] element_picker 모듈 import 중...")
    try:
        from ui.element_picker import ElementPickerOverlay
        print("    ✅ import OK")
    except Exception as e:
        print(f"    ❌ import 실패: {e}")
        return 1
    print()

    # GUI 없이 클래스 instance 생성 시도 (winId 가 필요해서 일부 메서드만 사용)
    # 직접 함수만 호출
    print("[3] _find_topmost_window_at_point 호출 (cursor 위치의 윈도우 찾기)")
    print("    *** 이 스크립트는 자기 자신 (PowerShell 콘솔) 을 exclude 안 함.")
    print("    *** 결과의 윈도우가 PowerShell/Terminal 이면 그 위치에 cursor 가 있던 것.")
    print()

    # Picker 의 메서드를 instance 없이 호출하기 위해 해당 로직 인라인 재현
    GW_HWNDNEXT = 2

    # argtypes 설정
    user32.GetTopWindow.argtypes = [ctypes.wintypes.HWND]
    user32.GetTopWindow.restype = ctypes.wintypes.HWND
    user32.GetWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_uint]
    user32.GetWindow.restype = ctypes.wintypes.HWND
    user32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]
    user32.IsWindowVisible.restype = ctypes.wintypes.BOOL
    user32.IsIconic.argtypes = [ctypes.wintypes.HWND]
    user32.IsIconic.restype = ctypes.wintypes.BOOL
    user32.GetWindowRect.argtypes = [
        ctypes.wintypes.HWND,
        ctypes.POINTER(ctypes.wintypes.RECT),
    ]
    user32.GetWindowRect.restype = ctypes.wintypes.BOOL

    hwnd = user32.GetTopWindow(None)
    scanned = 0
    matched_hwnd = None
    samples = []
    while hwnd and scanned < 500:
        scanned += 1
        try:
            visible = bool(user32.IsWindowVisible(hwnd))
            iconic = bool(user32.IsIconic(hwnd))
            if visible and not iconic:
                rect = ctypes.wintypes.RECT()
                if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    inside = (rect.left <= x < rect.right
                              and rect.top <= y < rect.bottom)
                    if len(samples) < 5:
                        # 윈도우 title 도 같이
                        buf = ctypes.create_unicode_buffer(256)
                        user32.GetWindowTextW(hwnd, buf, 256)
                        samples.append({
                            "hwnd": hwnd,
                            "title": buf.value[:60],
                            "rect": (rect.left, rect.top, rect.right, rect.bottom),
                            "inside": inside,
                        })
                    if inside:
                        buf = ctypes.create_unicode_buffer(256)
                        user32.GetWindowTextW(hwnd, buf, 256)
                        matched_hwnd = hwnd
                        matched_title = buf.value
                        break
        except Exception:
            pass
        hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)

    print(f"    스캔: {scanned} 개 top-level 윈도우")
    print(f"    상위 5개 샘플:")
    for s in samples:
        marker = "  ← MATCH" if s["inside"] else ""
        print(f"      HWND=0x{s['hwnd']:x} '{s['title']}' rect={s['rect']}{marker}")
    print()

    if matched_hwnd is None:
        print("    ❌ cursor 위치를 포함하는 윈도우 없음. 정상이 아님.")
        return 1

    print(f"    ✅ 매칭 윈도우: HWND=0x{matched_hwnd:x} '{matched_title}'")
    print()

    # 자식 창 정밀화
    print("[4] ChildWindowFromPointEx 로 자식 창 드릴")
    target_hwnd = matched_hwnd
    try:
        client_pt = ctypes.wintypes.POINT(x, y)
        user32.ScreenToClient(target_hwnd, ctypes.byref(client_pt))
        # CWP_SKIPINVISIBLE | CWP_SKIPDISABLED = 3
        child_hwnd = user32.ChildWindowFromPointEx(target_hwnd, client_pt, 3)
        print(f"    ScreenToClient → ({client_pt.x}, {client_pt.y})")
        print(f"    ChildWindowFromPointEx → 0x{child_hwnd:x}" if child_hwnd else "    → None")
        if child_hwnd and child_hwnd != target_hwnd:
            target_hwnd = child_hwnd
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(target_hwnd, buf, 256)
            print(f"    자식 HWND 사용: 0x{target_hwnd:x} '{buf.value[:60]}'")
    except Exception as e:
        print(f"    ❌ 예외: {e}")
    print()

    # pywinauto wrap
    print("[5] pywinauto UIAWrapper 로 wrap")
    try:
        from pywinauto.uia_element_info import UIAElementInfo
        from pywinauto.controls.uiawrapper import UIAWrapper
        elem_info = UIAElementInfo(target_hwnd)
        window_wrapper = UIAWrapper(elem_info)
        rect = window_wrapper.rectangle()
        print(f"    ✅ UIA wrap OK")
        print(f"    Window-level: {window_wrapper!r}")
        print(f"    rect=({rect.left},{rect.top})~({rect.right},{rect.bottom}) "
              f"size={rect.width()}x{rect.height()}")
    except Exception as e:
        print(f"    ❌ pywinauto wrap 실패: {e}")
        return 1
    print()

    # tree walk 로 깊은 element 드릴
    print("[6] UIA tree walk (children 따라가기)")
    try:
        # ElementPickerOverlay 의 _walk_uia_to_deepest 직접 호출 (instance 안 만들어도 됨)
        # 메서드를 unbound 호출
        # 또는 간단히 인라인 재현
        deadline = time.time() + 0.15
        current = window_wrapper
        for depth in range(10):
            if time.time() > deadline:
                print(f"    timeout at depth={depth}")
                break
            try:
                children = current.children()
            except Exception as e:
                print(f"    children() 실패 at depth={depth}: {e}")
                break
            if not children:
                break
            best_child = None
            best_area = None
            for child in children:
                if time.time() > deadline:
                    break
                try:
                    r = child.rectangle()
                    if r.left <= x < r.right and r.top <= y < r.bottom:
                        area = max(1, (r.right - r.left)) * max(1, (r.bottom - r.top))
                        if best_area is None or area < best_area:
                            best_area = area
                            best_child = child
                except Exception:
                    continue
            if best_child is None:
                break
            current = best_child
        walk_rect = current.rectangle()
        print(f"    walk 결과: {current!r}")
        print(f"    rect=({walk_rect.left},{walk_rect.top})~"
              f"({walk_rect.right},{walk_rect.bottom}) "
              f"size={walk_rect.width()}x{walk_rect.height()}")
    except Exception as e:
        print(f"    ❌ tree walk 실패: {e}")
    print()

    # raw walker 도 시도
    print("[7] RawViewWalker 보조 탐색 (tree walk 결과보다 깊은 게 있는지)")
    try:
        from pywinauto.uia_defines import IUIA
        iuia = IUIA().iuia
        walker = iuia.RawViewWalker
        deadline = time.time() + 0.15

        def walk_raw(elem, depth):
            if depth <= 0 or time.time() > deadline:
                return elem
            try:
                rect = elem.CurrentBoundingRectangle
            except Exception:
                return elem
            if not (rect.left <= x < rect.right and rect.top <= y < rect.bottom):
                return None
            best = elem
            best_area = max(1, rect.right - rect.left) * max(1, rect.bottom - rect.top)
            try:
                child = walker.GetFirstChildElement(elem)
            except Exception:
                return best
            while child:
                if time.time() > deadline:
                    break
                try:
                    cr = child.CurrentBoundingRectangle
                    if cr.left <= x < cr.right and cr.top <= y < cr.bottom:
                        c_area = max(1, cr.right - cr.left) * max(1, cr.bottom - cr.top)
                        if c_area < best_area:
                            deeper = walk_raw(child, depth - 1)
                            if deeper is not None:
                                try:
                                    dr = deeper.CurrentBoundingRectangle
                                    d_area = max(1, dr.right - dr.left) * max(1, dr.bottom - dr.top)
                                    if d_area < best_area:
                                        best = deeper
                                        best_area = d_area
                                except Exception:
                                    pass
                except Exception:
                    pass
                try:
                    child = walker.GetNextSiblingElement(child)
                except Exception:
                    break
            return best

        deepest_elem = walk_raw(elem_info._element, 10)
        if deepest_elem is not None:
            try:
                deepest_info = UIAElementInfo(deepest_elem)
                deepest_wrap = UIAWrapper(deepest_info)
                dr = deepest_wrap.rectangle()
                print(f"    raw walker 결과: {deepest_wrap!r}")
                print(f"    rect=({dr.left},{dr.top})~({dr.right},{dr.bottom}) "
                      f"size={dr.width()}x{dr.height()}")
            except Exception as e:
                print(f"    raw walker wrap 실패: {e}")
        else:
            print(f"    raw walker → None")
    except Exception as e:
        print(f"    ❌ raw walker 실패: {e}")
    print()

    print("=" * 70)
    print("진단 완료. 위 출력 전체를 그대로 공유해주세요.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
