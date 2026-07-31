// SPDX-License-Identifier: AGPL-3.0-or-later
// Electron main process — Python FastAPI 브리지의 생애주기를 소유한다 (handoff §37).
//
// 흐름:
//   1. random API 토큰 생성 → OHDO_API_TOKEN env.
//   2. 비어 있는 포트를 골라 `python -m api_server --port <port>` spawn.
//   3. Python stdout 의 `OHDO_API_READY {json}` 한 줄을 기다려 실제 포트 확정.
//   4. BrowserWindow 생성, renderer 에 ipc 로 {baseUrl, token} 제공.
//   5. app 종료(before-quit) 시 SIGTERM → 5s 후 강제 종료.

import { spawn, type ChildProcessWithoutNullStreams } from "child_process";
import { createServer } from "net";
import { randomBytes } from "crypto";
import { readFileSync, writeFileSync } from "fs";
import { join } from "path";
import { app, BrowserWindow, dialog, ipcMain, screen, shell } from "electron";

const READY_MARKER = "OHDO_API_READY";
const PREFERRED_PORT = 8765;
const READY_TIMEOUT_MS = 30_000;
const KILL_GRACE_MS = 5_000;

interface ApiInfo {
  baseUrl: string;
  token: string;
}

let pyProc: ChildProcessWithoutNullStreams | null = null;
let apiInfo: ApiInfo | null = null;
let mainWindow: BrowserWindow | null = null;
// element picker 오버레이: **디스플레이마다 1개**. 단일 spanning 투명창은 Windows 에서
// 보조 모니터(특히 다른 DPI)에 합성/렌더되지 않아 붉은 박스가 주모니터에서만 보였다(§77).
// 각 창은 한 디스플레이만 덮어(단일 DPI) 그 모니터에 정상 렌더된다. hover 박스는 요소가
// 위치한 디스플레이의 창에만 그려진다.
let overlayWindows: { win: BrowserWindow; displayId: number }[] = [];
let captureWindow: BrowserWindow | null = null;

// ── 실행 중 시각 효과 (run FX, handoff §79) ─────────────────────────
// 전체 실행 동안 디스플레이마다 클릭통과 오버레이 1개(§77 패턴): 테두리 글로우 +
// 상태 HUD + 커서 링 + 클릭 리플. 클릭 좌표는 Python 관찰 훅(/fx/clicks)을 main 이
// 폴링해 물리픽셀→해당 디스플레이 로컬 DIP 로 변환, 오버레이가 runfx:poll 로 소비.
interface RunFxState {
  active: boolean;
  phase: "running" | "done";
  success: boolean | null;
  progress: { current: number; total: number; label: string } | null;
  lastSeq: number;
  clickBuf: Map<number, { x: number; y: number }[]>; // displayId → 로컬 DIP 클릭
  pollTimer: NodeJS.Timeout | null;
  closeTimer: NodeJS.Timeout | null;
}
let runOverlays: { win: BrowserWindow; displayId: number }[] = [];
const runFx: RunFxState = {
  active: false,
  phase: "running",
  success: null,
  progress: null,
  lastSeq: 0,
  clickBuf: new Map(),
  pollTimer: null,
  closeTimer: null,
};

/** 프로젝트 루트 = desktop_v3/ 의 부모. dev 에서 .venv 와 api_server 가 여기에 있다. */
function projectRoot(): string {
  // dev: app.getAppPath() === .../ohdo/desktop_v3 → 부모가 프로젝트 루트.
  // packaged: OHDO_PROJECT_ROOT override 가 없으면 resourcesPath (frozen 번들 spawn 시 cwd 미사용).
  return process.env.OHDO_PROJECT_ROOT || join(app.getAppPath(), "..");
}

/** Python 브리지 실행 커맨드 (handoff §46).
 *
 * - **packaged** (app.isPackaged): electron-builder extraResources 로 동봉된 **frozen 브리지**
 *   (`resources/pybridge/ohdo-bridge[.exe]`, PyInstaller onedir) 를 직접 실행. Python 런타임
 *   미설치 PC 에서도 동작. 인자는 `--port <p>` + `--data-dir <userData>/data`.
 *   data-dir 를 명시하는 이유: frozen 브리지의 기본 data 경로는 번들 내부
 *   (`resources/pybridge/_internal/data`) 로 잡혀, 앱 업데이트/재설치 시 세션이 날아가거나
 *   perMachine 설치 시 쓰기 불가가 된다. userData(`%APPDATA%/ohdo`)로 빼서 영속·쓰기 보장.
 * - **dev**: `..\.venv\Scripts\python.exe -m api_server` (data-dir 미지정 → 프로젝트 루트 data/,
 *   PySide6 앱과 공유).
 * - `OHDO_PYTHON` env 가 있으면 dev/packaged 무관하게 그 인터프리터로 `-m api_server` (디버그용).
 */
