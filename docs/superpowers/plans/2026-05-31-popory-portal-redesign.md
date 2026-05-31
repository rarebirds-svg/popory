# popory Portal 리브랜딩 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** popory portal의 공개 표면(랜딩·대시보드·브리핑 허브/목록/본문)을 에디토리얼 "The Brief" 언어로, 어드민 표면을 "The Ledger" 매거진 언어로 리브랜딩한다. 라이트/다크 양 모드 지원.

**Architecture:** 하나의 토큰 시스템(`packages/ui/src/tokens.css`) 위에 두 테마를 둔다. 공개 영역은 기본 `--popory-*` 토큰(네이비)을 쓰고, 어드민은 `.ledger` 스코프에서 같은 변수를 종이 톤 값으로 재매핑한다 — 그래서 동일한 Tailwind 유틸리티가 표면별로 다르게 보인다. 폰트는 `next/font`로 Fraunces(세리프 헤드라인)·Inter+Noto Sans KR(본문)을 root layout에서 로드해 CSS 변수로 노출한다. 라우팅·인증·API·데이터 흐름은 불변, 프레젠테이션만 교체한다.

**Tech Stack:** Next.js 15 (App Router, edge runtime), React 19, Tailwind CSS 3.4 + @tailwindcss/typography, next/font, react-markdown + remark-gfm. 모노레포는 pnpm + turbo. portal은 `@popory/portal`, 공유 UI는 `@popory/ui`(node_modules 심볼릭 링크).

**검증 방식(중요):** portal에는 단위 테스트 하니스가 없고(플레이wright e2e 스캐폴드만 존재), 본 작업은 순수 프레젠테이션 변경이라 테스트 프레임워크를 새로 도입하지 않는다(YAGNI). 각 태스크의 검증은 다음 3종으로 한다.
- 타입 — `pnpm -C apps/portal typecheck` → 에러 0.
- 빌드(주요 분기점) — `pnpm -C apps/portal build` → 성공.
- 육안 — `pnpm -C apps/portal dev` 후 해당 경로를 브라우저로 확인. 라이트/다크는 OS 테마 또는 브라우저 devtools의 `prefers-color-scheme` 에뮬레이션으로 둘 다 본다.

**디자인 소스 오브 트루스:** 합의된 목업 HTML이 `.superpowers/brainstorm/39394-1780220883/content/`(gitignore됨)에 있다 — `system-b.html`(공개 4표면)이 구조·간격·위계의 기준. 스펙은 `docs/superpowers/specs/2026-05-31-popory-portal-redesign-design.md`.

**현 코드 사실(플랜 전제):**
- `Header` 시그니처는 `{ email, role: "member"|"admin", apiBase }`. 로그아웃은 `${apiBase}/api/logout`. (서버 컴포넌트, `'use client'` 없음.)
- `@popory/ui` index.ts는 `import "./tokens.css";` 를 포함한다 — 이 import는 반드시 유지.
- 마크다운 렌더는 `apps/portal/src/app/p/[area]/[id]/markdown-body.tsx`의 로컬 `MarkdownBody`. `@popory/ui`에는 없음.
- `published_at`은 **유닉스 초(number)**. 표시는 `new Date(published_at * 1000)`.
- 본문 상세 필드는 `item.body`(마크다운 문자열). 목록/허브 아이템은 `{ id, title, summary, published_at }`.

---

## File Structure

**토큰·설정 (기반)**
- Modify: `packages/ui/src/tokens.css` — 공개 팔레트 재조정 + 신규 토큰(`--popory-fg2`, `--popory-accent-soft`) + `.ledger` 스코프 토큰(라이트/다크).
- Modify: `apps/portal/tailwind.config.ts` — 신규 색 토큰 매핑, `fontFamily` serif/sans, `prose-popory` 재설계.
- Modify: `apps/portal/src/app/layout.tsx` — `next/font`로 Fraunces·Inter·Noto Sans KR 로드, html에 폰트 변수 클래스 부여.

