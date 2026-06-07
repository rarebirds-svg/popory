# Brief Feed Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/p/brief` 페이지를 카테고리 카드 그리드에서 통합 피드로 교체한다. 카테고리 필터 칩(URL 파라미터 방식)과 더 보기 버튼을 포함한다.

**Architecture:** 서버 컴포넌트(`page.tsx`)가 `searchParams.cat`으로 카테고리를 읽어 API에서 데이터를 fetch하고, 두 클라이언트 컴포넌트(`FilterChips`, `FeedList`)에 props로 전달한다. 더 보기는 클라이언트에서 누적 limit으로 직접 재fetch한다.

**Tech Stack:** Next.js 15 (edge runtime), React 19, Tailwind CSS, TypeScript

---

## 파일 구조

| 상태 | 경로 | 역할 |
|---|---|---|
| **Rewrite** | `apps/portal/src/app/p/brief/page.tsx` | 서버 컴포넌트. searchParams 수신, fetch, FilterChips + FeedList 조합 |
| **New** | `apps/portal/src/app/p/brief/FilterChips.tsx` | 클라이언트 컴포넌트. 카테고리 칩 렌더 + router.push |
| **New** | `apps/portal/src/app/p/brief/FeedList.tsx` | 클라이언트 컴포넌트. 피드 목록 렌더 + 더 보기 |

변경 없는 파일: 백엔드 API 전체, `/p/[area]/page.tsx`, `/p/[area]/[id]/page.tsx`

---

## Task 1: FilterChips 클라이언트 컴포넌트

**Files:**
- Create: `apps/portal/src/app/p/brief/FilterChips.tsx`

- [ ] **Step 1: 파일 생성**

```typescript
'use client'
// 브리핑 피드 카테고리 필터 칩 컴포넌트. 칩 클릭 시 ?cat= URL 파라미터로 이동.

import { useRouter } from "next/navigation";

export interface CategoryMeta {
  slug: string;
  name: string;
}

interface FilterChipsProps {
  categories: CategoryMeta[];
  activeCat: string; // "" = 전체
}

export function FilterChips({ categories, activeCat }: FilterChipsProps) {
  const router = useRouter();

  const handleClick = (slug: string) => {
    router.push(slug === "" ? "/p/brief" : `/p/brief?cat=${slug}`);
  };

  const base = "rounded-full px-3 py-1.5 text-xs font-medium transition cursor-pointer";
  const active = `${base} bg-popory-fg text-popory-bg`;
  const inactive = `${base} border border-popory-border text-popory-fg2 hover:border-popory-accent`;

  return (
    <div className="sticky top-0 z-10 border-b border-popory-border bg-popory-bg py-3">
      <div className="flex flex-wrap gap-2">
        <button onClick={() => handleClick("")} className={activeCat === "" ? active : inactive}>
          전체
        </button>
        {categories.map((c) => (
          <button key={c.slug} onClick={() => handleClick(c.slug)} className={c.slug === activeCat ? active : inactive}>
            {c.name}
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 타입체크**

```bash
cd apps/portal && pnpm typecheck
```

기대 결과: `FilterChips.tsx` 관련 에러 없음. (다른 파일은 아직 page.tsx가 교체 전이라 에러 없어야 함)

- [ ] **Step 3: 커밋**

```bash
git add apps/portal/src/app/p/brief/FilterChips.tsx
git commit -m "feat(portal): 브리핑 피드 FilterChips 컴포넌트"
```

---

## Task 2: FeedList 클라이언트 컴포넌트

**Files:**
- Create: `apps/portal/src/app/p/brief/FeedList.tsx`

- [ ] **Step 1: 파일 생성**

```typescript
'use client'
// 브리핑 피드 목록 렌더 및 더 보기 버튼. 누적 limit 방식으로 추가 로드.

import { useState } from "react";
import Link from "next/link";
import { API_BASE } from "@/lib/env";

export interface FeedItem {
  id: string;
  area: string;
  title: string;
  summary: string | null;
  published_at: number;
}

interface FeedListProps {
  initialItems: FeedItem[];
  activeCat: string; // "" = 전체, "realestate" 등 slug
  categoryNames: Record<string, string>; // slug → 한국어 이름
}