function bridgeCommand(port: number): { cmd: string; args: string[]; cwd: string } {
  const root = projectRoot();

  if (process.env.OHDO_PYTHON) {
    return {
      cmd: process.env.OHDO_PYTHON,
      args: ["-m", "api_server", "--port", String(port)],
      cwd: root,
    };
  }

  if (app.isPackaged) {
    // extraResources: { from: "build/pybridge", to: "pybridge" } → process.resourcesPath/pybridge/
    const exe = process.platform === "win32" ? "ohdo-bridge.exe" : "ohdo-bridge";
    const frozen = join(process.resourcesPath, "pybridge", exe);
    // 세션 저장소는 번들 밖 userData 로 (업데이트/재설치에도 보존 + 항상 쓰기 가능).
    const dataDir = join(app.getPath("userData"), "data");
    return {
      cmd: frozen,
      args: ["--port", String(port), "--data-dir", dataDir],
      cwd: join(process.resourcesPath, "pybridge"),
    };
  }

  // dev: 로컬 .venv 인터프리터.
  const python =
    process.platform === "win32"
      ? join(root, ".venv", "Scripts", "python.exe")
      : join(root, ".venv", "bin", "python");
  return { cmd: python, args: ["-m", "api_server", "--port", String(port)], cwd: root };
}

/** 주어진 포트가 비었는지 확인하고, 비었으면 그 포트를, 아니면 임의의 빈 포트를 반환한다. */
function probePort(preferred: number): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.unref();
    srv.once("error", () => {
      // 선호 포트 점유 → 임의의 빈 포트(0)로 폴백.
      const fallback = createServer();
      fallback.unref();
      fallback.once("error", reject);
      fallback.listen(0, "127.0.0.1", () => {
        const port = (fallback.address() as { port: number }).port;
        fallback.close(() => resolve(port));
      });
    });
    srv.listen(preferred, "127.0.0.1", () => {
      const port = (srv.address() as { port: number }).port;
      srv.close(() => resolve(port));
    });
  });
}

/** OS 가 비어 있다고 보장하는 포트를 하나 받아온다. */
function findFreePort(): Promise<number> {
  return probePort(PREFERRED_PORT);
}

/** Python 브리지를 spawn 하고 READY 마커를 기다린다. */
function startPythonBridge(): Promise<ApiInfo> {
  return new Promise(async (resolve, reject) => {
    const token = randomBytes(32).toString("hex");
    const port = await findFreePort();
    const { cmd, args, cwd } = bridgeCommand(port);

    console.log(`[main] python bridge spawn: ${cmd} ${args.join(" ")} (cwd=${cwd})`);

    const child = spawn(cmd, args, {
      cwd,
      env: { ...process.env, OHDO_API_TOKEN: token, PYTHONUNBUFFERED: "1" },
    });
    pyProc = child;

    let settled = false;
    let stdoutBuf = "";

    const timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        reject(new Error(`Python 브리지 READY 타임아웃 (${READY_TIMEOUT_MS}ms)`));
      }
    }, READY_TIMEOUT_MS);

    child.stdout.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      stdoutBuf += text;
      let nl: number;
      while ((nl = stdoutBuf.indexOf("\n")) >= 0) {
        const line = stdoutBuf.slice(0, nl).trim();
        stdoutBuf = stdoutBuf.slice(nl + 1);
        if (line) console.log(`[py] ${line}`);
        if (!settled && line.startsWith(READY_MARKER)) {
          try {
            const payload = JSON.parse(line.slice(READY_MARKER.length).trim());
            settled = true;
            clearTimeout(timer);
            resolve({ baseUrl: `http://127.0.0.1:${payload.port}`, token: payload.token || token });
          } catch (e) {
            settled = true;
            clearTimeout(timer);
            reject(new Error(`READY 마커 파싱 실패: ${line} (${e})`));
          }
        }
      }
    });

    child.stderr.on("data", (chunk: Buffer) => {
      // uvicorn 은 기동 로그를 stderr 로 낸다 — 진단용으로만 출력.
      console.error(`[py:err] ${chunk.toString().trimEnd()}`);
    });

    child.on("exit", (code, signal) => {
      console.log(`[main] python bridge exited code=${code} signal=${signal}`);
      pyProc = null;
      if (!settled) {
        settled = true;
        clearTimeout(timer);
        reject(new Error(`Python 브리지가 READY 전에 종료됨 (code=${code})`));
      }
    });

    child.on("error", (err) => {
      if (!settled) {
        settled = true;
        clearTimeout(timer);
        reject(err);
      }
    });
  });
}