**공유 컴포넌트 (`packages/ui`)**
- Create: `packages/ui/src/components/Kicker.tsx`
- Create: `packages/ui/src/components/BriefCard.tsx`
- Create: `packages/ui/src/components/WhyBlock.tsx`
- Modify: `packages/ui/src/components/Header.tsx` — Nav 리워크(로고 dot + 아바타). props 시그니처 유지.
- Modify: `packages/ui/src/index.ts` — tokens.css import 유지 + 신규 컴포넌트 export.

**공개 페이지 (`apps/portal/src/app`)**
- Modify: `page.tsx`(랜딩), `(authed)/dashboard/page.tsx`, `p/brief/page.tsx`, `p/[area]/page.tsx`, `p/page.tsx`, `p/[area]/[id]/page.tsx`.

**어드민 페이지 (`apps/portal/src/app/admin`)**
- Modify: `admin/layout.tsx`(.ledger 래퍼) + `admin/page.tsx`, `admin/whitelist/page.tsx`, `admin/users/page.tsx`, `admin/brief-categories/page.tsx`, `admin/brief-categories/new/NewForm.tsx`, `admin/brief-categories/[slug]/EditForm.tsx`.

---

## Task 1: 토큰·폰트 기반

**Files:**
- Modify: `packages/ui/src/tokens.css`
- Modify: `apps/portal/tailwind.config.ts`
- Modify: `apps/portal/src/app/layout.tsx`

- [ ] **Step 1: tokens.css를 새 팔레트로 교체**

`packages/ui/src/tokens.css` 전체를 아래로 교체한다.

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

`apps/portal/tailwind.config.ts` 전체를 아래로 교체한다.

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

Run: `pnpm -C apps/portal typecheck`
Expected: 에러 0.

- [ ] **Step 5: 빌드로 폰트 로드 확인**

Run: `pnpm -C apps/portal build`
Expected: 성공.

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

- [ ] **Step 4: index.ts에 export 추가 (tokens.css import 유지)**

`packages/ui/src/index.ts` 전체를 아래로 교체한다. **`import "./tokens.css";` 줄을 반드시 유지한다** (이게 빠지면 전 사이트 토큰이 깨진다). `MarkdownBody`는 `@popory/ui`에 없으므로 export하지 않는다.

```ts
// @popory/ui 공개 진입점. 토큰과 공통 컴포넌트를 재노출한다.
import "./tokens.css";
export { Card } from "./components/Card";
export { Header } from "./components/Header";
export { Kicker } from "./components/Kicker";
export { BriefCard } from "./components/BriefCard";
export { WhyBlock } from "./components/WhyBlock";
```

- [ ] **Step 5: 타입체크**

Run: `pnpm -C apps/portal typecheck`
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

`packages/ui/src/components/Header.tsx` 전체를 아래로 교체한다. props(`email`, `role`, `apiBase`)와 로그아웃 endpoint(`${apiBase}/api/logout`)는 그대로 유지해 호출부를 깨지 않는다.

```tsx
// 포털 상단 헤더(Nav). 로고와 사용자 정보·admin 링크·로그아웃을 제공한다.
export function Header({ email, role, apiBase }: { email: string; role: "member" | "admin"; apiBase: string }) {
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
          {role === "admin" && <a href="/admin" className="hover:text-popory-fg">어드민</a>}
          <span className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-popory-accent-soft text-[11px] font-bold text-popory-accent">
              {initial}
            </span>
            <span className="hidden sm:inline">{email}</span>
          </span>
          <form action={`${apiBase}/api/logout`} method="post">
            <button type="submit" className="hover:text-popory-fg">로그아웃</button>
          </form>
        </div>
      </div>
    </header>
  );
}
```

- [ ] **Step 2: 타입체크**

Run: `pnpm -C apps/portal typecheck`
Expected: 에러 0.

- [ ] **Step 3: 커밋**

```bash
git add packages/ui/src/components/Header.tsx
git commit -m "feat(ui): Nav 헤더 리워크 (로고 dot·아바타)"
```

---

## Task 4: 브리핑 본문 읽기 (prose-popory + 본문 셸)

**Files:**
- Modify: `apps/portal/src/app/p/[area]/[id]/page.tsx`
- (변경 없음) `apps/portal/src/app/p/[area]/[id]/markdown-body.tsx` — 로컬 `MarkdownBody`, `prose prose-popory`가 Task 1의 새 prose 설정을 받는다.

