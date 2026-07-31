# popory admin UI/UX 전면 개편 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** popory admin(8개 라우트)에 탭 네비 셸·에러/로딩 인프라·공통 컴포넌트를 도입하고, 파괴적 액션 confirm·모바일·접근성·포맷을 통일하며 `/content/status`를 `/admin/status`로 이전한다.

**Architecture:** 기존 서버 컴포넌트 구조는 유지한다. 1) 상태색 토큰과 admin 로컬 공통 모듈(`_components`, `_lib`)을 먼저 만들고, 2) 레이아웃을 탭 셸로 개편한 뒤, 3) 페이지를 하나씩 새 기반으로 전환한다. 스펙: `docs/superpowers/specs/2026-07-17-popory-admin-ui-redesign-design.md`.

**Tech Stack:** Next.js 15 (App Router, React 19), Tailwind 3, pnpm 9 + turbo. 레포: `~/projects/popory`.

## Global Constraints

- 작업은 popory 레포의 git worktree에서 진행한다. 브랜치명 `feature/admin-ui-redesign`.
- **신규 파일은 첫 줄(디렉티브 직후)에 한국어 역할 주석 필수** (AGENTS.md 규칙 6). 아래 태스크의 코드 블록에 이미 포함되어 있으니 그대로 쓴다.
- 한국어 UI 문구·주석은 콜론(`:`)으로 문장을 끝내지 않는다 (규칙 5).
- **portal에는 단위 테스트 러너가 없다** (`@popory/portal`의 스크립트는 typecheck/e2e뿐). 태스크 검증은 `pnpm --filter @popory/portal typecheck`, 최종 태스크에서 build + 수동 렌더 확인을 한다. e2e(golden.spec.ts)는 건드리지 않는다.
- 커밋 메시지는 기존 스타일(`feat(admin): 한국어 요약`)을 따르고 마지막 줄에 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`를 붙인다.
- 기존 파일 수정 시 외과적 변경만 한다 (규칙 3). 아래 "전체 교체" 표기가 있는 파일만 통째로 바꾼다.
- 명령은 모두 worktree 루트에서 실행한다.

---

### Task 1: 상태색 디자인 토큰

**Files:**
- Modify: `packages/ui/src/tokens.css` (전체 교체)
- Modify: `apps/portal/tailwind.config.ts:9-19` (colors.popory에 6키 추가)

**Interfaces:**
- Produces: CSS 변수 `--popory-success`, `--popory-success-soft`, `--popory-warn`, `--popory-warn-soft`, `--popory-danger`, `--popory-danger-soft` (4개 스코프 전부). Tailwind 클래스 `text-popory-success`, `bg-popory-danger-soft` 등. 이후 모든 태스크가 사용.

- [ ] **Step 1: tokens.css 전체 교체**

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
  /* 상태색. accent 와 구분되는 성공/주의/실패 시그널 */
  --popory-success: #1e7a3c;
  --popory-success-soft: #e3f2e8;
  --popory-warn: #8a6116;
  --popory-warn-soft: #f7efdb;
  --popory-danger: #c92a2a;
  --popory-danger-soft: #fbe4e4;
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
    --popory-success: #66bb7f;
    --popory-success-soft: #14291c;
    --popory-warn: #d9a94f;
    --popory-warn-soft: #2b2413;
    --popory-danger: #ef7070;
    --popory-danger-soft: #331a1a;
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
  --popory-success: #3d6b46;
  --popory-success-soft: #e6ecdb;
  --popory-warn: #8f6a12;
  --popory-warn-soft: #f2e8cd;
  --popory-danger: #b3261e;
  --popory-danger-soft: #f4ded6;
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
    --popory-success: #93b98a;
    --popory-success-soft: #202617;
    --popory-warn: #d3b269;
    --popory-warn-soft: #2c2514;
    --popory-danger: #e08273;
    --popory-danger-soft: #34201a;
  }
}
```

- [ ] **Step 2: tailwind.config.ts의 colors.popory에 6키 추가**

`accent-soft` 줄 다음, `card` 줄 앞에 삽입한다.

```ts
          success: "var(--popory-success)",
          "success-soft": "var(--popory-success-soft)",
          warn: "var(--popory-warn)",
          "warn-soft": "var(--popory-warn-soft)",
          danger: "var(--popory-danger)",
          "danger-soft": "var(--popory-danger-soft)",
```

- [ ] **Step 3: typecheck**

Run: `pnpm --filter @popory/portal typecheck`
Expected: 에러 0.

- [ ] **Step 4: Commit**

```bash
git add packages/ui/src/tokens.css apps/portal/tailwind.config.ts
git commit -m "feat(ui): 상태색 디자인 토큰 추가"
```

---

### Task 2: 날짜 포맷·한글 라벨 유틸 (`_lib`)

**Files:**
- Create: `apps/portal/src/app/admin/_lib/format.ts`
- Create: `apps/portal/src/app/admin/_lib/labels.ts`

**Interfaces:**
- Produces: `formatKst(ts: number | null | undefined): string`, `formatKstIso(iso: string): string`, `roleLabel(v: string): string`, `statusLabel(v: string | null): string`, `deliveryLabel(v: string): string`, `serviceLabel(v: string): string`, `platformLabel(v: string): string`, `statusIntent(v: string | null): "success" | "warn" | "danger" | "neutral"`.

- [ ] **Step 1: format.ts 작성**

```ts
// KST 날짜·시각 표기 단일 구현. admin 화면 전체가 이 포맷터만 쓴다.
export function formatKst(ts: number | null | undefined): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
}

export function formatKstIso(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ko-KR", {
      timeZone: "Asia/Seoul",
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
```

- [ ] **Step 2: labels.ts 작성**

```ts
// raw enum 값의 한글 라벨 매핑. 매핑에 없는 값은 raw 그대로 노출해 새 값이 화면을 깨지 않게 한다.
const ROLE: Record<string, string> = { member: "일반", admin: "관리자" };
const STATUS: Record<string, string> = {
  failed: "실패",
  queued: "대기",
  running: "진행 중",
  done: "완료",
  success: "완료",
  uploaded: "업로드됨",
};
const DELIVERY: Record<string, string> = { standalone: "단독", bundled: "묶음" };
const SERVICE: Record<string, string> = { content: "콘텐츠", brief: "브리핑" };
const PLATFORM: Record<string, string> = {
  "naver-blog": "블로그",
  youtube: "유튜브",
  shorts: "쇼츠",
  "instagram-image": "인스타",
  "youtube-post": "게시물",
};

export const roleLabel = (v: string): string => ROLE[v] ?? v;
export const statusLabel = (v: string | null): string => (v ? STATUS[v] ?? v : "");
export const deliveryLabel = (v: string): string => DELIVERY[v] ?? v;
export const serviceLabel = (v: string): string => SERVICE[v] ?? v;
export const platformLabel = (v: string): string => PLATFORM[v] ?? v;

export function statusIntent(v: string | null): "success" | "warn" | "danger" | "neutral" {
  if (!v) return "neutral";
  if (v === "failed" || v.endsWith("_fail")) return "danger";
  if (v === "queued" || v === "running") return "warn";
  if (v === "done" || v === "success" || v === "uploaded") return "success";
  return "neutral";
}
```