/** Python 브리지를 정중히(SIGTERM) 종료하고, 유예 후 강제 종료한다. */
function stopPythonBridge(): void {
  const child = pyProc;
  if (!child || child.killed) return;
  console.log("[main] python bridge SIGTERM");
  child.kill("SIGTERM");
  setTimeout(() => {
    if (pyProc && !pyProc.killed) {
      console.log("[main] python bridge 강제 종료(SIGKILL)");
      pyProc.kill("SIGKILL");
    }
  }, KILL_GRACE_MS);
}

// ── 커스텀 타이틀바 + 창 상태 영속 (OpenCode/VS Code 스타일 IDE 셸) ──
//
// titleBarStyle:"hidden" + titleBarOverlay(WCO) 로 네이티브 캡션 버튼(최소화/최대화/닫기,
// Win11 스냅 레이아웃 포함)은 OS 가 그리고, 나머지 타이틀바 영역은 renderer 의 TitleBar
// 컴포넌트가 채운다(-webkit-app-region: drag). 오버레이 색은 renderer 테마 토글 시
// window:set-titlebar-theme IPC 로 동기화한다.

const TITLEBAR_HEIGHT = 36;
// index.css 다크 테마 --d-rail/--d-text 와 일치하는 초기값 (renderer 로드 전 FOUC 방지).
const TITLEBAR_DARK = { color: "#1e1f22", symbolColor: "#dbdee1" };

interface WindowState {
  x?: number;
  y?: number;
  width: number;
  height: number;
  maximized?: boolean;
}

const DEFAULT_WINDOW_STATE: WindowState = { width: 1440, height: 900 };

function windowStateFile(): string {
  return join(app.getPath("userData"), "window-state.json");
}

/** 마지막 창 크기/위치/최대화 복원 (IDE 관례). 저장 위치가 현재 디스플레이 밖이면 기본값. */
function loadWindowState(): WindowState {
  try {
    const raw = JSON.parse(readFileSync(windowStateFile(), "utf-8")) as WindowState;
    if (
      typeof raw.width !== "number" ||
      typeof raw.height !== "number" ||
      raw.width < 600 ||
      raw.height < 400
    ) {
      return { ...DEFAULT_WINDOW_STATE };
    }
    // 위치가 있으면 어느 디스플레이와도 안 겹치는지 검사 (모니터 해제/재배치 대비).
    if (typeof raw.x === "number" && typeof raw.y === "number") {
      const visible = screen.getAllDisplays().some((d) => {
        const a = d.workArea;
        return (
          raw.x! < a.x + a.width - 40 &&
          raw.x! + raw.width > a.x + 40 &&
          raw.y! < a.y + a.height - 40 &&
          raw.y! >= a.y - 20
        );
      });
      if (!visible) {
        delete raw.x;
        delete raw.y;
      }
    }
    return raw;
  } catch {
    return { ...DEFAULT_WINDOW_STATE };
  }
}

function saveWindowState(): void {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  try {
    const maximized = mainWindow.isMaximized();
    // 최대화 상태면 복원(normal) bounds 를 저장해 다음 실행에서 최대화 해제 시 크기 유지.
    const b = maximized ? mainWindow.getNormalBounds() : mainWindow.getBounds();
    const state: WindowState = { x: b.x, y: b.y, width: b.width, height: b.height, maximized };
    writeFileSync(windowStateFile(), JSON.stringify(state));
  } catch {
    /* best-effort */
  }
}

