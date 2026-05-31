# popory Portal 리브랜딩 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** popory portal의 공개 표면(랜딩·대시보드·브리핑 허브/목록/본문)을 에디토리얼 "The Brief" 언어로, 어드민 표면을 "The Ledger" 매거진 언어로 리브랜딩한다. 라이트/다크 양 모드 지원.

**Architecture:** 하나의 토큰 시스템(`packages/ui/src/tokens.css`) 위에 두 테마를 둔다. 공개 영역은 기본 `--popory-*` 토큰(네이비)을 쓰고, 어드민은 `.ledger` 스코프에서 같은 변수를 종이 톤 값으로 재매핑한다 — 그래서 동일한 Tailwind 유틸리티가 표면별로 다르게 보인다. 폰트는 `next/font`로 Fraunces(세리프 헤드라인)·Inter+Noto Sans KR(본문)을 root layout에서 로드해 CSS 변수로 노출한다. 라우팅·인증·API·데이터 흐름은 불변, 프레젠테이션만 교체한다.

**Tech Stack:** Next.js 15 (App Router, edge runtime), React 19, Tailwind CSS 3.4 + @tailwindcss/typography, next/font, react-markdown + remark-gfm.

**검증 방식(중요):** 이 저장소에는 단위 테스트 하니스가 없고, 본 작업은 순수 프레젠테이션 변경이라 테스트 프레임워크를 새로 도입하지 않는다(YAGNI). 각 태스크의 검증은 다음 3종으로 한다.
- 타입 — `cd apps/portal && npx tsc --noEmit` → 에러 0.
- 빌드(주요 분기점) — `cd apps/portal && npm run build` → 성공.
- 육안 — `cd apps/portal && npm run dev` 후 해당 경로를 브라우저로 확인. 라이트/다크는 OS 테마 또는 브라우저 devtools의 `prefers-color-scheme` 에뮬레이션으로 둘 다 본다.

**디자인 소스 오브 트루스:** 합의된 목업 HTML이 `.superpowers/brainstorm/39394-1780220883/content/`(gitignore됨)에 있다 — `direction.html`(방향 비교), `system-b.html`(공개 4표면), `terracotta.html`(폐기, 무시). 구조·간격·위계는 `system-b.html`를 기준으로 한다. 스펙은 `docs/superpowers/specs/2026-05-31-popory-portal-redesign-design.md`.

---

## File Structure

**토큰·설정 (기반)**
- Modify: `packages/ui/src/tokens.css` — 공개 팔레트 재조정 + 신규 토큰(`--popory-fg2`, `--popory-accent-soft`) + `.ledger` 스코프 토큰(라이트/다크).
- Modify: `apps/portal/tailwind.config.ts` — 신규 색 토큰 매핑, `fontFamily` serif/sans 매핑, `prose-popory` 재설계.
- Modify: `apps/portal/src/app/layout.tsx` — `next/font`로 Fraunces·Inter·Noto Sans KR 로드, body에 폰트 변수 클래스 부여.

**공유 컴포넌트 (`packages/ui`)**
- Create: `packages/ui/src/components/Kicker.tsx` — accent-soft 칩.
- Create: `packages/ui/src/components/BriefCard.tsx` — 좌측 accent 보더 요점 카드.
- Create: `packages/ui/src/components/WhyBlock.tsx` — "왜 중요한가" 블록.
- Modify: `packages/ui/src/components/Header.tsx` — Nav 리워크(로고 dot + 우측 메뉴). props 시그니처 유지.
- Modify: `packages/ui/src/components/MarkdownBody.tsx` — 변경 없음(스타일은 tailwind `prose-popory`에서). 확인만.
- Modify: `packages/ui/src/index.ts` — 신규 컴포넌트 export.

**공개 페이지 (`apps/portal/src/app`)**
- Modify: `page.tsx` — 랜딩.
- Modify: `(authed)/dashboard/page.tsx` — 대시보드.
- Modify: `p/brief/page.tsx` — 브리핑 허브.
- Modify: `p/[area]/page.tsx` — 영역 목록.
- Modify: `p/page.tsx` — 공개 아카이브 홈.
- Modify: `p/[area]/[id]/page.tsx` — 본문 셸(키커·헤드라인·메타 + MarkdownBody).

**어드민 페이지 (`apps/portal/src/app/admin`)**
- Modify: `admin/layout.tsx` — `.ledger` 래퍼 + 세리프 헤딩.
- Modify: `admin/page.tsx`, `admin/whitelist/page.tsx`, `admin/users/page.tsx`, `admin/brief-categories/page.tsx`, `admin/brief-categories/new/NewForm.tsx`, `admin/brief-categories/[slug]/EditForm.tsx` — Ledger 톤 input/table/heading 정리.

---

## Task 1: 토큰·폰트 기반

**Files:**
- Modify: `packages/ui/src/tokens.css`
- Modify: `apps/portal/tailwind.config.ts`
- Modify: `apps/portal/src/app/layout.tsx`