- [ ] **Step 3: typecheck**

Run: `pnpm --filter @popory/portal typecheck`
Expected: 에러 0.

- [ ] **Step 4: Commit**

```bash
git add apps/portal/src/app/admin/_lib
git commit -m "feat(admin): 날짜 포맷·한글 라벨 공통 유틸"
```

---

### Task 3: Button·Badge·EmptyState·입력 클래스 (`_components` 1차)

**Files:**
- Create: `apps/portal/src/app/admin/_components/Button.tsx`
- Create: `apps/portal/src/app/admin/_components/Badge.tsx`
- Create: `apps/portal/src/app/admin/_components/EmptyState.tsx`
- Create: `apps/portal/src/app/admin/_components/field.ts`

**Interfaces:**
- Produces: `Button` (props: `variant?: "primary" | "secondary" | "danger"` + 표준 button 속성), `ButtonVariant` 타입, `Badge` (props: `intent?: "success" | "warn" | "danger" | "neutral"`, `children`), `BadgeIntent` 타입, `EmptyState` (children), 상수 `INPUT_CLASS`, `COMPACT_INPUT_CLASS`.

- [ ] **Step 1: Button.tsx 작성**

```tsx
// admin 공통 버튼. variant(primary/secondary/danger)와 비활성·포커스 스타일을 표준화한다.
import type { ButtonHTMLAttributes } from "react";

const VARIANT = {
  primary: "bg-popory-accent font-medium text-white",
  secondary: "border border-popory-border text-popory-fg",
  danger: "border border-popory-danger text-popory-danger",
} as const;

export type ButtonVariant = keyof typeof VARIANT;

export function Button({
  variant = "secondary",
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      className={`rounded-md px-4 py-2 text-sm disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-popory-accent ${VARIANT[variant]} ${className}`}
      {...rest}
    />
  );
}
```

- [ ] **Step 2: Badge.tsx 작성**

```tsx
// 상태 표시용 pill 배지. intent 별 상태색 토큰을 쓴다.
import type { ReactNode } from "react";

const INTENT = {
  success: "bg-popory-success-soft text-popory-success",
  warn: "bg-popory-warn-soft text-popory-warn",
  danger: "bg-popory-danger-soft text-popory-danger",
  neutral: "bg-popory-accent-soft text-popory-muted",
} as const;

export type BadgeIntent = keyof typeof INTENT;

export function Badge({ intent = "neutral", children }: { intent?: BadgeIntent; children: ReactNode }) {
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs ${INTENT[intent]}`}>
      {children}
    </span>
  );
}
```

- [ ] **Step 3: EmptyState.tsx 작성**

```tsx
// 빈 목록 안내 문구의 공통 표기.
import type { ReactNode } from "react";

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="mt-8 text-sm text-popory-muted">{children}</p>;
}
```

- [ ] **Step 4: field.ts 작성**

```ts
// admin 폼 입력의 공통 Tailwind 클래스 상수.
export const INPUT_CLASS =
  "w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg";
export const COMPACT_INPUT_CLASS =
  "rounded-md border border-popory-border bg-popory-card px-2 py-1";
