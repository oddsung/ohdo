// SPDX-License-Identifier: AGPL-3.0-or-later
// element picker 투명 오버레이 렌더러 (handoff §49).
//
// 이 창은 가상 데스크톱 전체를 덮는 투명·클릭통과(WS_EX_TRANSPARENT) 창이다.
// ~30fps 로 main 에 hover rect 를 요청해(window.ohdoPick.hover) 붉은 박스를 그린다.
// 클릭/Esc 는 이 창이 처리하지 않는다 — 전역 LL 후크(Python pick_pump)가 잡는다.
// rect 는 main 이 물리픽셀→DIP(오버레이 로컬 CSS px)로 변환해서 내려준다.

const hl = document.getElementById("hl") as HTMLDivElement;
const hint = document.getElementById("hint") as HTMLDivElement;

const HINT_NORMAL = "선택할 UI 요소를 클릭하세요 · F3 일시정지 · Esc 취소";
const HINT_PAUSED = "⏸ 일시정지 — 메뉴 등을 펼친 뒤 F3 로 재개";

interface HoverBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface HoverResult {
  box: HoverBox | null;
  paused: boolean;
}

declare global {
  interface Window {
    ohdoPick?: { hover: () => Promise<HoverResult | null> };
  }
}

export {};

let stopped = false;

async function tick(): Promise<void> {
  if (stopped) return;
  try {
    const res = await window.ohdoPick?.hover();
    const box = res?.box ?? null;
    if (box && box.w > 0 && box.h > 0) {
      hl.style.display = "block";
      hl.style.left = `${box.x}px`;
      hl.style.top = `${box.y}px`;
      hl.style.width = `${box.w}px`;
      hl.style.height = `${box.h}px`;
    } else {
      hl.style.display = "none";
    }
    // 일시정지 상태 안내 + 배너 색 전환.
    if (res?.paused) {
      hint.textContent = HINT_PAUSED;
      hint.style.borderColor = "rgba(250, 204, 21, 0.7)";
    } else {
      hint.textContent = HINT_NORMAL;
      hint.style.borderColor = "rgba(239, 68, 68, 0.6)";
    }
  } catch {
    hl.style.display = "none";
  }
  // ~30fps. requestAnimationFrame 는 백그라운드 창에서 throttle 되므로 setTimeout 사용.
  window.setTimeout(tick, 33);
}

window.addEventListener("beforeunload", () => {
  stopped = true;
});

tick();
