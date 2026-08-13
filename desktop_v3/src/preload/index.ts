// SPDX-License-Identifier: AGPL-3.0-or-later
// preload — contextIsolation 경계에서 renderer 에 최소 API 만 노출한다.
// API 토큰은 main 프로세스가 보유하고, renderer 는 ipc 로 요청해서만 받는다
// (renderer 번들/DOM 에 토큰을 하드코딩하지 않음).

import { contextBridge, ipcRenderer } from "electron";

export interface ApiInfo {
  baseUrl: string;
  token: string;
}

const api = {
  /** Python 브리지 접속 정보 {baseUrl, token}. 브리지 미기동 시 null. */
  getApiInfo: (): Promise<ApiInfo | null> => ipcRenderer.invoke("ohdo:get-api-info"),
  // element picker 투명 오버레이 제어 (handoff §49) — 메인 윈도우에서 호출.
  startPickOverlay: (): Promise<void> => ipcRenderer.invoke("pick:start"),
  stopPickOverlay: (): Promise<void> => ipcRenderer.invoke("pick:stop"),
  // 스크린 영역 캡처 (handoff §60) — 드래그 오버레이 → 물리 픽셀 사각형 반환(취소 시 null).
  captureRegion: (): Promise<{ left: number; top: number; width: number; height: number } | null> =>
    ipcRenderer.invoke("capture:start"),
  // 작업 녹화 시 메인 윈도우 최소화/복원 (§49).
  minimizeForRecord: (): Promise<void> => ipcRenderer.invoke("record:minimize"),
  restoreFromRecord: (): Promise<void> => ipcRenderer.invoke("record:restore"),
  // 코드 실행 완료 후 메인 윈도우를 앞으로 (§49).
  focusMainWindow: (): Promise<void> => ipcRenderer.invoke("window:focus"),
  // 프로젝트 내보내기/가져오기 (§47 #15) — 네이티브 폴더 선택 + Explorer 열기.
  pickDirectory: (): Promise<string | null> => ipcRenderer.invoke("fs:pick-directory"),
  revealPath: (p: string): Promise<void> => ipcRenderer.invoke("fs:reveal", p),
  // 커스텀 타이틀바(WCO) 캡션 버튼 색을 renderer 테마와 동기화.
  setTitleBarTheme: (colors: { color: string; symbolColor: string }): Promise<void> =>
    ipcRenderer.invoke("window:set-titlebar-theme", colors),
  // 실행 중 시각 효과 (run FX, handoff §79) — 시작/진행/종료.
  runFxStart: (): Promise<void> => ipcRenderer.invoke("runfx:start"),
  runFxProgress: (p: { current: number; total: number; label: string }): Promise<void> =>
    ipcRenderer.invoke("runfx:progress", p),
  runFxStop: (r?: { success?: boolean | null }): Promise<void> =>
    ipcRenderer.invoke("runfx:stop", r),
  // 자동 업데이트 (handoff §82) — main 의 electron-updater 이벤트 구독 + 재시작 설치.
  onUpdaterEvent: (
    cb: (e: { status: string; info?: { version?: string; message?: string } }) => void,
  ): (() => void) => {
    const listener = (
      _event: unknown,
      payload: { status: string; info?: { version?: string; message?: string } },
    ) => cb(payload);
    ipcRenderer.on("updater:event", listener);
    return () => ipcRenderer.removeListener("updater:event", listener);
  },
  installUpdate: (): Promise<void> => ipcRenderer.invoke("updater:install"),
};

contextBridge.exposeInMainWorld("ohdo", api);

// 오버레이 창 전용 — hover rect 폴링 (main 이 물리픽셀→오버레이 로컬 CSS px 변환).
contextBridge.exposeInMainWorld("ohdoPick", {
  hover: () => ipcRenderer.invoke("pick:hover"),
});

// 캡처 오버레이 전용 — 드래그 결과/취소를 main 으로 (handoff §60).
contextBridge.exposeInMainWorld("ohdoCapture", {
  done: (rect: { x: number; y: number; w: number; h: number }) =>
    ipcRenderer.send("capture:done", rect),
  cancel: () => ipcRenderer.send("capture:cancel"),
});

// run FX 오버레이 전용 — 커서/클릭/진행 상태 폴링 (handoff §79).
contextBridge.exposeInMainWorld("ohdoRunFx", {
  poll: () => ipcRenderer.invoke("runfx:poll"),
});

export type OhdoApi = typeof api;
