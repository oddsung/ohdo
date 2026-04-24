import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ohdo.ai",
  description: "AI 로 Windows 데스크톱/웹 자동화를 만드는 ohdo.ai 대시보드.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
