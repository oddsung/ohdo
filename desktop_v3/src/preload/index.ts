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
  // 작업 녹화 시 메인 윈도우 최소화/복원 (§49).
  minimizeForRecord: (): Promise<void> => ipcRenderer.invoke("record:minimize"),
  restoreFromRecord: (): Promise<void> => ipcRenderer.invoke("record:restore"),
  // 코드 실행 완료 후 메인 윈도우를 앞으로 (§49).
  focusMainWindow: (): Promise<void> => ipcRenderer.invoke("window:focus"),
  // 프로젝트 내보내기/가져오기 (§47 #15) — 네이티브 폴더 선택 + Explorer 열기.
  pickDirectory: (): Promise<string | null> => ipcRenderer.invoke("fs:pick-directory"),
  revealPath: (p: string): Promise<void> => ipcRenderer.invoke("fs:reveal", p),
};

contextBridge.exposeInMainWorld("ohdo", api);

// 오버레이 창 전용 — hover rect 폴링 (main 이 물리픽셀→오버레이 로컬 CSS px 변환).
contextBridge.exposeInMainWorld("ohdoPick", {
  hover: () => ipcRenderer.invoke("pick:hover"),
});

export type OhdoApi = typeof api;
