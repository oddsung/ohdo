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
  },
});