```

- [ ] **Step 5: typecheck 후 commit**

Run: `pnpm --filter @popory/portal typecheck` → 에러 0.

```bash
git add apps/portal/src/app/admin/_components
git commit -m "feat(admin): Button·Badge·EmptyState 공통 컴포넌트"
```

---

### Task 4: Table·FilterBar (`_components` 2차)

**Files:**
- Create: `apps/portal/src/app/admin/_components/Table.tsx`
- Create: `apps/portal/src/app/admin/_components/FilterBar.tsx`

**Interfaces:**
- Consumes: `Button` (Task 3).
- Produces: `Table` (props: `head: ReactNode[]`, `children` — tbody 행들), `FilterBar` (children — FilterField들, GET 제출 "필터" 버튼 내장), `FilterField` (props: `label: string`, `children` — select/input 하나).

- [ ] **Step 1: Table.tsx 작성**

```tsx
// overflow 래퍼와 통일된 thead 스타일을 제공하는 admin 공통 테이블.
import type { ReactNode } from "react";

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <div className="mt-6 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-popory-border">
            {head.map((h, i) => (
              <th key={i} scope="col" className="py-2 pr-4 text-left text-xs uppercase tracking-wide text-popory-muted">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: FilterBar.tsx 작성**

```tsx
// GET 필터 폼 래퍼. label 연결과 제출 버튼을 표준화한다.
import type { ReactNode } from "react";
import { Button } from "./Button";

export function FilterBar({ children }: { children: ReactNode }) {
  return (
    <form className="mt-4 flex flex-wrap items-end gap-2 text-sm">
      {children}
      <Button type="submit" variant="primary" className="px-3 py-1">필터</Button>
    </form>
  );
}

export function FilterField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-popory-muted">{label}</span>
      {children}
    </label>
  );
}
```

- [ ] **Step 3: typecheck 후 commit**

Run: `pnpm --filter @popory/portal typecheck` → 에러 0.

```bash
git add apps/portal/src/app/admin/_components/Table.tsx apps/portal/src/app/admin/_components/FilterBar.tsx
git commit -m "feat(admin): Table·FilterBar 공통 컴포넌트"
```

---

### Task 5: ConfirmSubmitButton

**Files:**
- Create: `apps/portal/src/app/admin/_components/ConfirmSubmitButton.tsx`

**Interfaces:**
- Consumes: `Button`, `ButtonVariant` (Task 3).
- Produces: `ConfirmSubmitButton` (props: `message: string`, `variant?: ButtonVariant`, `pendingLabel?: string`, `children`). server action `<form>` 안에서만 쓴다 (`useFormStatus`가 폼 컨텍스트 필요).

- [ ] **Step 1: ConfirmSubmitButton.tsx 작성**

```tsx
"use client";
// 확인 다이얼로그와 pending 비활성화를 묶은 제출 버튼. server action form 안에서 쓴다.
import type { ReactNode } from "react";
import { useFormStatus } from "react-dom";
import { Button, type ButtonVariant } from "./Button";

interface Props {
  message: string;
  variant?: ButtonVariant;
  pendingLabel?: string;
  children: ReactNode;
}

export function ConfirmSubmitButton({ message, variant = "secondary", pendingLabel = "처리 중…", children }: Props) {
  const { pending } = useFormStatus();
  return (
    <Button
      type="submit"
      variant={variant}
      disabled={pending}
      onClick={(e) => {
        if (!confirm(message)) e.preventDefault();
      }}
    >
      {pending ? pendingLabel : children}
    </Button>
  );
}
```

- [ ] **Step 2: typecheck 후 commit**

Run: `pnpm --filter @popory/portal typecheck` → 에러 0.

```bash
git add apps/portal/src/app/admin/_components/ConfirmSubmitButton.tsx
git commit -m "feat(admin): 확인·pending 제출 버튼 추가"
```

---

### Task 6: 탭 네비 셸 + error/loading 바운더리

**Files:**
- Create: `apps/portal/src/app/admin/_components/AdminTabs.tsx`
- Modify: `apps/portal/src/app/admin/layout.tsx` (전체 교체)
- Create: `apps/portal/src/app/admin/error.tsx`
- Create: `apps/portal/src/app/admin/loading.tsx`

**Interfaces:**
- Consumes: 없음 (독립).
- Produces: admin 전 페이지가 상속하는 셸(상단 바 + 탭)과 에러/로딩 바운더리. 탭에 `/admin/status`가 미리 포함된다 (Task 13에서 페이지 생성 — 그 전까지 탭 클릭 시 404, 최종 검증 전 정상화됨).

- [ ] **Step 1: AdminTabs.tsx 작성**

```tsx
"use client";
// admin 상단 탭 바. usePathname 으로 활성 탭에 accent 밑줄을 그린다.
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/admin", label: "오버뷰" },
  { href: "/admin/users", label: "사용자" },
  { href: "/admin/activity", label: "활동" },
  { href: "/admin/errors", label: "오류" },
  { href: "/admin/status", label: "상태" },
  { href: "/admin/whitelist", label: "화이트리스트" },
  { href: "/admin/brief-categories", label: "브리핑 카테고리" },
];

export function AdminTabs() {
  const pathname = usePathname();
  return (
    <nav aria-label="관리자 메뉴" className="overflow-x-auto whitespace-nowrap border-b border-popory-border">
      <ul className="flex gap-1">
        {TABS.map((t) => {
          const active = t.href === "/admin" ? pathname === "/admin" : pathname.startsWith(t.href);
          return (
            <li key={t.href}>
              <Link
                href={t.href}
                aria-current={active ? "page" : undefined}
                className={`inline-block border-b-2 px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-popory-accent ${
                  active
                    ? "border-popory-accent font-semibold text-popory-fg"
                    : "border-transparent text-popory-muted hover:text-popory-fg"
                }`}
              >
                {t.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
```

- [ ] **Step 2: layout.tsx 전체 교체**

```tsx
// 어드민 영역 가드 + 공통 셸(상단 바·탭 네비). role!=admin 이면 redirect. Ledger 테마 적용.
import { redirect } from "next/navigation";
import Link from "next/link";
import type { ReactNode } from "react";
import { getCurrentUser } from "@/lib/session";
import { AdminTabs } from "./_components/AdminTabs";

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  if (user.role !== "admin") redirect("/dashboard");
  return (
    <div className="ledger min-h-screen bg-popory-bg text-popory-fg [&_h1]:font-serif [&_h2]:font-serif [&_h3]:font-serif">
      <div className="mx-auto max-w-4xl px-6 py-6">
        <div className="flex items-baseline gap-3">
          <Link href="/" className="text-sm text-popory-muted hover:text-popory-fg">◄ 포털</Link>
          <span className="font-serif text-lg font-semibold">Popory Admin</span>
        </div>
        <div className="mt-4">
          <AdminTabs />
        </div>
        <div className="pt-6">{children}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: error.tsx 작성**

```tsx
"use client";
// admin 공통 에러 바운더리. 서버 컴포넌트 fetch 실패 시 흰 화면 대신 안내와 재시도 버튼을 보여준다.
import { Button } from "./_components/Button";

export default function AdminError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="mt-10 rounded-md border border-popory-danger bg-popory-danger-soft px-4 py-6 text-sm">
      <p className="font-semibold text-popory-danger">화면을 불러오지 못했습니다.</p>
      <p className="mt-1 text-popory-fg2">잠시 후 다시 시도해 주세요. 반복되면 워커 API 상태를 확인해 주세요.</p>
      <Button onClick={reset} className="mt-4 bg-popory-card">다시 시도</Button>
    </div>
  );
}
```

- [ ] **Step 4: loading.tsx 작성**

```tsx
// admin 공통 로딩 표시.
export default function AdminLoading() {
  return <p className="mt-10 text-sm text-popory-muted">불러오는 중…</p>;
}
```

- [ ] **Step 5: typecheck 후 commit**

Run: `pnpm --filter @popory/portal typecheck` → 에러 0.

```bash
git add apps/portal/src/app/admin/_components/AdminTabs.tsx apps/portal/src/app/admin/layout.tsx apps/portal/src/app/admin/error.tsx apps/portal/src/app/admin/loading.tsx
git commit -m "feat(admin): 탭 네비 셸과 error·loading 바운더리"
```

---

### Task 7: 오버뷰 페이지 전환

**Files:**
- Modify: `apps/portal/src/app/admin/page.tsx` (전체 교체)

**Interfaces:**
- Consumes: `formatKst` (Task 2). 자체 nav는 탭 바(Task 6)가 대체하므로 제거.

- [ ] **Step 1: page.tsx 전체 교체**

```tsx
// /admin 진입 시 보이는 overview (사용자 수, 영역별 publish 건수, 최근 audit).
import { headers } from "next/headers";
import { Card } from "@popory/ui";
import { API_BASE } from "@/lib/env";
import { formatKst } from "./_lib/format";

async function fetchOverview() {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/overview`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) throw new Error(`overview ${res.status}`);
  return (await res.json()) as {
    users: number;
    published_by_area: Record<string, number>;
    recent_audits: { actor_sub: string | null; action: string; target: string | null; created_at: number }[];
  };
}

export default async function AdminHome() {
  const o = await fetchOverview();
  return (
    <main>
      <h1 className="text-xl font-semibold">오버뷰</h1>
      <section className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card>
          <div className="text-popory-muted text-sm">활성 사용자</div>
          <div className="text-2xl">{o.users}</div>
        </Card>
        <Card>
          <div className="text-popory-muted text-sm">영역별 게시물</div>
          <ul className="mt-2 text-sm">
            {Object.entries(o.published_by_area).map(([k, v]) => (
              <li key={k}>{k}: {v}</li>
            ))}
          </ul>
        </Card>
      </section>
      <section className="mt-6">
        <h2 className="text-lg font-medium">최근 변경</h2>
        {o.recent_audits.length === 0 ? (
          <p className="mt-2 text-sm text-popory-muted">최근 변경이 없습니다.</p>
        ) : (
          <ul className="mt-2 text-sm">
            {o.recent_audits.map((a, i) => (
              <li key={i} className="text-popory-muted">
                {formatKst(a.created_at)} — {a.action} {a.target ?? ""}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
```

- [ ] **Step 2: typecheck 후 commit**

Run: `pnpm --filter @popory/portal typecheck` → 에러 0.

```bash
git add apps/portal/src/app/admin/page.tsx
git commit -m "refactor(admin): 오버뷰를 공통 기반으로 전환"
```

---

### Task 8: 사용자 목록·상세 전환

**Files:**
- Modify: `apps/portal/src/app/admin/users/page.tsx` (전체 교체)
- Modify: `apps/portal/src/app/admin/users/[sub]/page.tsx` (전체 교체)

**Interfaces:**
- Consumes: `Table`, `Badge`, `EmptyState`, `ConfirmSubmitButton`, `COMPACT_INPUT_CLASS`, `formatKst`, `roleLabel`, `statusLabel`, `statusIntent`, `platformLabel`. server action `changeRole`/`toggleBlock`은 그대로 둔다.

- [ ] **Step 1: users/page.tsx 전체 교체**

```tsx
// 사용자 목록과 역할·차단 UI.
import Link from "next/link";
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { changeRole, toggleBlock } from "./actions";
import { Table } from "../_components/Table";
import { Badge } from "../_components/Badge";
import { EmptyState } from "../_components/EmptyState";
import { ConfirmSubmitButton } from "../_components/ConfirmSubmitButton";
import { COMPACT_INPUT_CLASS } from "../_components/field";
import { roleLabel } from "../_lib/labels";

interface UserRow { sub: string; email: string; display_name: string | null; role: "member" | "admin"; blocked_at: number | null; }

export default async function UsersPage() {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/users`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) throw new Error(`users ${res.status}`);
  const { items } = (await res.json()) as { items: UserRow[] };
  return (
    <main>
      <h1 className="text-xl font-semibold">사용자</h1>
      {items.length === 0 ? (
        <EmptyState>사용자가 없습니다.</EmptyState>
      ) : (
        <Table head={["이메일", "역할", "상태", ""]}>
          {items.map((u) => (
            <tr key={u.sub} className="border-b border-popory-border">
              <td className="py-2 pr-4">
                <Link href={`/admin/users/${u.sub}`} className="text-popory-accent">{u.email}</Link>
              </td>
              <td className="py-2 pr-4">
                <form action={changeRole} className="flex items-center gap-2">
                  <input type="hidden" name="sub" value={u.sub} />
                  <select name="role" defaultValue={u.role} className={COMPACT_INPUT_CLASS} aria-label="역할 선택">
                    <option value="member">{roleLabel("member")}</option>
                    <option value="admin">{roleLabel("admin")}</option>
                  </select>
                  <ConfirmSubmitButton message={`${u.email} 의 역할을 변경할까요?`} pendingLabel="변경 중…">
                    변경
                  </ConfirmSubmitButton>
                </form>
              </td>
              <td className="py-2 pr-4">
                {u.blocked_at ? <Badge intent="danger">차단</Badge> : <Badge intent="success">정상</Badge>}
              </td>
              <td className="py-2">
                <form action={toggleBlock}>
                  <input type="hidden" name="sub" value={u.sub} />
                  <input type="hidden" name="blocked" value={u.blocked_at ? "false" : "true"} />
                  <ConfirmSubmitButton
                    message={u.blocked_at ? `${u.email} 차단을 해제할까요?` : `${u.email} 을(를) 차단할까요?`}
                    pendingLabel="처리 중…"
                  >
                    {u.blocked_at ? "차단해제" : "차단"}
                  </ConfirmSubmitButton>
                </form>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </main>
  );
}
```

- [ ] **Step 2: users/[sub]/page.tsx 전체 교체**

```tsx
// 사용자 한 명의 프로필·연결 계정·콘텐츠 생성 내역.
import Link from "next/link";
import { notFound } from "next/navigation";
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { Table } from "../../_components/Table";
import { Badge } from "../../_components/Badge";
import { EmptyState } from "../../_components/EmptyState";
import { formatKst } from "../../_lib/format";
import { roleLabel, statusLabel, statusIntent, platformLabel } from "../../_lib/labels";

interface JobRow {
  id: string;
  topic: string | null;
  platform: string | null;
  status: string;
  error: string | null;
  youtube_status: string | null;
  youtube_error: string | null;
  created_at: number;
}

interface Detail {
  user: { sub: string; email: string; display_name: string | null; role: string; blocked_at: number | null; created_at: number; last_seen_at: number | null };
  connections: { youtube: boolean; instagram: boolean; facebook: boolean };
  jobs: JobRow[];
}

export default async function UserDetailPage({ params }: { params: Promise<{ sub: string }> }) {
  const { sub } = await params;
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/users/${encodeURIComponent(sub)}/activity`, {
    headers: { cookie },
    cache: "no-store",
  });
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`user detail ${res.status}`);
  const d = (await res.json()) as Detail;

  const connected = [
    d.connections.youtube ? "YouTube" : null,
    d.connections.instagram ? "Instagram" : null,
    d.connections.facebook ? "Facebook" : null,
  ].filter(Boolean);

  return (
    <main>
      <Link href="/admin/users" className="text-sm text-popory-accent">← 사용자 목록</Link>
      <h1 className="mt-2 text-xl font-semibold">{d.user.email}</h1>
      <dl className="mt-4 grid grid-cols-1 gap-2 text-sm text-popory-muted sm:grid-cols-2">
        <div>역할 <span className="text-popory-fg">{roleLabel(d.user.role)}</span></div>
        <div>상태 {d.user.blocked_at ? <Badge intent="danger">차단됨</Badge> : <Badge intent="success">정상</Badge>}</div>
        <div>가입 <span className="text-popory-fg">{formatKst(d.user.created_at)}</span></div>
        <div>마지막 접속 <span className="text-popory-fg">{formatKst(d.user.last_seen_at)}</span></div>
        <div className="sm:col-span-2">연결 계정 <span className="text-popory-fg">{connected.length ? connected.join(", ") : "없음"}</span></div>
      </dl>

      <h2 className="mt-8 text-lg font-semibold">콘텐츠 생성 내역 ({d.jobs.length})</h2>
      {d.jobs.length === 0 ? (
        <EmptyState>생성한 콘텐츠가 없습니다.</EmptyState>
      ) : (
        <Table head={["생성", "주제", "플랫폼", "상태", "업로드"]}>
          {d.jobs.map((j) => (
            <tr key={j.id} className="border-b border-popory-border">
              <td className="py-2 pr-4 text-xs text-popory-muted">{formatKst(j.created_at)}</td>
              <td className="py-2 pr-4">
                <Link href={`/content/${j.id}`} className="text-popory-accent">{j.topic ?? "(제목 없음)"}</Link>
              </td>
              <td className="py-2 pr-4 text-xs">{j.platform ? platformLabel(j.platform) : "—"}</td>
              <td className="py-2 pr-4 text-xs">
                <Badge intent={statusIntent(j.status)}>{statusLabel(j.status)}</Badge>
                {j.error && <span className="mt-1 block text-popory-muted">{j.error}</span>}
              </td>
              <td className="py-2 text-xs">
                {j.youtube_status ? <Badge intent={statusIntent(j.youtube_status)}>{statusLabel(j.youtube_status)}</Badge> : "—"}
                {j.youtube_error && <span className="mt-1 block text-popory-danger">{j.youtube_error}</span>}
              </td>
            </tr>
          ))}
        </Table>
      )}
    </main>
  );
}
```

- [ ] **Step 3: typecheck 후 commit**

Run: `pnpm --filter @popory/portal typecheck` → 에러 0.

```bash
git add apps/portal/src/app/admin/users
git commit -m "refactor(admin): 사용자 목록·상세를 공통 기반으로 전환"
```

---

### Task 9: 활동 이력 전환

**Files:**
- Modify: `apps/portal/src/app/admin/activity/page.tsx` (전체 교체)

**Interfaces:**
- Consumes: `Table`, `Badge`, `EmptyState`, `FilterBar`, `FilterField`, `COMPACT_INPUT_CLASS`, `formatKst`, `statusLabel`, `statusIntent`. 커서 페이지네이션 로직(PAGE=50, before/before_id)은 그대로 유지.

- [ ] **Step 1: activity/page.tsx 전체 교체**

```tsx
// 전체 사용자 활동 타임라인. 사용자·종류 필터와 커서 페이지네이션.
import Link from "next/link";
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { Table } from "../_components/Table";
import { Badge } from "../_components/Badge";
import { EmptyState } from "../_components/EmptyState";
import { FilterBar, FilterField } from "../_components/FilterBar";
import { COMPACT_INPUT_CLASS } from "../_components/field";
import { formatKst } from "../_lib/format";
import { statusLabel, statusIntent } from "../_lib/labels";

interface ActivityRow {
  ts: number;
  id: string;
  kind: "content_job" | "topic" | "account" | "publish";
  user_sub: string | null;
  user_email: string | null;
  title: string;
  status: string | null;
  href: string | null;
}

interface UserRow { sub: string; email: string; }

const KIND_LABEL: Record<string, string> = {
  content_job: "콘텐츠 생성",
  topic: "주제·카테고리",
  account: "계정·권한",
  publish: "브리핑 발행",
};

export default async function ActivityPage({
  searchParams,
}: {
  searchParams: Promise<{ sub?: string; kind?: string; before?: string; before_id?: string }>;
}) {
  const sp = await searchParams;
  const cookie = (await headers()).get("cookie") ?? "";
  const qs = new URLSearchParams();
  if (sp.sub) qs.set("sub", sp.sub);
  if (sp.kind) qs.set("kind", sp.kind);
  if (sp.before) qs.set("before", sp.before);
  if (sp.before_id) qs.set("before_id", sp.before_id);

  const [actRes, userRes] = await Promise.all([
    fetch(`${API_BASE}/api/admin/activity?${qs}`, { headers: { cookie }, cache: "no-store" }),
    fetch(`${API_BASE}/api/admin/users`, { headers: { cookie }, cache: "no-store" }),
  ]);
  if (!actRes.ok) throw new Error(`activity ${actRes.status}`);
  if (!userRes.ok) throw new Error(`users ${userRes.status}`);
  const { items } = (await actRes.json()) as { items: ActivityRow[] };
  const { items: users } = (await userRes.json()) as { items: UserRow[] };

  // 한 장이 꽉 찼을 때만 다음 장이 있다. 워커의 기본 limit 과 같은 값이다.
  const PAGE = 50;
  // 커서는 (ts, id) 쌍이다. ts 만 쓰면 같은 초에 걸친 항목이 페이지 경계에서 사라진다.
  const last = items.length === PAGE ? items[items.length - 1]! : null;
  const nextQs = new URLSearchParams(qs);
  if (last) {
    nextQs.set("before", String(last.ts));
    nextQs.set("before_id", last.id);
  }

  return (
    <main>
      <h1 className="text-xl font-semibold">활동 이력</h1>

      <FilterBar>
        <FilterField label="사용자">
          <select name="sub" defaultValue={sp.sub ?? ""} className={COMPACT_INPUT_CLASS}>
            <option value="">전체 사용자</option>
            {users.map((u) => (
              <option key={u.sub} value={u.sub}>{u.email}</option>
            ))}
          </select>
        </FilterField>
        <FilterField label="종류">
          <select name="kind" defaultValue={sp.kind ?? ""} className={COMPACT_INPUT_CLASS}>
            <option value="">전체 종류</option>
            {Object.entries(KIND_LABEL).map(([k, label]) => (
              <option key={k} value={k}>{label}</option>
            ))}
          </select>
        </FilterField>
      </FilterBar>

      {items.length === 0 ? (
        <EmptyState>활동이 없습니다.</EmptyState>
      ) : (
        <Table head={["시각", "사용자", "종류", "내용", "상태"]}>
          {items.map((it) => (
            <tr key={it.id} className="border-b border-popory-border">
              <td className="py-2 pr-4 text-xs text-popory-muted">{formatKst(it.ts)}</td>
              <td className="py-2 pr-4 text-xs">
                {it.user_sub ? (
                  <Link href={`/admin/users/${it.user_sub}`} className="text-popory-accent">{it.user_email ?? it.user_sub}</Link>
                ) : (
                  <span className="text-popory-muted">—</span>
                )}
              </td>
              <td className="py-2 pr-4 text-xs text-popory-muted">{KIND_LABEL[it.kind] ?? it.kind}</td>
              <td className="py-2 pr-4">
                {it.href ? <Link href={it.href} className="text-popory-accent">{it.title}</Link> : it.title}
              </td>
              <td className="py-2 text-xs">
                {it.status ? <Badge intent={statusIntent(it.status)}>{statusLabel(it.status)}</Badge> : ""}
              </td>
            </tr>
          ))}
        </Table>
      )}

      {last && (
        <Link href={`/admin/activity?${nextQs}`} className="mt-6 inline-block text-sm text-popory-accent">
          더 보기
        </Link>
      )}
    </main>
  );
}
```

- [ ] **Step 2: typecheck 후 commit**

Run: `pnpm --filter @popory/portal typecheck` → 에러 0.

```bash
git add apps/portal/src/app/admin/activity/page.tsx
git commit -m "refactor(admin): 활동 이력을 공통 기반으로 전환"
```

---

### Task 10: 오류 로그 전환

**Files:**
- Modify: `apps/portal/src/app/admin/errors/page.tsx` (전체 교체)
- Modify: `apps/portal/src/app/admin/errors/ErrorRow.tsx` (전체 교체)

**Interfaces:**
- Consumes: `FilterBar`, `FilterField`, `COMPACT_INPUT_CLASS`, `EmptyState`, `Badge`, `formatKst`, `serviceLabel`.

- [ ] **Step 1: errors/page.tsx 전체 교체**

```tsx
// 로컬 잡(content·brief)의 실패 로그 조회 화면.
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { ErrorRow } from "./ErrorRow";
import { EmptyState } from "../_components/EmptyState";
import { FilterBar, FilterField } from "../_components/FilterBar";
import { COMPACT_INPUT_CLASS } from "../_components/field";
import { serviceLabel } from "../_lib/labels";

interface LogRow {
  id: string;
  service: string;
  cli: string;
  status: string;
  job_id: string | null;
  owner_sub: string | null;
  detail: string;
  created_at: number;
}

export default async function ErrorsPage({
  searchParams,
}: {
  searchParams: Promise<{ service?: string; status?: string }>;
}) {
  const sp = await searchParams;
  const cookie = (await headers()).get("cookie") ?? "";
  const qs = new URLSearchParams();
  if (sp.service) qs.set("service", sp.service);
  if (sp.status) qs.set("status", sp.status);
  const res = await fetch(`${API_BASE}/api/admin/job-logs?${qs}`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) throw new Error(`job-logs ${res.status}`);
  const { items } = (await res.json()) as { items: LogRow[] };

  return (
    <main>
      <h1 className="text-xl font-semibold">오류 로그</h1>
      <p className="mt-1 text-sm text-popory-muted">최근 7일. 로컬 잡이 실패를 남길 때마다 올라옵니다.</p>

      <FilterBar>
        <FilterField label="서비스">
          <select name="service" defaultValue={sp.service ?? ""} className={COMPACT_INPUT_CLASS}>
            <option value="">전체 서비스</option>
            <option value="content">{serviceLabel("content")}</option>
            <option value="brief">{serviceLabel("brief")}</option>
          </select>
        </FilterField>
        <FilterField label="상태">
          <input
            name="status"
            defaultValue={sp.status ?? ""}
            placeholder="예. item_fail"
            className={COMPACT_INPUT_CLASS}
          />
        </FilterField>
      </FilterBar>

      {items.length === 0 ? (
        <EmptyState>최근 7일간 실패가 없습니다.</EmptyState>
      ) : (
        <ul className="mt-6 space-y-2">
          {items.map((it) => (
            <ErrorRow key={it.id} row={it} />
          ))}
        </ul>
      )}
    </main>
  );
}
```

- [ ] **Step 2: ErrorRow.tsx 전체 교체**

```tsx
"use client";
// 오류 로그 한 줄. 펼치면 원본 JSON 을 보여준다.
import { useState } from "react";
import { Badge } from "../_components/Badge";
import { formatKst } from "../_lib/format";
import { serviceLabel } from "../_lib/labels";

interface Row {
  id: string;
  service: string;
  cli: string;
  status: string;
  job_id: string | null;
  detail: string;
  created_at: number;
}

function summary(detail: string): string {
  try {
    const d = JSON.parse(detail) as Record<string, unknown>;
    return String(d.error ?? d.message ?? "");
  } catch {
    return "";
  }
}

// 펼침 영역용 본문. JSON 이면 예쁘게, 아니면 원문 그대로 (parse 가 던지면 화면 전체가 죽는다).
function pretty(detail: string): string {
  try {
    return JSON.stringify(JSON.parse(detail), null, 2);
  } catch {
    return detail;
  }
}

export function ErrorRow({ row }: { row: Row }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-md border border-popory-border bg-popory-card p-3 text-sm">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full flex-wrap items-baseline gap-x-3 gap-y-1 text-left"
      >
        <span className="text-xs text-popory-muted">{formatKst(row.created_at)}</span>
        <span className="text-xs">{serviceLabel(row.service)}</span>
        <span className="text-xs">{row.cli}</span>
        <Badge intent="danger">{row.status}</Badge>
        <span className="w-full truncate text-xs text-popory-muted sm:w-auto sm:flex-1">{summary(row.detail)}</span>
      </button>
      {open && (
        <pre className="mt-2 overflow-x-auto rounded bg-popory-bg p-2 text-xs text-popory-fg">
          {pretty(row.detail)}
        </pre>
      )}
    </li>
  );
}
```

- [ ] **Step 3: typecheck 후 commit**

Run: `pnpm --filter @popory/portal typecheck` → 에러 0.

```bash
git add apps/portal/src/app/admin/errors
git commit -m "refactor(admin): 오류 로그를 공통 기반으로 전환"
```

---

### Task 11: 화이트리스트 전환

**Files:**
- Modify: `apps/portal/src/app/admin/whitelist/page.tsx` (전체 교체)

**Interfaces:**
- Consumes: `Button`, `ConfirmSubmitButton`, `EmptyState`, `INPUT_CLASS`. server action `addEmail`/`removeEmail`은 그대로 둔다.

- [ ] **Step 1: whitelist/page.tsx 전체 교체**

```tsx
// 화이트리스트 추가·삭제 UI.
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { addEmail, removeEmail } from "./actions";
import { Button } from "../_components/Button";
import { ConfirmSubmitButton } from "../_components/ConfirmSubmitButton";
import { EmptyState } from "../_components/EmptyState";
import { INPUT_CLASS } from "../_components/field";

async function listEmails() {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/whitelist`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) throw new Error(`whitelist ${res.status}`);
  return ((await res.json()) as { items: { email: string; note: string | null; created_at: number }[] }).items;
}

export default async function WhitelistPage() {
  const items = await listEmails();
  return (
    <main>
      <h1 className="text-xl font-semibold">화이트리스트</h1>
      <form action={addEmail} className="mt-4 flex flex-col gap-2 sm:flex-row">
        <label className="w-full">
          <span className="sr-only">이메일</span>
          <input name="email" type="email" required placeholder="email" className={INPUT_CLASS} />
        </label>
        <label className="w-full">
          <span className="sr-only">메모</span>
          <input name="note" placeholder="메모" className={INPUT_CLASS} />
        </label>
        <Button type="submit" variant="primary" className="shrink-0">추가</Button>
      </form>
      {items.length === 0 ? (
        <EmptyState>화이트리스트가 비어 있습니다.</EmptyState>
      ) : (
        <ul className="mt-6 space-y-2">
          {items.map((it) => (
            <li key={it.email} className="flex items-center justify-between gap-3 border-b border-popory-border py-2">
              <span className="min-w-0 truncate text-sm text-popory-fg">{it.email} {it.note ? `· ${it.note}` : ""}</span>
              <form action={removeEmail} className="shrink-0">
                <input type="hidden" name="email" value={it.email} />
                <ConfirmSubmitButton message={`${it.email} 을(를) 화이트리스트에서 삭제할까요?`} variant="danger" pendingLabel="삭제 중…">
                  삭제
                </ConfirmSubmitButton>
              </form>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
```

- [ ] **Step 2: typecheck 후 commit**

Run: `pnpm --filter @popory/portal typecheck` → 에러 0.

```bash
git add apps/portal/src/app/admin/whitelist/page.tsx
git commit -m "refactor(admin): 화이트리스트를 공통 기반으로 전환"
```

---

### Task 12: 브리핑 카테고리 전환

**Files:**
- Modify: `apps/portal/src/app/admin/brief-categories/page.tsx` (전체 교체)
- Modify: `apps/portal/src/app/admin/brief-categories/new/NewForm.tsx` (부분 수정)
- Modify: `apps/portal/src/app/admin/brief-categories/[slug]/EditForm.tsx` (부분 수정)

**Interfaces:**
- Consumes: `Table`, `Badge`, `EmptyState`, `Button`, `INPUT_CLASS`, `deliveryLabel`.

- [ ] **Step 1: brief-categories/page.tsx 전체 교체**

조용한 실패(빈 배열 반환)를 throw로 바꾸고 공통 컴포넌트를 쓴다.

```tsx
// admin · brief 카테고리 목록 + [편집] 링크.
import { headers } from "next/headers";
import Link from "next/link";
import { API_BASE } from "@/lib/env";
import { Table } from "../_components/Table";
import { Badge } from "../_components/Badge";
import { EmptyState } from "../_components/EmptyState";
import { deliveryLabel } from "../_lib/labels";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface CategoryRow {
  slug: string;
  name: string;
  delivery_mode: "standalone" | "bundled";
  enabled: boolean;
  sha: string;
}

async function fetchList(cookie: string): Promise<CategoryRow[]> {
  const res = await fetch(`${API_BASE}/api/admin/brief-categories`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) throw new Error(`brief-categories ${res.status}`);
  const { items } = (await res.json()) as { items: CategoryRow[] };
  return items;
}

export default async function BriefCategoriesPage() {
  const cookie = (await headers()).get("cookie") ?? "";
  const items = await fetchList(cookie);
  return (
    <main>
      <div className="flex items-baseline gap-3">
        <h1 className="text-xl font-semibold">브리핑 카테고리</h1>
        <Link href="/admin/brief-categories/new" className="ml-auto text-sm text-popory-accent">
          + 새 카테고리
        </Link>
      </div>
      <p className="mt-2 text-sm text-popory-muted">
        services/brief/categories/&#123;slug&#125;/SKILL.md 를 GitHub에서 read/edit. 저장 시 main 브랜치에 commit.
      </p>
      {items.length === 0 ? (
        <EmptyState>카테고리가 없습니다. 첫 카테고리를 추가해 보세요.</EmptyState>
      ) : (
        <Table head={["slug", "이름", "모드", "활성", "sha", ""]}>
          {items.map((c) => (
            <tr key={c.slug} className="border-b border-popory-border">
              <td className="py-2 pr-4 font-mono text-xs text-popory-fg">{c.slug}</td>
              <td className="py-2 pr-4 text-sm text-popory-fg">{c.name}</td>
              <td className="py-2 pr-4 text-sm text-popory-fg">{deliveryLabel(c.delivery_mode)}</td>
              <td className="py-2 pr-4">
                {c.enabled ? <Badge intent="success">활성</Badge> : <Badge intent="neutral">비활성</Badge>}
              </td>
              <td className="py-2 pr-4 font-mono text-[11px] text-popory-muted">{c.sha.slice(0, 7)}</td>
              <td className="py-2 text-sm">
                <Link href={`/admin/brief-categories/${c.slug}`} className="text-popory-accent">편집</Link>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </main>
  );
}
```

- [ ] **Step 2: NewForm.tsx 부분 수정**

세 군데만 바꾼다 (외과적 변경 — 나머지는 그대로).

수정 1. 로컬 `INPUT` 상수 제거하고 공통 상수 import.

```tsx
// 삭제
const INPUT = "w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg";
// import 에 추가
import { INPUT_CLASS as INPUT } from "../../_components/field";
```

수정 2. 에러 배너의 하드코딩 색을 토큰으로.

```tsx
// 기존
<div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
// 교체
<div className="rounded-md border border-popory-danger bg-popory-danger-soft px-4 py-3 text-sm text-popory-fg">
```

(배너 안의 `font-semibold` div에는 `text-popory-danger`를 추가한다.)

수정 3. 하단 제출 버튼을 공통 Button으로.

```tsx
// import 에 추가
import { Button } from "../../_components/Button";
// 기존 제출 button 교체
<Button type="submit" variant="primary" disabled={busy}>
  {busy ? "생성 중…" : "생성 (GitHub commit)"}
</Button>
```

취소 `<a>`는 그대로 둔다.

- [ ] **Step 3: EditForm.tsx 부분 수정**

NewForm과 같은 방식으로 네 군데.

수정 1. 로컬 `INPUT` 상수 제거 후 `import { INPUT_CLASS as INPUT } from "../../_components/field";`

수정 2. 에러 배너를 NewForm 수정 2와 동일하게 교체 (`저장 실패` div에 `text-popory-danger` 추가).

수정 3. 제출 버튼을 `<Button type="submit" variant="primary" disabled={busy}>{busy ? "저장 중…" : "저장 (GitHub commit)"}</Button>`으로 교체 (`import { Button } from "../../_components/Button";` 추가).

수정 4. 삭제 버튼의 하드코딩 색을 danger variant로 교체. `confirm()` 로직은 그대로 둔다.

```tsx
// 기존
<button type="button" onClick={onDelete} disabled={busy}
  className="ml-auto rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/40">
  {busy ? "처리 중…" : "삭제"}
</button>
// 교체
<Button type="button" variant="danger" onClick={onDelete} disabled={busy} className="ml-auto hover:bg-popory-danger-soft">
  {busy ? "처리 중…" : "삭제"}
</Button>
```

- [ ] **Step 4: typecheck 후 commit**

Run: `pnpm --filter @popory/portal typecheck` → 에러 0.

```bash
git add apps/portal/src/app/admin/brief-categories
git commit -m "refactor(admin): 브리핑 카테고리를 공통 기반으로 전환"
```

---

### Task 13: 생성 상태 화면 /admin/status 이전

**Files:**
- Create: `apps/portal/src/app/admin/status/page.tsx`
- Create: `apps/portal/src/app/admin/status/StatusPanel.tsx` (기존 파일 이동+수정)
- Modify: `apps/portal/src/app/(authed)/content/status/page.tsx` (전체 교체 — redirect만 남김)
- Delete: `apps/portal/src/app/(authed)/content/status/StatusPanel.tsx`
- Modify: `apps/portal/src/app/(authed)/content/page.tsx:39` (링크 한 줄)

**Interfaces:**
- Consumes: `formatKstIso`, `platformLabel` (Task 2), 상태색 토큰 (Task 1).
- Produces: `/admin/status` 라우트 (Task 6의 탭이 가리키는 대상). API 엔드포인트 `/api/content/status` 권한은 변경하지 않는다.

- [ ] **Step 1: admin/status/page.tsx 작성**

```tsx
// 콘텐츠 생성 상태(readiness + 트래픽) — admin 셸 안에서 클라이언트 패널을 렌더한다.
import { API_BASE } from "@/lib/env";
import { StatusPanel } from "./StatusPanel";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default function AdminStatusPage() {
  return (
    <main>
      <h1 className="text-xl font-semibold">생성 상태</h1>
      <StatusPanel apiBase={API_BASE} />
    </main>
  );
}
```

- [ ] **Step 2: admin/status/StatusPanel.tsx 작성 (이동+수정)**

기존 `(authed)/content/status/StatusPanel.tsx`를 옮기면서 다음만 바꾼다. 폴링·집계 로직은 그대로.

- `PLATFORM_LABEL` 로컬 맵 제거 → `import { platformLabel } from "../_lib/labels";` 후 `{platformLabel(p)}` 사용.
- `fmtReset` 로컬 함수 제거 → `import { formatKstIso } from "../_lib/format";` 후 `formatKstIso(item.resets_at)` 사용.
- 색 상수 교체.

```tsx
const SEV_BAR: Record<string, string> = { normal: "bg-popory-success", warning: "bg-popory-warn", critical: "bg-popory-danger" };
const SEV_TEXT: Record<string, string> = { normal: "text-popory-success", warning: "text-popory-warn", critical: "text-popory-danger" };
```

- `UsageRow`의 fallback `bar`도 `"bg-popory-success"`로.
- can_generate 배너 교체.

```tsx
<div className={`mt-3 rounded-lg px-4 py-3 text-sm font-medium ${s.can_generate ? "bg-popory-success-soft text-popory-success" : "bg-popory-danger-soft text-popory-danger"}`}>
```

- 개별 상태 텍스트의 `text-green-600`→`text-popory-success`, `text-red-600`→`text-popory-danger`, `text-yellow-600`→`text-popory-warn`, 에러 문구 `text-red-500`→`text-popory-danger`.
- 첫 줄 주석은 기존 그대로 유지한다 (`"use client";` 직후 한국어 역할 주석).

- [ ] **Step 3: 구 경로 redirect 처리**

`(authed)/content/status/page.tsx` 전체 교체.

```tsx
// 구 경로 /content/status → /admin/status 리다이렉트 (북마크 보존).
import { redirect } from "next/navigation";

export const runtime = "edge";

export default function ContentStatusRedirect() {
  redirect("/admin/status");
}
```

`(authed)/content/status/StatusPanel.tsx`는 `git rm`으로 삭제한다.

- [ ] **Step 4: content 홈의 링크 수정**

`(authed)/content/page.tsx`의 nav에서 기존 줄

```tsx
<Link href="/content/status" className="hover:text-popory-fg">생성 상태</Link>
```

을 admin 전용 조건부로 교체한다 (`user`는 이미 스코프에 있다).

```tsx
{user.role === "admin" && (
  <Link href="/admin/status" className="hover:text-popory-fg">생성 상태</Link>
)}
```

- [ ] **Step 5: typecheck 후 commit**

Run: `pnpm --filter @popory/portal typecheck` → 에러 0.

```bash
git add apps/portal/src/app/admin/status "apps/portal/src/app/(authed)/content/status" "apps/portal/src/app/(authed)/content/page.tsx"
git commit -m "feat(admin): 생성 상태 화면을 /admin/status 로 이전"
```

---

### Task 14: 최종 검증

**Files:** 없음 (검증 전용. 발견된 결함 수정 커밋만 허용)

- [ ] **Step 1: 전체 정적 검증**

Run: `pnpm lint && pnpm typecheck && pnpm test`
Expected: 전부 통과 (portal은 lint/test 스크립트가 없어 turbo가 건너뜀 — 실패만 아니면 됨).

- [ ] **Step 2: 프로덕션 빌드**

Run: `pnpm --filter @popory/portal build`
Expected: 빌드 성공, `/admin/*` 라우트 목록에 `/admin/status` 포함.

- [ ] **Step 3: 렌더 확인 (qa-runner)**

`pnpm --filter @popory/portal dev` 구동 후 admin 계정 세션으로 다음을 확인한다.

- 8개 라우트(`/admin`, `/admin/users`, `/admin/users/[sub]`, `/admin/activity`, `/admin/errors`, `/admin/status`, `/admin/whitelist`, `/admin/brief-categories`) 렌더와 탭 활성 표시.
- `/content/status` 접속 시 `/admin/status`로 redirect.
- activity·errors 필터 제출, users 역할 변경·차단의 confirm 노출, whitelist 삭제 confirm.
- 375px 폭에서 테이블 가로 스크롤과 탭 바 가로 스크롤.
- 워커 API를 끄거나 API_BASE를 잘못 준 상태에서 admin 페이지가 error.tsx(다시 시도 버튼)를 보여주는지.

- [ ] **Step 4: 교차 리뷰**

`scripts/ai/codex-review.sh main` 실행 후 code-reviewer 서브에이전트 리뷰와 수렴 (교집합 즉시 수정, 차집합은 사람에게 보고).