- [ ] **Step 1: 본문 셸을 에디토리얼 레이아웃으로 교체**

`apps/portal/src/app/p/[area]/[id]/page.tsx` 전체를 아래로 교체한다. 실제 fetch는 `/api/published_items/{id}`(area 쿼리 없음)이고 응답은 `{title, summary, body}`(published_at 없음), `MarkdownBody`는 **children**으로 본문을 받는다 — 이 형태를 그대로 유지하고 마크업만 에디토리얼로 바꾼다. `params`의 `area`로 카테고리 라벨을 만든다.

```tsx
// 단일 publish 본문 (Markdown 렌더). 에디토리얼 셸.
import { Kicker } from "@popory/ui";
import { API_BASE } from "@/lib/env";
import { MarkdownBody } from "./markdown-body";

export default async function ItemPage({ params }: { params: Promise<{ area: string; id: string }> }) {
  const { area, id } = await params;
  const res = await fetch(`${API_BASE}/api/published_items/${id}`, { cache: "no-store" });
  if (!res.ok) {
    return <main className="mx-auto max-w-2xl px-4 py-12 text-sm text-popory-muted">없는 글입니다.</main>;
  }
  const item = (await res.json()) as { title: string; summary: string | null; body: string };
  const categoryLabel = area.replace(/^brief-/, "");
  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <a href={`/p/${area}`} className="text-sm text-popory-muted hover:text-popory-fg">← 목록으로</a>
      <div className="mt-4">
        <Kicker>{categoryLabel}</Kicker>
      </div>
      <h1 className="mt-3 font-serif text-3xl font-semibold leading-tight tracking-tight text-popory-fg">
        {item.title}
      </h1>
      {item.summary && <p className="mt-3 text-base leading-relaxed text-popory-fg2">{item.summary}</p>}
      <div className="mt-3 flex items-center gap-2 border-b border-popory-border pb-5 text-xs text-popory-muted">
        <span>popory 브리핑</span>
      </div>
      <article className="prose prose-popory mt-6 max-w-none">
        <MarkdownBody>{item.body}</MarkdownBody>
      </article>
    </main>
  );
}
```

- [ ] **Step 2: 타입체크**

Run: `pnpm -C apps/portal typecheck`
Expected: 에러 0.

- [ ] **Step 3: 육안 확인**

`pnpm -C apps/portal dev` → 실제 발행물 경로(`/p/brief-<slug>/<id>`) 접속. 키커 → 세리프 헤드라인 → 본문 순서, 본문 폭(약 42rem)·행간이 읽기 좋은지 라이트/다크 모두 확인.

- [ ] **Step 4: 커밋**

```bash
git add "apps/portal/src/app/p/[area]/[id]/page.tsx"
git commit -m "feat(portal): 브리핑 본문 에디토리얼 레이아웃 (키커·세리프 헤드라인·prose 재설계)"
```

---

## Task 5: 브리핑 허브 (/p/brief)

**Files:**
- Modify: `apps/portal/src/app/p/brief/page.tsx`

- [ ] **Step 1: 허브 return 마크업 교체 (fetch·타입·`cards` 로직 유지)**

`apps/portal/src/app/p/brief/page.tsx`에서 상단 import/interface/`fetchCategories`/`fetchLatest`/`formatDate`/`cards` 빌드 로직은 그대로 둔다. 다음 두 가지만 바꾼다.
1. import에 Kicker 추가: 파일 상단 `import Link from "next/link";` 아래에 `import { Kicker } from "@popory/ui";` 추가.
2. `return (...)` 블록 전체를 아래로 교체.