function createWindow(): void {
  const state = loadWindowState();
  mainWindow = new BrowserWindow({
    x: state.x,
    y: state.y,
    width: state.width,
    height: state.height,
    minWidth: 940,
    minHeight: 600,
    backgroundColor: "#313338",
    show: false,
    autoHideMenuBar: true,
    // 네이티브 타이틀바 숨김 + WCO 캡션 버튼 (VS Code/Cursor/OpenCode 스타일).
    titleBarStyle: "hidden",
    titleBarOverlay: { ...TITLEBAR_DARK, height: TITLEBAR_HEIGHT },
    webPreferences: {
      preload: join(__dirname, "../preload/index.js"),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (state.maximized) mainWindow.maximize();
  mainWindow.on("ready-to-show", () => mainWindow?.show());
  mainWindow.on("close", () => saveWindowState());

  // electron-vite 가 dev 서버 URL 을 ELECTRON_RENDERER_URL 로 주입한다.
  if (process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    mainWindow.loadFile(join(__dirname, "../renderer/index.html"));
  }
}

/** element picker 투명 오버레이 (handoff §49).
 *
 * 가상 데스크톱 전체를 덮는 투명·프레임리스·클릭통과(WS_EX_TRANSPARENT) 창.
 * `setIgnoreMouseEvents(true)` 가 WS_EX_TRANSPARENT 를 설정 → UIA ElementFromPoint 가
 * 이 창을 건너뛰고 그 아래 대상 앱 element 를 반환한다(v2 가 풀던 문제를 동일 원리로 해결).
 * 클릭/Esc 는 이 창이 아니라 전역 LL 후크(Python pick_pump)가 잡는다.
 */
function createPickOverlay(): void {
  if (overlayWindows.length) return;

  const devUrl = process.env.ELECTRON_RENDERER_URL;
  // 디스플레이마다 1개 — 단일 spanning 투명창은 멀티모니터(특히 다른 DPI)에서 보조모니터에
  // 합성 안 됨(§77). 각 창은 자기 디스플레이의 bounds(DIP)만 덮어 그 모니터에 정상 렌더.
  for (const d of screen.getAllDisplays()) {
    const win = new BrowserWindow({
      x: d.bounds.x,
      y: d.bounds.y,
      width: d.bounds.width,
      height: d.bounds.height,
      transparent: true,
      frame: false,
      resizable: false,
      movable: false,
      minimizable: false,
      maximizable: false,
      fullscreenable: false,
      skipTaskbar: true,
      focusable: false,
      hasShadow: false,
      enableLargerThanScreen: true,
      alwaysOnTop: true,
      show: false,
      webPreferences: {
        preload: join(__dirname, "../preload/index.js"),
        sandbox: false,
      },
    });

    // 클릭통과(WS_EX_TRANSPARENT) — 대상 앱이 클릭을 받고 LL 후크가 캡처. forward 로
    // 마우스 이동 이벤트는 받아 cursor 표시 유지.
    win.setIgnoreMouseEvents(true, { forward: true });
    win.setAlwaysOnTop(true, "screen-saver");
    // 작업표시줄(Shell_TrayWnd) 위 z-order 강제는 Python pick_pump 가 ctypes
    // SetWindowPos(HWND_TOPMOST) 로 처리한다(§49 fix2/3) — Electron setAlwaysOnTop/moveTop
    // 으론 작업표시줄을 못 이김. 모든 오버레이 HWND 를 등록해 Python 이 주기 재적용.

    if (devUrl) {
      win.loadURL(`${devUrl}/overlay.html`);
    } else {
      // 빌드 시 두 엔트리(index/overlay) 모두 out/renderer/ 루트로 emit (index.html 과 동일 레벨).
      win.loadFile(join(__dirname, "../renderer/overlay.html"));
    }
    win.once("ready-to-show", () => win.showInactive());
    win.on("closed", () => {
      overlayWindows = overlayWindows.filter((o) => o.win !== win);
    });
    overlayWindows.push({ win, displayId: d.id });
  }
}

function closePickOverlay(): void {
  for (const o of overlayWindows) {
    if (!o.win.isDestroyed()) o.win.destroy();
  }
  overlayWindows = [];
}

/** 모든 picker 오버레이 창의 네이티브 HWND (Python z-order/§70 숨김 등록용). */
function overlayHwnds(): number[] {
  const out: number[] = [];
  for (const o of overlayWindows) {
    if (o.win.isDestroyed()) continue;
    const buf = o.win.getNativeWindowHandle();
    // Win64: HWND 는 8바이트. 값은 안전정수 범위라 Number 변환 OK.
    out.push(buf.length >= 8 ? Number(buf.readBigUInt64LE(0)) : buf.readUInt32LE(0));
  }
  return out;
}

/** 가상 데스크톱 전체를 덮는 union bounds (DIP). picker/capture 오버레이 공용. */
function virtualBounds(): { x: number; y: number; width: number; height: number } {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const d of screen.getAllDisplays()) {
    minX = Math.min(minX, d.bounds.x);
    minY = Math.min(minY, d.bounds.y);
    maxX = Math.max(maxX, d.bounds.x + d.bounds.width);
    maxY = Math.max(maxY, d.bounds.y + d.bounds.height);
  }
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

/** 스크린 영역 캡처 오버레이 (handoff §60, 백로그 #13).
 *
 * picker 오버레이와 달리 **클릭통과 아님** — 드래그로 사각형을 직접 받는다.
 * 오버레이가 mouseup 시 오버레이-로컬 CSS px 사각형을 IPC(capture:done)로 보내면
 * main 이 DIP→물리 픽셀로 변환해 resolve 한다(아래 registerCaptureIpc). Esc=취소.
 */
function createCaptureOverlay(): void {
  if (captureWindow) return;
  const b = virtualBounds();
  captureWindow = new BrowserWindow({
    x: b.x,
    y: b.y,
    width: b.width,
    height: b.height,
    transparent: true,
    frame: false,
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    hasShadow: false,
    enableLargerThanScreen: true,
    alwaysOnTop: true,
    show: false,
    webPreferences: {
      preload: join(__dirname, "../preload/index.js"),
      sandbox: false,
    },
  });
  captureWindow.setAlwaysOnTop(true, "screen-saver");

  const devUrl = process.env.ELECTRON_RENDERER_URL;
  if (devUrl) {
    captureWindow.loadURL(`${devUrl}/capture_overlay.html`);
  } else {
    captureWindow.loadFile(join(__dirname, "../renderer/capture_overlay.html"));
  }
  captureWindow.once("ready-to-show", () => captureWindow?.show());
  captureWindow.on("closed", () => {
    captureWindow = null;
  });
}

function closeCaptureOverlay(): void {
  if (captureWindow) {
    captureWindow.destroy();
    captureWindow = null;
  }
}

/** 오버레이-로컬 CSS px(DIP) 사각형 → 물리 픽셀(가상 데스크톱 좌표). 멀티모니터/고DPI 대응. */
function overlayCssRectToPhysical(rect: {
  x: number;
  y: number;
  w: number;
  h: number;
}): { left: number; top: number; width: number; height: number } | null {
  if (!captureWindow) return null;
  const b = captureWindow.getBounds();
  // 오버레이-로컬 CSS px → 스크린 DIP(창 origin 더함) → dipToScreenPoint → 물리 px.
  const tl = screen.dipToScreenPoint({ x: b.x + rect.x, y: b.y + rect.y });
  const br = screen.dipToScreenPoint({ x: b.x + rect.x + rect.w, y: b.y + rect.y + rect.h });
  return { left: tl.x, top: tl.y, width: br.x - tl.x, height: br.y - tl.y };
}

/** Python 물리픽셀 rect → 특정 오버레이 창(=한 디스플레이) 로컬 CSS px(DIP).
 *
 * 요소가 이 창의 디스플레이에 있을 때만 box 를 반환(아니면 null) — 디스플레이별 오버레이가
 * 각자 자기 모니터의 요소만 그리게 한다(§77). `screenToDipPoint` 로 두 모서리를 각각 변환해
 * 모니터별 scaleFactor 가 달라도 정확.
 */
function physicalRectToOverlayCss(
  rect: { left: number; top: number; right: number; bottom: number },
  entry: { win: BrowserWindow; displayId: number },
): { x: number; y: number; w: number; h: number } | null {
  if (entry.win.isDestroyed()) return null;
  const tl = screen.screenToDipPoint({ x: rect.left, y: rect.top });
  const br = screen.screenToDipPoint({ x: rect.right, y: rect.bottom });
  // 요소 중심(DIP)이 속한 디스플레이가 이 창의 디스플레이가 아니면 그리지 않는다.
  const center = { x: Math.round((tl.x + br.x) / 2), y: Math.round((tl.y + br.y) / 2) };
  if (screen.getDisplayNearestPoint(center).id !== entry.displayId) return null;
  const b = entry.win.getBounds();
  return { x: tl.x - b.x, y: tl.y - b.y, w: br.x - tl.x, h: br.y - tl.y };
}

/** 실행 FX 오버레이 생성/해제 (handoff §79) — picker 오버레이(§77)와 동일 창 구조. */
function createRunOverlays(): void {
  if (runOverlays.length) return;
  const devUrl = process.env.ELECTRON_RENDERER_URL;
  for (const d of screen.getAllDisplays()) {
    const win = new BrowserWindow({
      x: d.bounds.x,
      y: d.bounds.y,
      width: d.bounds.width,
      height: d.bounds.height,
      transparent: true,
      frame: false,
      resizable: false,
      movable: false,
      minimizable: false,
      maximizable: false,
      fullscreenable: false,
      skipTaskbar: true,
      focusable: false,
      hasShadow: false,
      enableLargerThanScreen: true,
      alwaysOnTop: true,
      show: false,
      webPreferences: {
        preload: join(__dirname, "../preload/index.js"),
        sandbox: false,
      },
    });
    win.setIgnoreMouseEvents(true);
    win.setAlwaysOnTop(true, "screen-saver");
    if (devUrl) {
      win.loadURL(`${devUrl}/run_overlay.html`);
    } else {
      win.loadFile(join(__dirname, "../renderer/run_overlay.html"));
    }
    win.once("ready-to-show", () => win.showInactive());
    win.on("closed", () => {
      runOverlays = runOverlays.filter((o) => o.win !== win);
    });
    runOverlays.push({ win, displayId: d.id });
  }
}

function closeRunOverlays(): void {
  for (const o of runOverlays) {
    if (!o.win.isDestroyed()) o.win.destroy();
  }
  runOverlays = [];
}

async function bridgeFx(path: string): Promise<void> {
  if (!apiInfo) return;
  await fetch(`${apiInfo.baseUrl}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${apiInfo.token}` },
  }).catch(() => {});
}

/** 브리지 /fx/clicks 폴링 — 물리픽셀 클릭을 소속 디스플레이 로컬 DIP 로 변환해 버퍼링. */
function pollFxClicks(): void {
  if (!apiInfo || !runFx.active) return;
  fetch(`${apiInfo.baseUrl}/fx/clicks?since=${runFx.lastSeq}`, {
    headers: { Authorization: `Bearer ${apiInfo.token}` },
  })
    .then((r) => r.json())
    .then((data: { seq: number; clicks: { x: number; y: number }[] }) => {
      if (!data || typeof data.seq !== "number") return;
      runFx.lastSeq = data.seq;
      for (const c of data.clicks || []) {
        const dip = screen.screenToDipPoint({ x: c.x, y: c.y });
        const disp = screen.getDisplayNearestPoint(dip);
        const entry = runOverlays.find((o) => o.displayId === disp.id);
        if (!entry || entry.win.isDestroyed()) continue;
        const b = entry.win.getBounds();
        const buf = runFx.clickBuf.get(disp.id) ?? [];
        buf.push({ x: dip.x - b.x, y: dip.y - b.y });
        if (buf.length > 20) buf.splice(0, buf.length - 20);
        runFx.clickBuf.set(disp.id, buf);
      }
    })
    .catch(() => {});
}

function startRunFx(): void {
  if (runFx.closeTimer) {
    clearTimeout(runFx.closeTimer);
    runFx.closeTimer = null;
  }
  runFx.active = true;
  runFx.phase = "running";
  runFx.success = null;
  runFx.progress = null;
  runFx.lastSeq = 0;
  runFx.clickBuf.clear();
  createRunOverlays();
  void bridgeFx("/fx/start");
  if (!runFx.pollTimer) runFx.pollTimer = setInterval(pollFxClicks, 120);
}

function stopRunFx(success: boolean | null): void {
  if (!runFx.active && runOverlays.length === 0) return;
  runFx.phase = "done";
  runFx.success = success;
  runFx.active = false;
  if (runFx.pollTimer) {
    clearInterval(runFx.pollTimer);
    runFx.pollTimer = null;
  }
  void bridgeFx("/fx/stop");
  mainWindow?.setProgressBar(-1);
  // 종료 플래시(성공/실패 색)를 잠깐 보여준 뒤 닫는다. 즉시 재실행 시 startRunFx 가 취소.
  runFx.closeTimer = setTimeout(() => {
    closeRunOverlays();
    runFx.closeTimer = null;
  }, 900);
}

function registerRunFxIpc(): void {
  ipcMain.handle("runfx:start", () => startRunFx());
  ipcMain.handle("runfx:stop", (_e, r: { success?: boolean | null } | undefined) =>
    stopRunFx(r?.success ?? null),
  );
  ipcMain.handle(
    "runfx:progress",
    (_e, p: { current: number; total: number; label: string }) => {
      runFx.progress = p;
      if (mainWindow && !mainWindow.isDestroyed()) {
        // 작업표시줄 진행바 — total 미상이면 indeterminate(>1).
        mainWindow.setProgressBar(p.total > 0 ? Math.min(1, p.current / p.total) : 2);
      }
    },
  );
  // run 오버레이 폴링 — 호출 창(=디스플레이) 기준 로컬 상태 반환 (§77 fromWebContents 패턴).
  ipcMain.handle("runfx:poll", (event) => {
    const sender = BrowserWindow.fromWebContents(event.sender);
    const entry = runOverlays.find((o) => o.win === sender);
    if (!entry || entry.win.isDestroyed()) {
      return { active: false, phase: runFx.phase, success: runFx.success };
    }
    const b = entry.win.getBounds();
    const cur = screen.getCursorScreenPoint(); // DIP
    const curDisp = screen.getDisplayNearestPoint(cur);
    const cursor =
      curDisp.id === entry.displayId ? { x: cur.x - b.x, y: cur.y - b.y } : null;
    const clicks = runFx.clickBuf.get(entry.displayId) ?? [];
    if (clicks.length) runFx.clickBuf.set(entry.displayId, []);
    const isPrimary = screen.getPrimaryDisplay().id === entry.displayId;
    return {
      active: runFx.active,
      phase: runFx.phase,
      success: runFx.success,
      isPrimary,
      cursor,
      clicks,
      progress: runFx.progress,
    };
  });
}

/** 메인 윈도우에서 호출하는 picker IPC 핸들러 등록 (1회). */
function registerPickIpc(): void {
  ipcMain.handle("pick:start", async () => {
    // v2 처럼 메인 윈도우를 숨겨 대상 앱이 가려지지 않게 한다.
    mainWindow?.minimize();
    createPickOverlay();
    // 모든 오버레이 HWND 를 Python 에 등록 → 펌프 루프가 각 창을 SetWindowPos(HWND_TOPMOST) 로
    // 작업표시줄(Shell_TrayWnd) 위로 z-order 강제(Electron setAlwaysOnTop 으론 부족) + §70
    // grab 직전 숨김도 전부 처리. (디스플레이별 오버레이라 리스트로 등록 — §77.)
    try {
      const hwnds = overlayHwnds();
      if (hwnds.length && apiInfo) {
        await fetch(`${apiInfo.baseUrl}/pick/overlay`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${apiInfo.token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ hwnds }),
        });
      }
    } catch {
      /* best-effort — 등록 실패해도 selection 자체는 동작 */
    }
  });
  ipcMain.handle("pick:stop", () => {
    closePickOverlay();
    if (mainWindow?.isMinimized()) mainWindow.restore();
  });

  // 스크린 영역 캡처 (handoff §60, 백로그 #13). 메인 minimize → 캡처 오버레이로 드래그
  // → 오버레이가 capture:done/capture:cancel(IPC send) → main 이 DIP→물리 변환해 resolve.
  // 반환: 물리 픽셀 사각형 {left,top,width,height} 또는 null(취소). 한 번에 하나만.
  ipcMain.handle("capture:start", () => {
    return new Promise<{ left: number; top: number; width: number; height: number } | null>(
      (resolve) => {
        let settled = false;
        const cleanup = () => {
          ipcMain.removeListener("capture:done", onDone);
          ipcMain.removeListener("capture:cancel", onCancel);
          closeCaptureOverlay();
          if (mainWindow?.isMinimized()) mainWindow.restore();
        };
        const finish = (value: { left: number; top: number; width: number; height: number } | null) => {
          if (settled) return;
          settled = true;
          cleanup();
          resolve(value);
        };
        const onDone = (_e: unknown, rect: { x: number; y: number; w: number; h: number }) => {
          finish(overlayCssRectToPhysical(rect));
        };
        const onCancel = () => finish(null);
        ipcMain.once("capture:done", onDone);
        ipcMain.once("capture:cancel", onCancel);

        mainWindow?.minimize();
        createCaptureOverlay();
        // 오버레이 창이 닫히면(예: 외부 요인) 취소로 간주.
        captureWindow?.on("closed", () => finish(null));
      },
    );
  });

  // 작업 녹화 시작/종료 시 메인 윈도우 최소화/복원 (사용자 요청, §49).
  // 녹화 중 대상 앱 조작을 ohdo 창이 가리지 않도록 — element picker 와 동일 UX.
  ipcMain.handle("record:minimize", () => {
    mainWindow?.minimize();
  });
  ipcMain.handle("record:restore", () => {
    if (mainWindow?.isMinimized()) mainWindow.restore();
  });

  // 코드 실행 완료 후 메인 윈도우를 앞으로 (사용자 요청, §49). 실행된 코드가 메모장/계산기
  // 등 대상 앱을 띄워 포커스를 가져가므로, 결과를 바로 보도록 ohdo 창을 복원·최상단으로.
  ipcMain.handle("window:focus", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    // Windows foreground 가로채기 제약 우회 — 잠깐 alwaysOnTop 으로 앞으로 가져온 뒤 해제.
    // §75: 동기 해제(true→focus()→false 한 tick)는 일부 Windows 에서 WS_EX_TOPMOST 가 안 풀려
    // 메인 창이 계속 최상위에 박히는 버그(다른 창이 앞으로 못 옴, ohdo 재클릭해야 해제)였다 →
    // foreground 전환이 끝나도록 짧은 지연 후 topmost 해제(창이 닫혔으면 무시).
    mainWindow.setAlwaysOnTop(true);
    mainWindow.focus();
    setTimeout(() => {
      if (mainWindow && !mainWindow.isDestroyed()) mainWindow.setAlwaysOnTop(false);
    }, 250);
  });
  // 프로젝트 내보내기/가져오기 (§47 #15) — 네이티브 폴더 선택 + Explorer 열기.
  ipcMain.handle("fs:pick-directory", async () => {
    if (!mainWindow) return null;
    const res = await dialog.showOpenDialog(mainWindow, { properties: ["openDirectory"] });
    return res.canceled || res.filePaths.length === 0 ? null : res.filePaths[0];
  });
  ipcMain.handle("fs:reveal", (_e, p: string) => {
    if (p) shell.showItemInFolder(p);
  });
  // renderer 테마 토글 → WCO 캡션 버튼 영역 색 동기화 (Windows 전용 API, 타 플랫폼 no-op).
  ipcMain.handle(
    "window:set-titlebar-theme",
    (_e, colors: { color?: string; symbolColor?: string }) => {
      if (!mainWindow || mainWindow.isDestroyed()) return;
      try {
        mainWindow.setTitleBarOverlay?.({
          color: colors?.color || TITLEBAR_DARK.color,
          symbolColor: colors?.symbolColor || TITLEBAR_DARK.symbolColor,
          height: TITLEBAR_HEIGHT,
        });
      } catch {
        /* titleBarOverlay 미지원 플랫폼 — 무시 */
      }
    },
  );
  ipcMain.handle("pick:hover", async (event) => {
    if (!apiInfo) return { box: null, paused: false };
    try {
      const res = await fetch(`${apiInfo.baseUrl}/pick/hover`, {
        headers: { Authorization: `Bearer ${apiInfo.token}` },
      });
      const data = (await res.json()) as {
        rect?: { left: number; top: number; right: number; bottom: number } | null;
        paused?: boolean;
      };
      // 어느 오버레이(=디스플레이)가 폴링했는지 식별 → 그 디스플레이의 요소만 box 반환(§77).
      const sender = BrowserWindow.fromWebContents(event.sender);
      const entry = overlayWindows.find((o) => o.win === sender);
      const box = data?.rect && entry ? physicalRectToOverlayCss(data.rect, entry) : null;
      return { box, paused: !!data?.paused };
    } catch {
      return { box: null, paused: false };
    }
  });
}

app.whenReady().then(async () => {
  // renderer 가 API 접속 정보를 요청할 때 응답 (preload → contextBridge).
  ipcMain.handle("ohdo:get-api-info", () => apiInfo);
  registerPickIpc();
  registerRunFxIpc();

  try {
    apiInfo = await startPythonBridge();
    console.log(`[main] bridge ready at ${apiInfo.baseUrl}`);
  } catch (err) {
    console.error("[main] Python 브리지 시작 실패:", err);
    // 브리지가 없어도 창은 띄운다 — renderer 가 에러 상태를 표시한다.
    apiInfo = null;
  }

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", () => {
  closePickOverlay();
  closeRunOverlays();
  stopPythonBridge();
});

app.on("window-all-closed", () => {
  stopPythonBridge();
  if (process.platform !== "darwin") app.quit();
});