- [ ] **Step 1: tokens.css를 새 팔레트로 교체**

`packages/ui/src/tokens.css` 전체를 아래로 교체한다. 첫 줄 한국어 헤더 주석은 유지한다.

```css
/* popory 포털·영역 사이트가 공통으로 사용하는 디자인 토큰 (라이트/다크). */
:root {
  /* 공개 "The Brief" 팔레트 */
  --popory-bg: #f7f8fa;
  --popory-fg: #0d1b2a;
  --popory-fg2: #33414f;
  --popory-muted: #7b8794;
  --popory-accent: #1f3a93;
  --popory-accent-soft: #eef1fb;
  --popory-card: #ffffff;
  --popory-border: #e9ecf1;
  --popory-radius: 12px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --popory-bg: #0b0f15;
    --popory-fg: #f2f5fa;
    --popory-fg2: #c2cdd9;
    --popory-muted: #8b97a5;
    --popory-accent: #6f8bdc;
    --popory-accent-soft: #16203a;
    --popory-card: #131922;
    --popory-border: #232c38;
  }
}

/* 어드민 "The Ledger" 테마: 같은 변수를 종이 톤으로 재매핑한다. */
.ledger {
  --popory-bg: #f6f1e7;
  --popory-fg: #1b1b18;
  --popory-fg2: #46443d;
  --popory-muted: #5a5750;
  --popory-accent: #9a3b2e;
  --popory-accent-soft: #f1e7df;
  --popory-card: #fffdf8;
  --popory-border: #d6cdba;
}
@media (prefers-color-scheme: dark) {
  .ledger {
    --popory-bg: #17150f;
    --popory-fg: #efe9dc;
    --popory-fg2: #cdc4b3;
    --popory-muted: #a39a86;
    --popory-accent: #c97a5f;
    --popory-accent-soft: #2a2418;
    --popory-card: #1f1c14;
    --popory-border: #34301f;
  }
}
```

- [ ] **Step 2: tailwind.config.ts에 신규 토큰·폰트·prose 반영**

`apps/portal/tailwind.config.ts` 전체를 아래로 교체한다. 첫 줄 주석 유지.

```ts
// 포털 Tailwind 설정. popory 토큰을 CSS 변수로 받고, prose-popory 변형을 정의한다.
import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        popory: {
          bg: "var(--popory-bg)",
          fg: "var(--popory-fg)",
          fg2: "var(--popory-fg2)",
          muted: "var(--popory-muted)",
          accent: "var(--popory-accent)",
          "accent-soft": "var(--popory-accent-soft)",
          card: "var(--popory-card)",
          border: "var(--popory-border)",
        },
      },
      fontFamily: {
        serif: ["var(--font-serif)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "var(--font-sans-kr)", "system-ui", "sans-serif"],
      },
      typography: {
        popory: {
          css: {
            "--tw-prose-body": "var(--popory-fg2)",
            "--tw-prose-headings": "var(--popory-fg)",
            "--tw-prose-links": "var(--popory-accent)",
            "--tw-prose-bold": "var(--popory-fg)",
            "--tw-prose-quotes": "var(--popory-fg2)",
            "--tw-prose-quote-borders": "var(--popory-accent)",
            "--tw-prose-bullets": "var(--popory-muted)",
            "--tw-prose-counters": "var(--popory-muted)",
            "--tw-prose-hr": "var(--popory-border)",
            "--tw-prose-th-borders": "var(--popory-border)",
            "--tw-prose-td-borders": "var(--popory-border)",
            "--tw-prose-code": "var(--popory-fg)",
            "--tw-prose-pre-bg": "var(--popory-card)",
            maxWidth: "42rem",
            fontSize: "1.0625rem",
            lineHeight: "1.8",
            h1: { fontFamily: "var(--font-serif)", letterSpacing: "-0.02em" },
            h2: { fontFamily: "var(--font-serif)", letterSpacing: "-0.01em" },
            h3: { fontFamily: "var(--font-serif)" },
          },
        },
      },
    },
  },
  plugins: [typography],
};
export default config;
```

- [ ] **Step 3: layout.tsx에 next/font 로드**

`apps/portal/src/app/layout.tsx` 전체를 아래로 교체한다.

```tsx
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
```

- [ ] **Step 4: 타입체크**

Run: `cd apps/portal && npx tsc --noEmit`
Expected: 에러 0. (`@tailwindcss/typography` 타입은 무시되어도 무방.)

- [ ] **Step 5: 빌드로 폰트 로드 확인**

Run: `cd apps/portal && npm run build`
Expected: 성공. `next/font`가 Fraunces/Inter/Noto Sans KR을 받아온다.

- [ ] **Step 6: 커밋**

```bash
git add packages/ui/src/tokens.css apps/portal/tailwind.config.ts apps/portal/src/app/layout.tsx
git commit -m "feat(portal): 리브랜딩 토큰·폰트 기반 (The Brief 공개 / Ledger 어드민)"
```