```tsx
  return (
    <main className="mx-auto max-w-5xl px-4 py-10">
      <Kicker>Daily Briefings</Kicker>
      <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">
        매일 아침, 여러 갈래의 세상
      </h1>
      <p className="mt-2 text-sm text-popory-muted">
        AI가 큐레이션한 일일 브리핑. 매일 09:00 KST 발행.
      </p>
      {cards.length === 0 ? (
        <p className="mt-10 text-sm text-popory-muted">카테고리 목록을 불러오지 못했습니다.</p>
      ) : (
        <ul className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {cards.map((c) => (
            <li key={c.slug}>
              <Link
                href={`/p/brief-${c.slug}`}
                className="group block h-full rounded-xl border border-popory-border bg-popory-card p-5 transition hover:border-popory-accent"
              >
                <div className="flex items-center justify-between">
                  <span className="text-base font-bold text-popory-fg">{c.name}</span>
                </div>
                {c.description && <p className="mt-1 text-xs text-popory-muted">{c.description}</p>}
                {c.latest ? (
                  <div className="mt-3 border-t border-dashed border-popory-border pt-3">
                    <p className="line-clamp-2 text-sm font-medium leading-relaxed text-popory-fg2">
                      {c.latest.title}
                    </p>
                    <p className="mt-1.5 text-[11px] text-popory-muted">최신 · {formatDate(c.latest.published_at)}</p>
                  </div>
                ) : (
                  <p className="mt-3 border-t border-dashed border-popory-border pt-3 text-xs text-popory-muted">
                    아직 발행된 브리핑이 없습니다.
                  </p>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
```

(기존 `formatDate(unixSeconds)`는 그대로 사용 — `published_at`이 유닉스 초이므로 시그니처 변경 불필요.)

- [ ] **Step 2: 타입체크**

Run: `pnpm -C apps/portal typecheck`
Expected: 에러 0.

- [ ] **Step 3: 육안 확인**

`pnpm -C apps/portal dev` → `http://localhost:3000/p/brief`. 키커·세리프 제목·카테고리 카드(호버 시 accent 보더)·빈 상태를 라이트/다크로 확인.

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

- [ ] **Step 1: 영역 목록을 날짜 중심 리스트로 교체**

`apps/portal/src/app/p/[area]/page.tsx` 전체를 아래로 교체한다. fetch 로직·타입은 유지하고 날짜 헬퍼와 마크업만 바꾼다.

```tsx
// 영역별 발행물 목록 페이지.
import Link from "next/link";
import { Kicker } from "@popory/ui";
import { API_BASE } from "@/lib/env";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface Item {
  id: string;
  title: string;
  summary: string | null;
  published_at: number;
}

async function fetchItems(area: string): Promise<Item[]> {
  try {
    const res = await fetch(`${API_BASE}/api/published_items?area=${area}&limit=50`, {
      cache: "no-store",
    });
    if (!res.ok) return [];
    const { items } = (await res.json()) as { items: Item[] };
    return items;
  } catch {
    return [];
  }
}

function dayOf(unixSeconds: number): string {
  return String(new Date(unixSeconds * 1000).getDate());
}
function monthOf(unixSeconds: number): string {
  return `${new Date(unixSeconds * 1000).getMonth() + 1}월`;
}

export default async function AreaListPage({
  params,
}: {
  params: Promise<{ area: string }>;
}) {
  const { area } = await params;
  const items = await fetchItems(area);
  const categoryLabel = area.replace(/^brief-/, "");

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <Kicker>{categoryLabel}</Kicker>
      <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">
        {categoryLabel} 브리핑
      </h1>
      <div className="mt-6">
        {items.length === 0 ? (
          <p className="text-sm text-popory-muted">아직 발행된 글이 없습니다.</p>
        ) : (
          items.map((it) => (
            <Link
              key={it.id}
              href={`/p/${area}/${it.id}`}
              className="flex gap-4 border-b border-popory-border py-4 transition hover:bg-popory-accent-soft/40"
            >
              <div className="w-14 shrink-0 text-center">
                <div className="font-serif text-2xl font-semibold leading-none text-popory-fg">{dayOf(it.published_at)}</div>
                <div className="mt-1 text-[10px] uppercase tracking-widest text-popory-muted">{monthOf(it.published_at)}</div>
              </div>
              <div>
                <h2 className="text-[15px] font-bold leading-snug text-popory-fg">{it.title}</h2>
                {it.summary && <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-popory-muted">{it.summary}</p>}
              </div>
            </Link>
          ))
        )}
      </div>
    </main>
  );
}
```

- [ ] **Step 2: 아카이브 홈(/p) 교체**

`apps/portal/src/app/p/page.tsx` 전체를 아래로 교체한다. 실제 구조(하드코딩 `AREAS` + `/api/published_items?limit=100` 집계 `counts()`)를 그대로 유지하고 헤더·카드 스타일만 허브와 통일한다.

