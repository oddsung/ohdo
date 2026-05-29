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
};

contextBridge.exposeInMainWorld("ohdo", api);

export type OhdoApi = typeof api;