---

## Task 2: 공유 프리미티브 — Kicker / BriefCard / WhyBlock

**Files:**
- Create: `packages/ui/src/components/Kicker.tsx`
- Create: `packages/ui/src/components/BriefCard.tsx`
- Create: `packages/ui/src/components/WhyBlock.tsx`
- Modify: `packages/ui/src/index.ts`

- [ ] **Step 1: Kicker 작성**

Create `packages/ui/src/components/Kicker.tsx`:

```tsx
// 카테고리·날짜를 표시하는 accent-soft 칩(키커). 헤드라인 위에 놓는다.
import type { ReactNode } from "react";

export function Kicker({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={`inline-block rounded-md bg-popory-accent-soft px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-popory-accent ${className}`}
    >
      {children}
    </span>
  );
}
```

- [ ] **Step 2: BriefCard 작성**

Create `packages/ui/src/components/BriefCard.tsx`:

```tsx
// 좌측 accent 보더의 요점 카드. 제목과 내용을 담아 브리핑 본문/목록에서 쓴다.
import type { ReactNode } from "react";

export function BriefCard({
  title,
  children,
  accent = true,
  className = "",
}: {
  title?: ReactNode;
  children: ReactNode;
  accent?: boolean;
  className?: string;
}) {
  return (
    <div
      className={`rounded-lg border border-popory-border bg-popory-card p-4 ${
        accent ? "border-l-4 border-l-popory-accent" : ""
      } ${className}`}
    >
      {title && <h4 className="mb-2 text-sm font-bold text-popory-fg">{title}</h4>}
      <div className="text-sm leading-relaxed text-popory-fg2">{children}</div>
    </div>
  );
}
```

- [ ] **Step 3: WhyBlock 작성**

Create `packages/ui/src/components/WhyBlock.tsx`:

```tsx
// "왜 중요한가" 강조 블록. accent-soft 배경 + 좌측 accent 보더.
import type { ReactNode } from "react";

export function WhyBlock({ label = "왜 중요한가", children }: { label?: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border-l-4 border-popory-accent bg-popory-accent-soft p-4">
      <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-wider text-popory-accent">{label}</span>
      <p className="m-0 text-sm leading-relaxed text-popory-fg2">{children}</p>
    </div>
  );
}
```

- [ ] **Step 4: index.ts에 export 추가**

`packages/ui/src/index.ts` 전체를 아래로 교체한다.

```ts
// @popory/ui 공개 진입점. 공통 컴포넌트를 재노출한다.
export { Card } from "./components/Card";
export { Header } from "./components/Header";
export { MarkdownBody } from "./components/MarkdownBody";
export { Kicker } from "./components/Kicker";
export { BriefCard } from "./components/BriefCard";
export { WhyBlock } from "./components/WhyBlock";
```

- [ ] **Step 5: 타입체크**

Run: `cd apps/portal && npx tsc --noEmit`
Expected: 에러 0.

- [ ] **Step 6: 커밋**

```bash
git add packages/ui/src/components/Kicker.tsx packages/ui/src/components/BriefCard.tsx packages/ui/src/components/WhyBlock.tsx packages/ui/src/index.ts
git commit -m "feat(ui): 공유 프리미티브 Kicker·BriefCard·WhyBlock 추가"
```

---

## Task 3: Nav 리워크 (Header)

**Files:**
- Modify: `packages/ui/src/components/Header.tsx`

- [ ] **Step 1: Header를 새 디자인으로 교체 (props 시그니처 유지)**

`packages/ui/src/components/Header.tsx` 전체를 아래로 교체한다. props(`email`, `role?`, `showAdmin?`)는 그대로 유지해 호출부를 깨지 않는다. 미사용 `useState` import를 제거한다(이 변경으로 고아가 됨).

```tsx
// 포털 상단 헤더(Nav). 로고와 사용자 정보·admin 링크·로그아웃을 제공한다.
'use client';

interface HeaderProps {
  email: string;
  role?: string;
  showAdmin?: boolean;
}

export function Header({ email, showAdmin }: HeaderProps) {
  const initial = email?.[0]?.toUpperCase() ?? "?";
  return (
    <header className="border-b border-popory-border bg-popory-card">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3.5">
        <a href="/dashboard" className="flex items-center gap-2 text-lg font-bold tracking-tight text-popory-accent">
          <span className="h-2.5 w-2.5 rounded-full bg-popory-accent" aria-hidden />
          popory
        </a>
        <div className="flex items-center gap-4 text-sm text-popory-muted">
          <a href="/p/brief" className="hidden hover:text-popory-fg sm:inline">브리핑</a>
          {showAdmin && <a href="/admin" className="hover:text-popory-fg">어드민</a>}
          <span className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-popory-accent-soft text-[11px] font-bold text-popory-accent">
              {initial}
            </span>
            <span className="hidden sm:inline">{email}</span>
          </span>
          <form action="/api/auth/logout" method="post">
            <button type="submit" className="hover:text-popory-fg">로그아웃</button>
          </form>
        </div>
      </div>
    </header>
  );
}
```