```tsx
// 공개 published_items 의 영역별 카드.
import Link from "next/link";
import { Kicker } from "@popory/ui";
import { API_BASE } from "@/lib/env";

const AREAS = [
  { key: "brief", label: "뉴스 브리핑" },
];

async function counts() {
  const res = await fetch(`${API_BASE}/api/published_items?limit=100`, { cache: "no-store" });
  const { items } = (await res.json()) as { items: { area: string }[] };
  const map = new Map<string, number>();
  for (const i of items) map.set(i.area, (map.get(i.area) ?? 0) + 1);
  return map;
}

export default async function PublicHome() {
  const c = await counts();
  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <Kicker>Archive</Kicker>
      <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">공개 아카이브</h1>
      <ul className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {AREAS.map((a) => (
          <li key={a.key}>
            <Link
              href={`/p/${a.key}`}
              className="group block rounded-xl border border-popory-border bg-popory-card p-5 transition hover:border-popory-accent"
            >
              <div className="text-base font-bold text-popory-fg">{a.label}</div>
              <div className="mt-1 text-sm text-popory-muted">{c.get(a.key) ?? 0}개 발행물</div>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
```

- [ ] **Step 3: 타입체크**

Run: `pnpm -C apps/portal typecheck`
Expected: 에러 0.

- [ ] **Step 4: 육안 확인**

`pnpm -C apps/portal dev` → `/p` 와 `/p/brief-<slug>`. 날짜 컬럼·세리프 숫자·빈 상태를 라이트/다크로 확인.

- [ ] **Step 5: 커밋**

```bash
git add "apps/portal/src/app/p/[area]/page.tsx" apps/portal/src/app/p/page.tsx
git commit -m "feat(portal): 영역 목록 날짜 중심 리스트 + 아카이브 홈 정리"
```

---

## Task 7: 대시보드 (/dashboard)

**Files:**
- Modify: `apps/portal/src/app/(authed)/dashboard/page.tsx`

- [ ] **Step 1: 대시보드 전체 교체 (세션·AREAS·Header 시그니처 유지)**

`apps/portal/src/app/(authed)/dashboard/page.tsx` 전체를 아래로 교체한다. `getCurrentUser`·`AREAS`·`Header({email, role, apiBase})` 호출은 유지하고, 인사말 헤더 + 서비스 카드 그리드를 에디토리얼로 바꾼다. Header는 max-w main 밖으로 빼서 풀폭 바로 둔다. `Card`는 더 이상 쓰지 않으므로 import에서 제거(고아 제거).

```tsx
// 로그인 사용자의 대시보드. 영역 카드와 admin 진입 링크.
import { redirect } from "next/navigation";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";

type AreaCard = { key: string; label: string; href: (apiBase: string) => string; external?: boolean };

const AREAS: AreaCard[] = [
  { key: "brief", label: "뉴스 브리핑", href: () => "/p/brief" },
  { key: "content", label: "컨텐츠 관리", href: (b) => `${b}/go/content` },
  { key: "finance", label: "금융 자산", href: (b) => `${b}/go/finance` },
  { key: "baduk", label: "바둑", href: () => "https://www.inkbaduk.com", external: true },
];

export default async function Dashboard() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const todayLabel = new Intl.DateTimeFormat("ko-KR", { dateStyle: "full" }).format(new Date());

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-5xl px-4 py-10">
        <Kicker>{todayLabel}</Kicker>
        <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">오늘의 popory</h1>
        <p className="mt-2 text-sm text-popory-muted">가족이 함께 보는 브리핑과 서비스를 한곳에서.</p>
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {AREAS.map((a) => (
            <a
              key={a.key}
              href={a.href(API_BASE)}
              target={a.external ? "_blank" : undefined}
              rel={a.external ? "noopener noreferrer" : undefined}
              className="group block"
            >
              <div className="h-full rounded-xl border border-popory-border bg-popory-card p-5 transition group-hover:border-popory-accent">
                <h2 className="text-base font-bold text-popory-fg">{a.label}</h2>
                <p className="mt-1 text-sm text-popory-muted">{a.external ? "외부 사이트" : "바로 진입"}</p>
              </div>
            </a>
          ))}
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 2: 타입체크**

Run: `pnpm -C apps/portal typecheck`
Expected: 에러 0.

- [ ] **Step 3: 육안 확인**

`pnpm -C apps/portal dev` → `/dashboard`. 풀폭 헤더·인사말 키커·세리프 제목·서비스 카드 라이트/다크 확인.

- [ ] **Step 4: 커밋**

```bash
git add "apps/portal/src/app/(authed)/dashboard/page.tsx"
git commit -m "feat(portal): 대시보드 에디토리얼 리디자인 (인사말·서비스 카드)"
```

---

## Task 8: 랜딩 (/)

**Files:**
- Modify: `apps/portal/src/app/page.tsx`

- [ ] **Step 1: 랜딩 전체 교체 (세션 리다이렉트·구글 로그인 링크 유지)**

`apps/portal/src/app/page.tsx` 전체를 아래로 교체한다. `getCurrentUser`/리다이렉트, 구글 로그인 링크(`${API_BASE}/auth/google/start`)는 그대로 유지하고 히어로만 에디토리얼로.

```tsx
// 비로그인 랜딩 + 로그인된 경우 dashboard 로 redirect.
import { redirect } from "next/navigation";
import Link from "next/link";
import { Kicker } from "@popory/ui";
import { API_BASE } from "@/lib/env";
import { getCurrentUser } from "@/lib/session";

