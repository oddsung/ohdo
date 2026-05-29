// SPDX-License-Identifier: AGPL-3.0-or-later
// Monaco 를 **로컬 번들**로 로드하도록 설정 (handoff §40 후속 fix).
//
// @monaco-editor/react 는 기본적으로 jsdelivr CDN 에서 에디터를 받아오는데,
// Electron 렌더러의 CSP(connect-src 'self' + localhost 만 허용)가 그 요청을 차단해서
// 에디터가 "Loading..." 에서 멈춘다. 번들된 monaco-editor 패키지를 loader 에 주입하면
// 네트워크 요청 없이 동작한다.
import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
// 기본 에디터 worker (Vite 가 별도 청크로 번들 → blob/file 로 인스턴스화).
// Python 은 monaco 내장 토크나이저만 쓰므로 언어별 worker 불필요 — editor.worker 면 충분.
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";

(globalThis as unknown as { MonacoEnvironment: monaco.Environment }).MonacoEnvironment = {
  getWorker() {
    return new EditorWorker();
  },
};

loader.config({ monaco });