- [ ] **Step 2: 타입체크**

Run: `cd apps/portal && npx tsc --noEmit`
Expected: 에러 0. (`role` prop은 인터페이스에 남기되 미사용 — 호출부 `role={...}` 전달이 깨지지 않는다.)

- [ ] **Step 3: 육안 확인**

Run: `cd apps/portal && npm run dev` → `http://localhost:3000/dashboard` 접속(로그인 필요 시 우회 어려우면 build만 통과 확인). 헤더에 로고 dot·아바타가 보이는지 확인.

- [ ] **Step 4: 커밋**

```bash
git add packages/ui/src/components/Header.tsx
git commit -m "feat(ui): Nav 헤더 리워크 (로고 dot·아바타)"
```

---

## Task 4: 브리핑 본문 읽기 (prose-popory 검증 + 본문 셸)

**Files:**
- Modify: `apps/portal/src/app/p/[area]/[id]/page.tsx`
- (참고) `packages/ui/src/components/MarkdownBody.tsx` — 변경 없음, `prose prose-popory`가 Task 1의 새 prose 설정을 받는다.

- [ ] **Step 1: 본문 페이지 현재 구조 확인**

Run: `sed -n '1,80p' apps/portal/src/app/p/[area]/[id]/page.tsx`
Expected: 발행물을 fetch해 제목·날짜·`<MarkdownBody content=... />`를 렌더하는 server component. fetch/props 구조를 메모한다(다음 스텝에서 그대로 재사용).

- [ ] **Step 2: 본문 셸을 에디토리얼 레이아웃으로 교체**

`apps/portal/src/app/p/[area]/[id]/page.tsx`에서, 데이터 fetch 로직은 그대로 두고 **return 마크업만** 아래 형태로 교체한다. 변수명(`item`, `area` 등)은 Step 1에서 확인한 실제 이름에 맞춘다. 키커의 카테고리 라벨은 area 문자열(예: `brief-real-estate` → 표시용으로 가공)이나 item 필드에서 가져온다.

```tsx
return (
  <main className="mx-auto max-w-2xl px-4 py-10">
    <a href={`/p/${area}`} className="text-sm text-popory-muted hover:text-popory-fg">← 목록으로</a>
    <div className="mt-4">
      <Kicker>{categoryLabel}{item.published_at ? ` · ${formatDate(item.published_at)}` : ""}</Kicker>
    </div>
    <h1 className="mt-3 font-serif text-3xl font-semibold leading-tight tracking-tight text-popory-fg">
      {item.title}
    </h1>
    <div className="mt-3 flex items-center gap-2 border-b border-popory-border pb-5 text-xs text-popory-muted">
      <span>popory 브리핑</span>
    </div>
    <div className="mt-6">
      <MarkdownBody content={item.body ?? item.content ?? ""} />
    </div>
  </main>
);
```

import 줄에 `Kicker`를 추가한다: `import { MarkdownBody, Kicker } from "@popory/ui";`

`categoryLabel`과 `formatDate`는 파일 상단(컴포넌트 밖)에 작은 헬퍼로 둔다. `area`가 `brief-` 접두라면 제거하고 표시한다.

