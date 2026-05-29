/** @type {import('tailwindcss').Config} */
// Discord-like 다크 테마 (handoff §37 참조 UX) + shadcn/ui CSS 변수 토큰.
// 색은 src/renderer/src/index.css 의 :root.dark 변수로 정의 (테마 토글 대비).
import animate from "tailwindcss-animate";

export default {
  darkMode: "class",
  content: ["./src/renderer/index.html", "./src/renderer/src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Discord 3-column 표면색 — CSS 변수(RGB 채널)로 테마 토글 + 투명도 동시 지원.
        // 값은 index.css 의 :root(light) / .dark 에서 정의.
        discord: {
          bg: "rgb(var(--d-bg) / <alpha-value>)", // 메인 채팅 영역
          sidebar: "rgb(var(--d-sidebar) / <alpha-value>)", // 세션 사이드바
          rail: "rgb(var(--d-rail) / <alpha-value>)", // 좌측 서버 레일 + 최외곽
          card: "rgb(var(--d-card) / <alpha-value>)", // 카드/입력 배경
          text: "rgb(var(--d-text) / <alpha-value>)", // 본문 텍스트
          muted: "rgb(var(--d-muted) / <alpha-value>)", // 보조 텍스트
          accent: "rgb(var(--d-accent) / <alpha-value>)", // blurple
          green: "rgb(var(--d-green) / <alpha-value>)", // 온라인/성공
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [animate],
};
