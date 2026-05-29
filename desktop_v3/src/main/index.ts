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
import { app, BrowserWindow, ipcMain } from "electron";

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
 *   미설치 PC 에서도 동작. 인자는 `--port <p>` 만 (PyInstaller entry 가 api_server.__main__).
 * - **dev**: `..\.venv\Scripts\python.exe -m api_server`.
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
    return { cmd: frozen, args: ["--port", String(port)], cwd: join(process.resourcesPath, "pybridge") };
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

app.whenReady().then(async () => {
  // renderer 가 API 접속 정보를 요청할 때 응답 (preload → contextBridge).
  ipcMain.handle("ohdo:get-api-info", () => apiInfo);

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

app.on("before-quit", stopPythonBridge);

app.on("window-all-closed", () => {
  stopPythonBridge();
  if (process.platform !== "darwin") app.quit();
});
