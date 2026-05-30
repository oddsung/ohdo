// SPDX-License-Identifier: AGPL-3.0-or-later
// 스크린 영역 캡처 오버레이 렌더러 (handoff §60, 백로그 #13).
//
// element picker 오버레이(overlay.ts, 클릭통과+hover 폴링)와 달리, 이 창은 **드래그로
// 사각형을 직접 받는다**(클릭통과 아님). 사용자가 마우스로 영역을 그리면 mouseup 시
// 오버레이-로컬 CSS px 사각형을 main 으로 보낸다(window.ohdoCapture.done). main 이
// DIP→물리 픽셀로 변환해 /capture/region 으로 grab 한다. Esc 는 취소.

const sel = document.getElementById("sel") as HTMLDivElement;

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

declare global {
  interface Window {
    ohdoCapture?: {
      done: (rect: Rect) => void;
      cancel: () => void;
    };
  }
}

export {};

let startX = 0;
let startY = 0;
let dragging = false;
let done = false;

function draw(x: number, y: number, w: number, h: number): void {
  sel.style.display = "block";
  sel.style.left = `${x}px`;
  sel.style.top = `${y}px`;
  sel.style.width = `${w}px`;
  sel.style.height = `${h}px`;
}

window.addEventListener("mousedown", (e) => {
  if (done || e.button !== 0) return;
  dragging = true;
  startX = e.clientX;
  startY = e.clientY;
  draw(startX, startY, 0, 0);
});

window.addEventListener("mousemove", (e) => {
  if (!dragging) return;
  const x = Math.min(startX, e.clientX);
  const y = Math.min(startY, e.clientY);
  const w = Math.abs(e.clientX - startX);
  const h = Math.abs(e.clientY - startY);
  draw(x, y, w, h);
});

window.addEventListener("mouseup", (e) => {
  if (!dragging || done || e.button !== 0) return;
  dragging = false;
  const x = Math.min(startX, e.clientX);
  const y = Math.min(startY, e.clientY);
  const w = Math.abs(e.clientX - startX);
  const h = Math.abs(e.clientY - startY);
  // 너무 작은 선택(클릭 오작동)은 취소 처리.
  if (w < 4 || h < 4) {
    window.ohdoCapture?.cancel();
    return;
  }
  done = true;
  window.ohdoCapture?.done({ x, y, w, h });
});

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !done) {
    done = true;
    window.ohdoCapture?.cancel();
  }
});
