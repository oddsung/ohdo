// SPDX-License-Identifier: AGPL-3.0-or-later
// 실행 중 시각 효과 오버레이 렌더러 (handoff §79).
//
// ~30fps 로 main 에 상태를 폴링(window.ohdoRunFx.poll)해 그린다:
// - cursor: 이 디스플레이에 있을 때만 커서 링 표시 (로컬 DIP)
// - clicks: 클릭 리플 (Python 관찰 훅 → main 변환 → 로컬 DIP)
// - progress: 상단 HUD (주 디스플레이만)
// - phase done: 성공/실패 색 플래시 (창은 main 이 잠시 후 닫음)

const frame = document.getElementById("frame") as HTMLDivElement;
const hud = document.getElementById("hud") as HTMLDivElement;
const hudText = document.getElementById("hud-text") as HTMLSpanElement;
const ring = document.getElementById("ring") as HTMLDivElement;

interface RunFxPollResult {
  active: boolean;
  phase: "running" | "done";
  success: boolean | null;
  isPrimary?: boolean;
  cursor?: { x: number; y: number } | null;
  clicks?: { x: number; y: number }[];
  progress?: { current: number; total: number; label: string } | null;
}

declare global {
  interface Window {
    ohdoRunFx?: { poll: () => Promise<RunFxPollResult | null> };
  }
}

export {};

let stopped = false;
let doneApplied = false;

function spawnRipple(x: number, y: number): void {
  const el = document.createElement("div");
  el.className = "ripple";
  el.style.left = `${x}px`;
  el.style.top = `${y}px`;
  document.body.appendChild(el);
  window.setTimeout(() => el.remove(), 650);
}

async function tick(): Promise<void> {
  if (stopped) return;
  try {
    const res = await window.ohdoRunFx?.poll();
    if (res) {
      // 커서 링 — 이 디스플레이에 커서가 있을 때만.
      if (res.phase === "running" && res.cursor) {
        ring.style.display = "block";
        ring.style.left = `${res.cursor.x}px`;
        ring.style.top = `${res.cursor.y}px`;
      } else {
        ring.style.display = "none";
      }
      // 클릭 리플.
      for (const c of res.clicks ?? []) spawnRipple(c.x, c.y);
      // HUD — 주 디스플레이만, 진행 라벨은 renderer 가 로컬라이즈해서 전달.
      if (res.isPrimary && res.phase === "running" && res.progress?.label) {
        hud.style.display = "flex";
        hudText.textContent = res.progress.label;
      } else if (res.phase !== "running") {
        hud.style.display = "none";
      }
      // 종료 플래시 — 성공(초록)/실패(빨강), 수동 중지(null)는 플래시 없이 닫힘.
      if (res.phase === "done" && !doneApplied) {
        doneApplied = true;
        if (res.success === true) frame.classList.add("done-ok");
        else if (res.success === false) frame.classList.add("done-fail");
        else frame.style.display = "none";
        ring.style.display = "none";
      }
    }
  } catch {
    /* main 이 창을 닫는 중 — 무시 */
  }
  window.setTimeout(tick, 33);
}

window.addEventListener("beforeunload", () => {
  stopped = true;
});

tick();
