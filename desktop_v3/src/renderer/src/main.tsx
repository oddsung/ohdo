// SPDX-License-Identifier: AGPL-3.0-or-later
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./monacoSetup"; // Monaco 를 로컬 번들로 로드 (CDN/CSP 차단 회피) — App 보다 먼저
import "./i18n"; // i18next 초기화 (App 보다 먼저 — 첫 렌더에 언어 적용)
import App from "./App";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