export default async function Page() {
  const user = await getCurrentUser();
  if (user) redirect("/dashboard");
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-4 text-center">
      <Kicker>popory family</Kicker>
      <h1 className="mt-4 font-serif text-4xl font-semibold tracking-tight text-popory-fg">
        매일 아침, 우리 가족의 브리핑
      </h1>
      <p className="mt-3 text-sm leading-relaxed text-popory-muted">
        AI가 큐레이션한 일일 브리핑과 가족 서비스를 한곳에서. 가족 전용 포털입니다.
      </p>
      <Link
        href={`${API_BASE}/auth/google/start`}
        className="mt-8 inline-block rounded-md bg-popory-accent px-5 py-2.5 text-sm font-medium text-white transition hover:opacity-90"
      >
        Google로 시작
      </Link>
    </main>
  );
}
```

- [ ] **Step 2: 타입체크**

Run: `pnpm -C apps/portal typecheck`
Expected: 에러 0.

- [ ] **Step 3: 육안 확인**

`pnpm -C apps/portal dev` → `http://localhost:3000/` (로그아웃 상태). 히어로·로그인 버튼·라이트/다크 확인.

- [ ] **Step 4: 커밋**

```bash
git add apps/portal/src/app/page.tsx
git commit -m "feat(portal): 랜딩 히어로 에디토리얼 리디자인"
```

---

## Task 9: 어드민 Ledger 테마 — 레이아웃

**Files:**
- Modify: `apps/portal/src/app/admin/layout.tsx`

- [ ] **Step 1: `.ledger` 스코프와 세리프 헤딩 적용**

`apps/portal/src/app/admin/layout.tsx` 전체를 아래로 교체한다. 가드 로직은 유지하고, 최상위 래퍼에 `ledger` 클래스 + 배경/세리프 헤딩을 적용한다.

```tsx
// 어드민 영역 가드. role!=admin 이면 / 로 redirect. Ledger 테마 적용.
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { getCurrentUser } from "@/lib/session";

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  if (user.role !== "admin") redirect("/dashboard");
  return (
    <div className="ledger min-h-screen bg-popory-bg text-popory-fg [&_h1]:font-serif [&_h2]:font-serif [&_h3]:font-serif">
      <div className="mx-auto max-w-4xl px-6 py-10">{children}</div>
    </div>
  );
}
```

`.ledger`가 Task 1에서 정의한 종이 톤 토큰을 자식 전체에 재매핑하므로, 기존 `popory-*` 유틸리티가 자동으로 Ledger 색을 받는다.

- [ ] **Step 2: 타입체크 + 빌드**

Run: `pnpm -C apps/portal typecheck && pnpm -C apps/portal build`
Expected: 둘 다 성공.

- [ ] **Step 3: 육안 확인**