// slug → 배지 색상 (Tailwind 표준 컬러)
const BADGE_COLOR: Record<string, { bg: string; text: string }> = {
  realestate:     { bg: "bg-blue-100",   text: "text-blue-700" },
  anticorruption: { bg: "bg-red-100",    text: "text-red-700" },
  chaebol:        { bg: "bg-amber-100",  text: "text-amber-800" },
  sanction:       { bg: "bg-purple-100", text: "text-purple-700" },
  antitrust:      { bg: "bg-green-100",  text: "text-green-700" },
  "legal-ai":     { bg: "bg-sky-100",    text: "text-sky-700" },
};

const PAGE_SIZE = 60;

function slugFromArea(area: string) {
  return area.replace(/^brief-/, "");
}

function dayOf(ts: number) {
  return new Date(ts * 1000).getDate();
}

function monthOf(ts: number) {
  return `${new Date(ts * 1000).getMonth() + 1}월`;
}

export function FeedList({ initialItems, activeCat, categoryNames }: FeedListProps) {
  const [items, setItems] = useState<FeedItem[]>(initialItems);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [loading, setLoading] = useState(false);
  const [exhausted, setExhausted] = useState(initialItems.length < PAGE_SIZE);

  const loadMore = async () => {
    setLoading(true);
    const nextLimit = limit + PAGE_SIZE;
    const area = activeCat ? `brief-${activeCat}` : "";
    const url = area
      ? `${API_BASE}/api/published_items?area=${area}&limit=${nextLimit}`
      : `${API_BASE}/api/published_items?limit=${nextLimit}`;
    try {
      const res = await fetch(url);
      if (!res.ok) return;
      const { items: next } = (await res.json()) as { items: FeedItem[] };
      setItems(next);
      setLimit(nextLimit);
      if (next.length < nextLimit) setExhausted(true);
    } finally {
      setLoading(false);
    }
  };

  if (items.length === 0) {
    return <p className="mt-8 text-sm text-popory-muted">아직 발행된 브리핑이 없습니다.</p>;
  }

  return (
    <>
      <ul>
        {items.map((it) => {
          const slug = slugFromArea(it.area);
          const badge = BADGE_COLOR[slug] ?? { bg: "bg-gray-100", text: "text-gray-700" };
          const name = categoryNames[slug] ?? slug;
          return (
            <li key={it.id}>
              <Link
                href={`/p/${it.area}/${it.id}`}
                className="flex gap-4 border-b border-popory-border py-4 transition hover:bg-popory-accent-soft/40"
              >
                <div className="w-10 shrink-0 text-center">
                  <div className="font-serif text-xl font-semibold leading-none text-popory-fg">
                    {dayOf(it.published_at)}
                  </div>
                  <div className="mt-0.5 text-[9px] uppercase tracking-widest text-popory-muted">
                    {monthOf(it.published_at)}
                  </div>
                </div>
                <div className="flex-1">
                  <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-bold ${badge.bg} ${badge.text}`}>
                    {name}
                  </span>
                  <h2 className="mt-1.5 text-[15px] font-bold leading-snug text-popory-fg">
                    {it.title}
                  </h2>
                  {it.summary && (
                    <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-popory-muted">
                      {it.summary}
                    </p>
                  )}
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
      {!exhausted && (
        <div className="mt-6 flex justify-center pb-10">
          <button
            onClick={loadMore}
            disabled={loading}
            className="rounded-full border border-popory-border px-5 py-2 text-sm text-popory-fg2 transition hover:border-popory-accent disabled:opacity-50"
          >
            {loading ? "불러오는 중…" : "더 보기"}
          </button>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 2: 타입체크**

```bash
cd apps/portal && pnpm typecheck
```

기대 결과: `FeedList.tsx` 관련 에러 없음.

- [ ] **Step 3: 커밋**

```bash
git add apps/portal/src/app/p/brief/FeedList.tsx
git commit -m "feat(portal): 브리핑 피드 FeedList 컴포넌트 (더 보기 포함)"
```

---

## Task 3: page.tsx 교체

**Files:**
- Modify: `apps/portal/src/app/p/brief/page.tsx` (전체 교체)

- [ ] **Step 1: page.tsx 전체 교체**

기존 파일을 아래 내용으로 완전 교체한다.

```typescript
// popory 일일 브리핑 통합 피드 페이지. 카테고리 필터 칩 + 날짜순 피드.
import { Kicker } from "@popory/ui";
import { API_BASE } from "@/lib/env";
import { FilterChips, type CategoryMeta } from "./FilterChips";
import { FeedList, type FeedItem } from "./FeedList";

export const dynamic = "force-dynamic";
export const runtime = "edge";

const PAGE_SIZE = 60;

const VALID_SLUGS = new Set([
  "realestate", "anticorruption", "chaebol", "sanction", "antitrust", "legal-ai",
]);

async function fetchCategories(): Promise<CategoryMeta[]> {
  try {
    const res = await fetch(`${API_BASE}/api/brief-categories`, { cache: "no-store" });
    if (!res.ok) return [];
    const { items } = (await res.json()) as { items: CategoryMeta[] };
    return items;
  } catch {
    return [];
  }
}

async function fetchItems(activeCat: string): Promise<FeedItem[]> {
  try {
    const url = activeCat
      ? `${API_BASE}/api/published_items?area=brief-${activeCat}&limit=${PAGE_SIZE}`
      : `${API_BASE}/api/published_items?limit=${PAGE_SIZE}`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return [];
    const { items } = (await res.json()) as { items: FeedItem[] };
    return items;
  } catch {
    return [];
  }
}

export default async function BriefFeedPage({
  searchParams,
}: {
  searchParams: Promise<{ cat?: string }>;
}) {
  const { cat } = await searchParams;
  // 유효하지 않은 slug는 전체 피드로 폴백
  const activeCat = cat && VALID_SLUGS.has(cat) ? cat : "";

  const [cats, items] = await Promise.all([
    fetchCategories(),
    fetchItems(activeCat),
  ]);

  const categoryNames: Record<string, string> = Object.fromEntries(
    cats.map((c) => [c.slug, c.name]),
  );

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <Kicker>Daily Briefings</Kicker>
      <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">
        매일 아침, 여러 갈래의 세상
      </h1>
      <p className="mt-2 text-sm text-popory-muted">
        AI가 큐레이션한 일일 브리핑. 매일 09:00 KST 발행.
      </p>
      <div className="mt-6">
        <FilterChips categories={cats} activeCat={activeCat} />
        <FeedList initialItems={items} activeCat={activeCat} categoryNames={categoryNames} />
      </div>
    </main>
  );
}
```

- [ ] **Step 2: 타입체크**

```bash
cd apps/portal && pnpm typecheck
```

기대 결과: 에러 0개.

- [ ] **Step 3: 커밋**

```bash
git add apps/portal/src/app/p/brief/page.tsx
git commit -m "feat(portal): /p/brief 카드 그리드 → 통합 피드 (카테고리 필터 + 더 보기)"
```

---

## Task 4: 동작 검증

**Files:** 없음 (읽기 전용 확인)

- [ ] **Step 1: 개발 서버 실행**

```bash
cd apps/portal && pnpm dev
```

- [ ] **Step 2: 기본 피드 확인**

브라우저에서 `http://localhost:3000/p/brief` 접속.

체크리스트:
- 헤더("매일 아침, 여러 갈래의 세상") 표시됨
- 상단 필터 칩 (`전체` 활성 상태) 표시됨
- 피드 아이템: 날짜 숫자·월·카테고리 배지·제목·요약 2줄 표시됨
- 아이템이 60개 미만이면 더 보기 버튼 없음, 60개 이상이면 버튼 있음

- [ ] **Step 3: 카테고리 필터 확인**

`부동산` 칩 클릭 → URL이 `/p/brief?cat=realestate`로 변경되고 피드가 부동산만 표시됨.
`전체` 클릭 → `/p/brief`로 돌아오고 전체 피드 복원됨.

- [ ] **Step 4: 개별 글 진입 확인**

피드 아이템 클릭 → `/p/brief-{slug}/{id}` 상세 페이지 정상 이동.

- [ ] **Step 5: 기존 카테고리 목록 페이지 확인**

`http://localhost:3000/p/brief-realestate` 직접 접속 → 기존 목록 페이지 그대로 동작함.

- [ ] **Step 6: 개발 서버 종료**

`Ctrl+C`

---

## 완료 기준

- [ ] `pnpm typecheck` 에러 0개
- [ ] `/p/brief` 피드 표시 (날짜·배지·제목·요약)
- [ ] 카테고리 필터 칩 → URL 파라미터 방식으로 동작
- [ ] 더 보기 버튼 동작 (60건 초과 시 표시)
- [ ] 기존 `/p/brief-{slug}` 페이지 영향 없음
