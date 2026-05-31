// 포털 전역 레이아웃. 에디토리얼 폰트(Fraunces·Inter·Noto Sans KR)를 로드하고 토큰 변수를 노출한다.
import "./globals.css";
import type { ReactNode } from "react";
import { Fraunces, Inter, Noto_Sans_KR } from "next/font/google";

const fraunces = Fraunces({ subsets: ["latin"], weight: ["500", "600", "700"], variable: "--font-serif", display: "swap" });
const inter = Inter({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-sans", display: "swap" });
const notoKr = Noto_Sans_KR({ subsets: ["latin"], weight: ["400", "500", "700"], variable: "--font-sans-kr", display: "swap" });

export const metadata = { title: "popory family" };
export const runtime = "edge";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko" className={`${fraunces.variable} ${inter.variable} ${notoKr.variable}`}>
      <body className="min-h-screen font-sans antialiased">{children}</body>
    </html>
  );
}