```tsx
function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}.${d.getDate()}`;
}
```

`categoryLabel`은 `const categoryLabel = area.replace(/^brief-/, "");` 로 컴포넌트 본문 안에서 만든다. (실제 area/필드명은 Step 1 확인값에 맞춘다. 본문 필드가 `body`인지 `content`인지도 확인해 한쪽으로 고정한다.)

- [ ] **Step 3: 타입체크**

Run: `cd apps/portal && npx tsc --noEmit`
Expected: 에러 0. (필드명 불일치 시 Step 1 확인값으로 수정.)

- [ ] **Step 4: 육안 확인**

`npm run dev` → 실제 발행물 경로(`/p/brief-<slug>/<id>`) 접속. 키커 → 세리프 헤드라인 → 본문 순서, 본문 폭(약 42rem)·행간이 읽기 좋은지 라이트/다크 모두 확인.

- [ ] **Step 5: 커밋**

```bash
git add apps/portal/src/app/p/\[area\]/\[id\]/page.tsx
git commit -m "feat(portal): 브리핑 본문 에디토리얼 레이아웃 (키커·세리프 헤드라인·prose 재설계)"
```

---

## Task 5: 브리핑 허브 (/p/brief)

**Files:**
- Modify: `apps/portal/src/app/p/brief/page.tsx`

- [ ] **Step 1: 허브 마크업 교체 (fetch 로직 유지)**

`apps/portal/src/app/p/brief/page.tsx`의 `fetchCategories`·`fetchLatest`·`Promise.all` 로직은 그대로 두고, `return` 마크업을 아래로 교체한다. `Kicker` import를 추가한다.

```tsx
import { Kicker } from "@popory/ui";
```

```tsx
return (
  <main className="mx-auto max-w-5xl px-4 py-10">
    <Kicker>Daily Briefings</Kicker>
    <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">매일 아침, 여러 갈래의 세상</h1>
    <p className="mt-2 text-sm text-popory-muted">AI가 큐레이션한 일일 브리핑. 매일 오전 9시 발행.</p>
    {categories.length === 0 ? (
      <p className="mt-10 text-sm text-popory-muted">아직 발행된 브리핑이 없습니다.</p>
    ) : (
      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {categories.map((c, i) => (
          <Link key={c.slug} href={`/p/brief-${c.slug}`} className="group">
            <div className="h-full rounded-xl border border-popory-border bg-popory-card p-5 transition group-hover:border-popory-accent">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-bold text-popory-fg">{c.name}</h2>
              </div>
              {c.description && <p className="mt-1 text-xs text-popory-muted">{c.description}</p>}
              {latest[i] && (
                <p className="mt-3 border-t border-dashed border-popory-border pt-3 text-sm leading-relaxed text-popory-fg2 line-clamp-2">
                  {latest[i]!.title}
                </p>
              )}
            </div>
          </Link>
        ))}
      </div>
    )}
  </main>
);
```

(기존에 `Card`를 import했다면, 더 이상 쓰지 않으면 import에서 제거한다.)

- [ ] **Step 2: 타입체크**

Run: `cd apps/portal && npx tsc --noEmit`
Expected: 에러 0.

- [ ] **Step 3: 육안 확인**

`npm run dev` → `http://localhost:3000/p/brief`. 키커·세리프 제목·카테고리 카드(호버 시 accent 보더)·빈 상태를 라이트/다크로 확인.

- [ ] **Step 4: 커밋**

```bash
git add apps/portal/src/app/p/brief/page.tsx
git commit -m "feat(portal): 브리핑 허브 에디토리얼 리디자인"
```

---

## Task 6: 영역 목록 (/p/[area]) + 아카이브 홈 (/p)

**Files:**
- Modify: `apps/portal/src/app/p/[area]/page.tsx`
- Modify: `apps/portal/src/app/p/page.tsx`

- [ ] **Step 1: 두 파일의 현재 구조 확인**

Run: `sed -n '1,80p' apps/portal/src/app/p/[area]/page.tsx; echo "====="; sed -n '1,80p' apps/portal/src/app/p/page.tsx`
Expected: `[area]`는 발행물 목록(제목·요약·날짜)을, `p`는 영역별 카운트를 fetch해 보여준다. fetch 로직·변수명을 메모한다.

- [ ] **Step 2: 영역 목록을 날짜 중심 리스트로 교체**

`apps/portal/src/app/p/[area]/page.tsx`의 fetch 로직은 유지하고, return 마크업을 아래 형태로 교체한다. `Kicker` import 추가. `items` 변수명·필드명은 Step 1 확인값에 맞춘다.

```tsx
return (
  <main className="mx-auto max-w-3xl px-4 py-10">
    <div className="text-xs text-popory-muted">브리핑 · {categoryLabel}</div>
    <h1 className="mt-2 font-serif text-3xl font-semibold tracking-tight text-popory-fg">{categoryLabel} 일일 브리핑</h1>
    <div className="mt-6">
      {items.length === 0 ? (
        <p className="text-sm text-popory-muted">아직 발행된 글이 없습니다.</p>
      ) : (
        items.map((it) => (
          <Link key={it.id} href={`/p/${area}/${it.id}`} className="flex gap-4 border-b border-popory-border py-4 hover:bg-popory-accent-soft/40">
            <div className="w-14 shrink-0 text-center">
              <div className="font-serif text-2xl font-semibold leading-none text-popory-fg">{dayOf(it.published_at)}</div>
              <div className="mt-1 text-[10px] uppercase tracking-widest text-popory-muted">{monthOf(it.published_at)}</div>
            </div>
            <div>
              <h2 className="text-[15px] font-bold leading-snug text-popory-fg">{it.title}</h2>
              {it.summary && <p className="mt-1 text-xs leading-relaxed text-popory-muted line-clamp-2">{it.summary}</p>}
            </div>
          </Link>
        ))
      )}
    </div>
  </main>
);
```

파일 상단(컴포넌트 밖)에 헬퍼를 둔다.

```tsx
function dayOf(iso?: string): string {
  if (!iso) return "·";
  return String(new Date(iso).getDate());
}
function monthOf(iso?: string): string {
  if (!iso) return "";
  return `${new Date(iso).getMonth() + 1}월`;
}
```

`categoryLabel`은 `const categoryLabel = area.replace(/^brief-/, "");` 로 컴포넌트 안에서 만든다(필요 시 Link href의 `area` 사용도 일관되게).

