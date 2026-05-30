import { resolve } from "path";
import react from "@vitejs/plugin-react";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";

// electron-vite 는 main / preload / renderer 3개 빌드 타깃을 한 config 로 관리한다.
// - main, preload: Node 환경. externalizeDepsPlugin 으로 node 의존성을 번들에서 제외.
// - renderer: 브라우저 환경. React + @ alias.
export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
  },
  renderer: {
    resolve: {
      alias: {
        "@": resolve("src/renderer/src"),
      },
    },
    plugins: [react()],
    build: {
      rollupOptions: {
        input: {
          // 메인 UI + element picker 오버레이(§49) + 영역 캡처 오버레이(§60) 3개 엔트리.
          index: resolve("src/renderer/index.html"),
          overlay: resolve("src/renderer/overlay.html"),
          capture_overlay: resolve("src/renderer/capture_overlay.html"),
        },
      },
    },
  },
});
