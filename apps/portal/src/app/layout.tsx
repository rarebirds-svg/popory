// 포털 전역 레이아웃.
import "./globals.css";
import type { ReactNode } from "react";

export const metadata = { title: "popory family" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