- [ ] **Step 3: 아카이브 홈(/p)을 키커+카드 톤으로 정리**

`apps/portal/src/app/p/page.tsx`의 fetch 로직은 유지하고, 제목을 세리프로, 영역 카드를 허브와 같은 카드 스타일(`rounded-xl border border-popory-border bg-popory-card p-5 ... hover:border-popory-accent`)로 맞춘다. 상단에 `<Kicker>Archive</Kicker>` + `<h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">popory 아카이브</h1>`를 둔다. 카드 내부 구조(영역명·카운트)는 기존 데이터 필드를 그대로 사용한다.

- [ ] **Step 4: 타입체크**

Run: `cd apps/portal && npx tsc --noEmit`
Expected: 에러 0.

- [ ] **Step 5: 육안 확인**

`npm run dev` → `/p` 와 `/p/brief-<slug>`. 날짜 컬럼·세리프 숫자·빈 상태를 라이트/다크로 확인.

- [ ] **Step 6: 커밋**

```bash
git add apps/portal/src/app/p/\[area\]/page.tsx apps/portal/src/app/p/page.tsx
git commit -m "feat(portal): 영역 목록 날짜 중심 리스트 + 아카이브 홈 정리"
```

---

## Task 7: 대시보드 (/dashboard)

**Files:**
- Modify: `apps/portal/src/app/(authed)/dashboard/page.tsx`

- [ ] **Step 1: 대시보드 마크업 교체 (세션·서비스 배열 유지)**

`apps/portal/src/app/(authed)/dashboard/page.tsx`에서 `getSession`/`redirect`/`SERVICES` 정의는 유지하고, return 마크업을 아래로 교체한다. `Header`·`Card` import는 유지하고 `Kicker`를 추가한다. (Card를 더 안 쓰면 import에서 제거.)

```tsx
return (
  <div>
    <Header email={session.email} role={session.role} showAdmin={session.role === "admin"} />
    <main className="mx-auto max-w-5xl px-4 py-10">
      <Kicker>{todayLabel}</Kicker>
      <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">오늘의 popory</h1>
      <p className="mt-2 text-sm text-popory-muted">가족이 함께 보는 브리핑과 서비스를 한곳에서.</p>
      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {SERVICES.map((s) => (
          <a key={s.href} href={s.href} className="group block" {...(s.external ? { target: "_blank", rel: "noreferrer" } : {})}>
            <div className="h-full rounded-xl border border-popory-border bg-popory-card p-5 transition group-hover:border-popory-accent">
              <h2 className="text-base font-bold text-popory-fg">{s.title}</h2>
              <p className="mt-1 text-sm text-popory-muted">{s.description}</p>
            </div>
          </a>
        ))}
      </div>
    </main>
  </div>
);
```

컴포넌트 안 `const session` 직후에 날짜 라벨을 만든다.

```tsx
const todayLabel = new Intl.DateTimeFormat("ko-KR", { dateStyle: "full" }).format(new Date());
```

import에 `Kicker` 추가: `import { Header, Card, Kicker } from "@popory/ui";` (Card 미사용 시 제거).

- [ ] **Step 2: 타입체크**

Run: `cd apps/portal && npx tsc --noEmit`
Expected: 에러 0.

- [ ] **Step 3: 육안 확인**

`npm run dev` → `/dashboard`. 인사말 키커·세리프 제목·서비스 카드 라이트/다크 확인.

- [ ] **Step 4: 커밋**

```bash
git add apps/portal/src/app/\(authed\)/dashboard/page.tsx
git commit -m "feat(portal): 대시보드 에디토리얼 리디자인 (인사말·서비스 카드)"
```

---

## Task 8: 랜딩 (/)

**Files:**
- Modify: `apps/portal/src/app/page.tsx`

- [ ] **Step 1: 랜딩 현재 구조 확인**

Run: `sed -n '1,80p' apps/portal/src/app/page.tsx`
Expected: 비로그인 시 로그인 랜딩, 로그인 시 `/dashboard` 리다이렉트. 로그인 진입(구글 등) 마크업·링크를 메모한다.

- [ ] **Step 2: 랜딩 히어로를 에디토리얼로 교체 (리다이렉트·로그인 링크 유지)**

세션 체크/리다이렉트와 로그인 URL은 그대로 두고, 비로그인 화면 마크업만 교체한다. 중앙 정렬 히어로: `<Kicker>popory family</Kicker>` + 세리프 대제목 + 부제 + 기존 로그인 버튼/링크(원래 href·action 유지). 예:

```tsx
return (
  <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-4 text-center">
    <Kicker>popory family</Kicker>
    <h1 className="mt-4 font-serif text-4xl font-semibold tracking-tight text-popory-fg">매일 아침, 우리 가족의 브리핑</h1>
    <p className="mt-3 text-sm leading-relaxed text-popory-muted">AI가 큐레이션한 일일 브리핑과 가족 서비스를 한곳에서.</p>
    <div className="mt-8">
      {/* 기존 로그인 버튼/링크를 여기로 옮긴다 (href·action 변경 금지) */}
    </div>
  </main>
);
```