`pnpm -C apps/portal dev` → `/admin`. 배경이 종이 톤, 헤딩이 세리프, 강조가 잉크 레드로 바뀌었는지 라이트/다크 확인.

- [ ] **Step 4: 커밋**

```bash
git add apps/portal/src/app/admin/layout.tsx
git commit -m "feat(portal): 어드민 Ledger 테마 레이아웃 (.ledger 토큰 재매핑·세리프 헤딩)"
```

---

## Task 10: 어드민 폼·테이블 톤 정리

**Files:**
- Modify: `apps/portal/src/app/admin/page.tsx`
- Modify: `apps/portal/src/app/admin/whitelist/page.tsx`
- Modify: `apps/portal/src/app/admin/users/page.tsx`
- Modify: `apps/portal/src/app/admin/brief-categories/page.tsx`
- Modify: `apps/portal/src/app/admin/brief-categories/new/NewForm.tsx`
- Modify: `apps/portal/src/app/admin/brief-categories/[slug]/EditForm.tsx`

대부분의 색은 Task 9의 `.ledger` 토큰 재매핑으로 이미 적용된다. 이 태스크는 **위계·여백·세리프 헤딩·강조 포인트**를 Ledger 톤에 맞게 마감하는 작업이다. 기능(Server Action, form action, fetch, 핸들러)·구조는 변경하지 않는다.

- [ ] **Step 1: 각 파일의 현재 className 파악**

Run: `grep -rn "className" "apps/portal/src/app/admin/page.tsx" "apps/portal/src/app/admin/whitelist/page.tsx" "apps/portal/src/app/admin/users/page.tsx" "apps/portal/src/app/admin/brief-categories/page.tsx" "apps/portal/src/app/admin/brief-categories/new/NewForm.tsx" "apps/portal/src/app/admin/brief-categories/[slug]/EditForm.tsx"`
Expected: 현재 input/table/button/링크 클래스 목록. 정리 대상 식별.

- [ ] **Step 2: admin/page.tsx 다듬기**

`admin/page.tsx`는 `Card`(@popory/ui)와 `<nav className="mt-4 flex gap-4 text-popory-accent">`를 쓰며, 색은 layout의 `.ledger`로 자동 재매핑된다. 제목도 layout이 세리프를 입히므로 폰트 클래스 추가 불필요. 선택적으로 nav에 `hover:underline`만 더하는 정도로 마감한다(구조 변경 없음).

- [ ] **Step 3: NewForm.tsx / EditForm.tsx 마감**

두 폼은 이미 `const INPUT = "w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm"` 상수와 `Field`(라벨은 `text-popory-muted`) 컴포넌트, popory-accent 버튼을 쓴다. 이 토큰들은 `.ledger` 스코프에서 자동으로 종이 톤으로 재매핑되므로 **구조 변경은 불필요**하다. 텍스트 대비를 명시하고 싶으면 `INPUT` 상수 끝에 ` text-popory-fg`만 덧붙인다(두 파일 동일하게, 중복 정의 금지). 에러 배너(`rounded-md border border-red-300 bg-red-50 ...`)는 그대로 둔다. 그 외 form action·핸들러·필드 구성은 절대 변경하지 않는다.

- [ ] **Step 4: whitelist / users / brief-categories 테이블·목록 다듬기**

각 페이지의 테이블/목록을 다음 규칙으로 통일한다.
- 테이블 헤더 셀: `className="text-left text-xs uppercase tracking-wide text-popory-muted"`
- 행: `className="border-b border-popory-border"`
- 데이터 셀: `className="py-2 text-sm text-popory-fg"`
- 행 안의 액션 버튼: Step 3의 primary/secondary 버튼 클래스 재사용.
- 입력(이메일 추가 등): Step 3의 `INPUT` 동일 클래스.

기능/Server Action/form action은 변경 금지.

- [ ] **Step 5: 타입체크 + 빌드**

Run: `pnpm -C apps/portal typecheck && pnpm -C apps/portal build`
Expected: 둘 다 성공.

- [ ] **Step 6: 육안 확인**

`pnpm -C apps/portal dev` → `/admin`, `/admin/whitelist`, `/admin/users`, `/admin/brief-categories`, `/admin/brief-categories/new`. 폼·테이블이 Ledger 톤으로 일관되고, 폼 제출(추가/삭제/저장)이 그대로 동작하는지 라이트/다크 확인.

