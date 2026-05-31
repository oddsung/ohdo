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
let overlayWindow: BrowserWindow | null = null;
let captureWindow: BrowserWindow | null = null;

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

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 940,
    minHeight: 600,
    backgroundColor: "#313338",
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, "../preload/index.js"),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.on("ready-to-show", () => mainWindow?.show());

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
  if (overlayWindow) return;

  // 모든 디스플레이를 덮는 union bounds (DIP).
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

  overlayWindow = new BrowserWindow({
    x: minX,
    y: minY,
    width: maxX - minX,
    height: maxY - minY,
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
  overlayWindow.setIgnoreMouseEvents(true, { forward: true });
  overlayWindow.setAlwaysOnTop(true, "screen-saver");
  // 작업표시줄(Shell_TrayWnd) 위 z-order 강제는 Python pick_pump 가 ctypes
  // SetWindowPos(HWND_TOPMOST) 로 처리한다(§49 fix2/3) — Electron setAlwaysOnTop/moveTop
  // 으론 작업표시줄을 못 이김. 여기선 초기 1회만 올리고 주기 재적용은 Python 이 담당.

  const devUrl = process.env.ELECTRON_RENDERER_URL;
  if (devUrl) {
    overlayWindow.loadURL(`${devUrl}/overlay.html`);
  } else {
    // 빌드 시 두 엔트리(index/overlay) 모두 out/renderer/ 루트로 emit (index.html 과 동일 레벨).
    overlayWindow.loadFile(join(__dirname, "../renderer/overlay.html"));
  }
  overlayWindow.once("ready-to-show", () => overlayWindow?.showInactive());
  overlayWindow.on("closed", () => {
    overlayWindow = null;
  });
}

function closePickOverlay(): void {
  if (overlayWindow) {
    overlayWindow.destroy();
    overlayWindow = null;
  }
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

/** Python 물리픽셀 rect → 오버레이 로컬 CSS px(DIP). 멀티모니터/고DPI 대응. */
function physicalRectToOverlayCss(rect: {
  left: number;
  top: number;
  right: number;
  bottom: number;
}): { x: number; y: number; w: number; h: number } | null {
  if (!overlayWindow) return null;
  // screenToDipPoint: 물리 스크린 px → DIP (Windows). 두 모서리를 각각 변환해야
  // 모니터별 scaleFactor 가 다른 경우에도 정확.
  const tl = screen.screenToDipPoint({ x: rect.left, y: rect.top });
  const br = screen.screenToDipPoint({ x: rect.right, y: rect.bottom });
  const b = overlayWindow.getBounds();
  return { x: tl.x - b.x, y: tl.y - b.y, w: br.x - tl.x, h: br.y - tl.y };
}

/** 메인 윈도우에서 호출하는 picker IPC 핸들러 등록 (1회). */
function registerPickIpc(): void {
  ipcMain.handle("pick:start", async () => {
    // v2 처럼 메인 윈도우를 숨겨 대상 앱이 가려지지 않게 한다.
    mainWindow?.minimize();
    createPickOverlay();
    // 오버레이 HWND 를 Python 에 등록 → 펌프 루프가 SetWindowPos(HWND_TOPMOST) 로
    // 작업표시줄(Shell_TrayWnd) 위로 z-order 강제 (Electron setAlwaysOnTop 으론 부족).
    try {
      if (overlayWindow && apiInfo) {
        const buf = overlayWindow.getNativeWindowHandle();
        // Win64: HWND 는 8바이트. 값은 안전정수 범위라 Number 변환 OK.
        const hwnd = buf.length >= 8 ? Number(buf.readBigUInt64LE(0)) : buf.readUInt32LE(0);
        await fetch(`${apiInfo.baseUrl}/pick/overlay`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${apiInfo.token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ hwnd }),
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
  ipcMain.handle("pick:hover", async () => {
    if (!apiInfo) return { box: null, paused: false };
    try {
      const res = await fetch(`${apiInfo.baseUrl}/pick/hover`, {
        headers: { Authorization: `Bearer ${apiInfo.token}` },
      });
      const data = (await res.json()) as {
        rect?: { left: number; top: number; right: number; bottom: number } | null;
        paused?: boolean;
      };
      return {
        box: data?.rect ? physicalRectToOverlayCss(data.rect) : null,
        paused: !!data?.paused,
      };
    } catch {
      return { box: null, paused: false };
    }
  });
}

app.whenReady().then(async () => {
  // renderer 가 API 접속 정보를 요청할 때 응답 (preload → contextBridge).
  ipcMain.handle("ohdo:get-api-info", () => apiInfo);
  registerPickIpc();

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
  stopPythonBridge();
});

app.on("window-all-closed", () => {
  stopPythonBridge();
  if (process.platform !== "darwin") app.quit();
});