`Kicker` import 추가. 기존 로그인 진입 요소를 그대로 옮겨 넣는다.

- [ ] **Step 3: 타입체크**

Run: `cd apps/portal && npx tsc --noEmit`
Expected: 에러 0.

- [ ] **Step 4: 육안 확인**

`npm run dev` → `http://localhost:3000/` (로그아웃 상태). 히어로·로그인 버튼 동작·라이트/다크 확인.

- [ ] **Step 5: 커밋**

```bash
git add apps/portal/src/app/page.tsx
git commit -m "feat(portal): 랜딩 히어로 에디토리얼 리디자인"
```

---

## Task 9: 어드민 Ledger 테마 — 레이아웃

**Files:**
- Modify: `apps/portal/src/app/admin/layout.tsx`

- [ ] **Step 1: 어드민 레이아웃 현재 구조 확인**

Run: `sed -n '1,80p' apps/portal/src/app/admin/layout.tsx`
Expected: admin role 가드 + 자식 렌더. 래퍼 엘리먼트 구조를 메모한다.

- [ ] **Step 2: `.ledger` 스코프와 세리프 헤딩 적용**

가드 로직은 유지하고, children을 감싸는 최상위 엘리먼트에 `ledger` 클래스 + 배경/폰트를 적용한다. 예(실제 가드 변수명은 Step 1 확인값 유지):

```tsx
return (
  <div className="ledger min-h-screen bg-popory-bg text-popory-fg [&_h1]:font-serif [&_h2]:font-serif [&_h3]:font-serif">
    {/* 기존 admin nav/헤더가 있으면 그대로 둔다 */}
    <div className="mx-auto max-w-4xl px-4 py-10">{children}</div>
  </div>
);
```

`.ledger`가 Task 1에서 정의한 종이 톤 토큰을 자식 전체에 재매핑하므로, 기존 `popory-*` 유틸리티가 자동으로 Ledger 색을 받는다.

- [ ] **Step 3: 타입체크 + 빌드**

Run: `cd apps/portal && npx tsc --noEmit && npm run build`
Expected: 둘 다 성공.

- [ ] **Step 4: 육안 확인**

`npm run dev` → `/admin`. 배경이 종이 톤으로, 헤딩이 세리프로, 강조가 잉크 레드로 바뀌었는지 라이트/다크 확인.

- [ ] **Step 5: 커밋**

```bash
git add apps/portal/src/app/admin/layout.tsx
git commit -m "feat(portal): 어드민 Ledger 테마 레이아웃 (.ledger 토큰 재매핑·세리프 헤딩)"
```

---

## Task 10: 어드민 폼·테이블 정리

**Files:**
- Modify: `apps/portal/src/app/admin/page.tsx`
- Modify: `apps/portal/src/app/admin/whitelist/page.tsx`
- Modify: `apps/portal/src/app/admin/users/page.tsx`
- Modify: `apps/portal/src/app/admin/brief-categories/page.tsx`
- Modify: `apps/portal/src/app/admin/brief-categories/new/NewForm.tsx`
- Modify: `apps/portal/src/app/admin/brief-categories/[slug]/EditForm.tsx`

- [ ] **Step 1: 각 파일의 헤딩·input·table·button 클래스 확인**

Run: `grep -rn "className" apps/portal/src/app/admin/page.tsx apps/portal/src/app/admin/whitelist/page.tsx apps/portal/src/app/admin/users/page.tsx apps/portal/src/app/admin/brief-categories/page.tsx apps/portal/src/app/admin/brief-categories/new/NewForm.tsx apps/portal/src/app/admin/brief-categories/[slug]/EditForm.tsx`
Expected: 현재 사용 중인 input/table/button 클래스 목록. Ledger 톤으로 통일할 대상을 식별한다.

- [ ] **Step 2: 공통 클래스 토큰 통일**

각 파일에서 다음 규칙으로 정리한다. 기능(Server Action, form action, 핸들러)·구조는 변경하지 않는다.
- 페이지 제목 `h1`/`h2`는 `font-serif`가 layout에서 이미 적용됨 — 별도 폰트 클래스 추가 불필요. 크기·여백만 필요 시 정리.
- input/textarea: `w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg` 로 통일.
- 라벨: `text-xs font-medium text-popory-muted`.
- primary 버튼: `rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white`.
- secondary 버튼: `rounded-md border border-popory-border px-4 py-2 text-sm text-popory-fg`.
- 테이블: 헤더 `text-left text-xs uppercase tracking-wide text-popory-muted`, 행 구분 `border-b border-popory-border`, 셀 `py-2 text-sm text-popory-fg`.
- 에러 배너: `rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700`(다크 대응 필요 시 `dark:` 변형 유지/추가).