- [ ] **Step 7: 커밋**

```bash
git add apps/portal/src/app/admin
git commit -m "feat(portal): 어드민 폼·테이블 Ledger 톤 통일"
```

---

## Task 11: 마감 — 라이트/다크·반응형·빌드

- [ ] **Step 1: 전체 빌드**

Run: `pnpm -C apps/portal build`
Expected: 성공. 경고가 있으면 읽고 의미 있는 것만 처리.

- [ ] **Step 2: 라이트/다크 전수 확인**

`pnpm -C apps/portal dev` 상태에서 브라우저 devtools의 Rendering → `Emulate CSS prefers-color-scheme`를 light/dark로 토글하며 확인한다.
- 공개: `/`, `/dashboard`, `/p`, `/p/brief`, `/p/brief-<slug>`, `/p/brief-<slug>/<id>`
- 어드민: `/admin`, `/admin/whitelist`, `/admin/users`, `/admin/brief-categories`, `/admin/brief-categories/new`, `/admin/brief-categories/<slug>`
대비가 깨지거나 읽기 어려운 곳은 해당 페이지의 토큰 클래스로 수정.

- [ ] **Step 3: 반응형 확인**

각 화면을 모바일 폭(375px)·데스크톱에서 확인. 그리드(`sm:`/`lg:`)·본문 폭·헤더가 깨지지 않는지 본다. 깨진 곳만 수정.

- [ ] **Step 4: 최종 커밋(수정이 있었다면)**

```bash
git add -A
git commit -m "fix(portal): 리브랜딩 라이트/다크·반응형 마감 정리"
```

- [ ] **Step 5: 완료 보고**

빌드 성공·확인 경로·라이트/다크 결과를 요약 보고. 미해결 항목이 있으면 명시.

---

## Self-Review (작성자 점검 결과)

**스펙 커버리지.** 두 디자인 언어(공개 The Brief / 어드민 Ledger) → Task 1·3~8(공개)·9~10(어드민). 토큰 확장 → Task 1. 폰트 → Task 1. 공유 컴포넌트 → Task 2·3. 공개 6개 화면 → Task 4(본문)·5(허브)·6(목록+아카이브)·7(대시보드)·8(랜딩). 어드민 5개 화면 → Task 9·10. 라이트/다크 → 각 태스크 + Task 11. 빈 상태 → Task 5·6. 비범위(라우팅·인증·API·데이터 불변) → 각 태스크가 "fetch/로직 유지, 마크업만 교체" 명시.

**실 코드 정합성 점검(수정 반영됨).**
- `Header` props `{email, role, apiBase}` + `${apiBase}/api/logout` 유지 → 호출부(dashboard) 불변.
- `index.ts`의 `import "./tokens.css";` 유지. `MarkdownBody`는 `@popory/ui`에 없으므로 export 안 함 — 본문은 로컬 `./markdown-body` 사용.
- `published_at`은 유닉스 초 → 모든 날짜 헬퍼가 `* 1000` 적용.
- 브리핑 허브는 실제 `cards`/`c.latest` 구조와 기존 `formatDate(unixSeconds)`를 그대로 사용.
- 명령은 pnpm 워크스페이스 기준(`pnpm -C apps/portal ...`).

**플레이스홀더 스캔.** "적절히 처리" 식 모호 지시 없음. Task 10만 기존 폼/테이블이 길어 전체 코드 대신 클래스 통일 규칙 + Step 1 grep 확인으로 구성 — 기능 불변이 핵심이라 의도적 선택.

**타입/이름 일관성.** `Kicker`/`BriefCard`/`WhyBlock` 시그니처는 Task 2 정의와 사용처 일치. `.ledger` 클래스명은 Task 1 정의 ↔ Task 9 사용 일치. `formatDate`/`dayOf`/`monthOf`는 각 파일 내 정의와 사용 일치.

**참고.** `BriefCard`/`WhyBlock`은 향후 구조화 본문에서 쓸 프리미티브로 export까지만 하고, 현재 마크다운 본문 렌더에는 강제 적용하지 않는다.
