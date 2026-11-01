// 포털 전역 레이아웃. 에디토리얼 폰트(Fraunces·Inter·Noto Sans KR)를 로드하고 토큰 변수를 노출한다.
//
// 폰트는 next/font/google 대신 @fontsource 패키지로 자체 호스팅한다(2026-11). next/font/google 은 빌드 때마다
// Google Fonts 에서 CSS·폰트 파일을 받아 오는데, Google 이 가끔 확장자 없는 파일 주소를 돌려주면 Next 15 로더가
// `Cannot read properties of null (reading '1')` 로 빌드를 멈췄다(CI·배포에서 반복). npm 패키지라 설치 때 받고
// 빌드는 네트워크를 쓰지 않는다. 굵기는 예전 설정과 같고, 한글은 unicode-range 조각으로 나뉘어 쓰는 글자만 받는다.
// 글꼴 이름(--font-*)은 globals.css 에서 정한다.
import "@fontsource/fraunces/500.css";
import "@fontsource/fraunces/600.css";
import "@fontsource/fraunces/700.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/noto-sans-kr/400.css";
import "@fontsource/noto-sans-kr/500.css";
import "@fontsource/noto-sans-kr/700.css";
import "./globals.css";
import type { ReactNode } from "react";

export const metadata = { title: "popory family" };
export const runtime = "edge";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen font-sans antialiased">{children}</body>
    </html>
  );
}
