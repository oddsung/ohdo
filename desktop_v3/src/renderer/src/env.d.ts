/// <reference types="vite/client" />

// preload(src/preload/index.ts) 가 contextBridge 로 노출한 window.ohdo 의 타입.
// renderer 번들은 preload 모듈을 직접 import 하지 않으므로(런타임 분리), 여기서
// 구조적으로 동일한 인터페이스를 선언한다.
export interface ApiInfo {
  baseUrl: string;
  token: string;
}

export interface OhdoBridge {
  getApiInfo: () => Promise<ApiInfo | null>;
  // element picker 투명 오버레이 제어 (handoff §49).
  startPickOverlay: () => Promise<void>;
  stopPickOverlay: () => Promise<void>;
  // 작업 녹화 시 메인 윈도우 최소화/복원 (§49).
  minimizeForRecord: () => Promise<void>;
  restoreFromRecord: () => Promise<void>;
  // 코드 실행 완료 후 메인 윈도우를 앞으로 (§49).
  focusMainWindow: () => Promise<void>;
  // 프로젝트 내보내기/가져오기 (§47 #15).
  pickDirectory: () => Promise<string | null>;
  revealPath: (p: string) => Promise<void>;
}

declare global {
  interface Window {
    ohdo: OhdoBridge;
  }
}

// Vite ?worker 임포트 — vite/client 가 선언하지만 tsconfig types:["node"] 로
// 자동 로드가 제한될 수 있어 명시 선언 (Monaco worker 번들용).
declare module "*?worker" {
  const workerConstructor: { new (): Worker };
  export default workerConstructor;
}

export {};