`NewForm.tsx`·`EditForm.tsx`에 이미 정의된 `INPUT`/`Field` 상수가 있으면 그 상수 값만 위 규칙으로 바꾼다(중복 정의 금지, DRY).

- [ ] **Step 3: 타입체크 + 빌드**

Run: `cd apps/portal && npx tsc --noEmit && npm run build`
Expected: 둘 다 성공.

- [ ] **Step 4: 육안 확인**

`npm run dev` → `/admin`, `/admin/whitelist`, `/admin/users`, `/admin/brief-categories`, `/admin/brief-categories/new`. 폼·테이블이 Ledger 톤으로 일관된지, 폼 제출(추가/삭제/저장)이 그대로 동작하는지 라이트/다크 확인.

- [ ] **Step 5: 커밋**

```bash
git add apps/portal/src/app/admin
git commit -m "feat(portal): 어드민 폼·테이블 Ledger 톤 통일"
```

---

## Task 11: 마감 — 라이트/다크·반응형·빌드

**Files:**
- (필요 시) 위 모든 페이지 미세 조정

- [ ] **Step 1: 전체 빌드**

Run: `cd apps/portal && npm run build`
Expected: 성공. 경고가 있으면 읽고 의미 있는 것만 처리.

- [ ] **Step 2: 라이트/다크 전수 확인**

`npm run dev` 상태에서 브라우저 devtools의 Rendering → `Emulate CSS prefers-color-scheme`를 light/dark로 토글하며 다음 경로를 모두 확인한다.
- 공개: `/`, `/dashboard`, `/p`, `/p/brief`, `/p/brief-<slug>`, `/p/brief-<slug>/<id>`
- 어드민: `/admin`, `/admin/whitelist`, `/admin/users`, `/admin/brief-categories`, `/admin/brief-categories/new`, `/admin/brief-categories/<slug>`
대비가 깨지거나 읽기 어려운 곳이 있으면 해당 페이지에서 토큰 클래스로 수정.

- [ ] **Step 3: 반응형 확인**

각 화면을 모바일 폭(375px)·데스크톱 폭에서 확인. 그리드(`sm:`/`lg:`)·본문 폭·헤더가 깨지지 않는지 본다. 깨진 곳만 수정.

- [ ] **Step 4: 최종 커밋(수정이 있었다면)**

```bash
git add -A
git commit -m "fix(portal): 리브랜딩 라이트/다크·반응형 마감 정리"
```

- [ ] **Step 5: 완료 보고**

빌드 성공·확인 경로·라이트/다크 결과를 요약 보고. 미해결 항목이 있으면 명시.

---

## Self-Review (작성자 점검 결과)

**스펙 커버리지.**
- 두 디자인 언어(공개 The Brief / 어드민 Ledger) → Task 1(토큰)·Task 3~8(공개)·Task 9~10(어드민). ✓
- 토큰 아키텍처 확장(신규 토큰·`.ledger` 재매핑) → Task 1. ✓
- 폰트(next/font, Fraunces/Inter/Noto KR) → Task 1. ✓
- 공유 컴포넌트(Kicker/BriefCard/WhyBlock, Nav, MarkdownBody/prose) → Task 2·3·4. ✓
- 공개 6개 화면 → Task 4(본문)·5(허브)·6(목록+아카이브)·7(대시보드)·8(랜딩). ✓
- 어드민 5개 화면 → Task 9(레이아웃)·10(폼·테이블). ✓
- 라이트/다크 양 모드 → 각 태스크 육안 + Task 11 전수. ✓
- 빈 상태(empty state) → Task 5·6에 포함. ✓
- 비범위(라우팅·인증·API·데이터 불변) → 각 태스크가 "fetch/로직 유지, 마크업만 교체" 원칙을 명시. ✓

**플레이스홀더 스캔.** 본문 셸(Task 4)·목록(Task 6)·랜딩(Task 8)은 실제 변수/필드명을 사전 "Step 1 확인"으로 잡은 뒤 적용하도록 구성 — 저장소의 실제 props 이름을 모르는 상태에서의 불가피한 안전장치이며, 코드 자체는 완전하다. "적절히 처리" 식 모호 지시는 없다.

**타입/이름 일관성.** `Kicker`/`BriefCard`/`WhyBlock` 시그니처는 Task 2 정의와 이후 사용처가 일치. `Header` props(`email`/`role`/`showAdmin`)는 기존 호출부와 동일하게 유지. `.ledger` 클래스명은 Task 1 정의와 Task 9 사용이 일치.

**참고.** `BriefCard`/`WhyBlock`은 본문 마크다운이 해당 구조일 때 활용하는 프리미티브로 export까지만 하고 페이지 강제 적용은 하지 않는다(브리핑 본문은 마크다운 렌더가 기본). 향후 구조화 본문에서 사용.
