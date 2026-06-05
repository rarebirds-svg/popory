# 컨텐츠 관리 Slice 1 · Phase B (포털 UI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** popory 포털에 컨텐츠 작업 생성·초안 검토·스타일 프로필 UI(`/content`)를 추가하고 대시보드 카드를 내부 페이지로 연결한다.

**Architecture:** Next.js 15 App Router. 서버 컴포넌트가 쿠키를 실어 Worker API(`/api/content/*`, Phase A)를 호출해 데이터를 가져오고, 폼은 client component가 `API_BASE` + `credentials:include`로 POST/PATCH한다. 각 페이지는 `getCurrentUser`로 자체 인증(미로그인 시 `/` 리다이렉트). 기존 어드민 폼·Ledger 톤·`popory-*` 토큰 재사용.

**Tech Stack:** Next.js 15, React 19, Tailwind(`popory-*` 토큰), TypeScript.

**전제:** Phase A(`2026-06-05-content-studio-slice1-backend.md`)가 머지돼 `/api/content/*` 라우트가 동작해야 한다. 스펙: `docs/superpowers/specs/2026-06-05-content-studio-naver-design.md`.

**검증 방식:** 포털은 페이지 단위 테스트가 없으므로 각 태스크는 `pnpm --filter @popory/portal typecheck` + `pnpm --filter @popory/portal build` 통과로 검증한다.

---

## File Structure

| 파일 | 책임 | 신규/수정 |
|------|------|-----------|
| `apps/portal/src/app/(authed)/content/page.tsx` | 작업 목록 + 진입 | 신규 |
| `apps/portal/src/app/(authed)/content/new/page.tsx` | 새 작업 폼 셸(스타일 프로필 서버 fetch) | 신규 |
| `apps/portal/src/app/(authed)/content/new/NewJobForm.tsx` | 작업 생성 client 폼 | 신규 |
| `apps/portal/src/app/(authed)/content/[id]/page.tsx` | 작업 상세 셸(서버 fetch) | 신규 |
| `apps/portal/src/app/(authed)/content/[id]/DraftEditor.tsx` | 초안 검토·편집 client | 신규 |
| `apps/portal/src/app/(authed)/content/styles/page.tsx` | 스타일 프로필 목록 | 신규 |
| `apps/portal/src/app/(authed)/content/styles/new/page.tsx` | 스타일 프로필 생성 셸 | 신규 |
| `apps/portal/src/app/(authed)/content/styles/new/StyleProfileForm.tsx` | 샘플 10개 입력 client | 신규 |
| `apps/portal/src/app/(authed)/dashboard/page.tsx` | "컨텐츠 관리" 카드 href 교정 | 수정 |

공통 상수(`INPUT` className 등)는 각 client 파일에 로컬 선언한다 — 기존 `NewForm.tsx`가 그러하듯(작은 중복 허용, 파일 독립성 우선).

---

## Task 1: 작업 목록 페이지

**Files:**
- Create: `apps/portal/src/app/(authed)/content/page.tsx`

- [ ] **Step 1: 페이지 작성**

`apps/portal/src/app/(authed)/content/page.tsx`:

```tsx
// 컨텐츠 작업 목록 — 상태별 진입. GET /api/content/jobs.
import { redirect } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface JobRow {
  id: string;
  topic: string;
  status: "queued" | "running" | "review" | "done" | "failed";
  created_at: number;
}

const STATUS_LABEL: Record<JobRow["status"], string> = {
  queued: "대기 중",
  running: "생성 중",
  review: "검토 필요",
  done: "완료",
  failed: "실패",
};

async function fetchJobs(cookie: string): Promise<JobRow[]> {
  const res = await fetch(`${API_BASE}/api/content/jobs`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  const { jobs } = (await res.json()) as { jobs: JobRow[] };
  return jobs;
}

export default async function ContentPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const jobs = await fetchJobs(cookie);

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>컨텐츠 관리</Kicker>
        <div className="mt-3 flex items-baseline gap-3">
          <h1 className="font-serif text-3xl font-semibold tracking-tight text-popory-fg">내 컨텐츠</h1>
          <Link href="/content/styles" className="ml-auto text-sm text-popory-muted hover:text-popory-fg">스타일 프로필</Link>
          <Link href="/content/new" className="text-sm font-medium text-popory-accent">+ 새 작업</Link>
        </div>
        <p className="mt-2 text-sm text-popory-muted">주제를 넣으면 리서치·검토를 거친 네이버 블로그 초안을 만듭니다.</p>

        {jobs.length === 0 ? (
          <p className="mt-10 text-sm text-popory-muted">아직 작업이 없습니다. “새 작업”으로 시작하세요.</p>
        ) : (
          <ul className="mt-8 divide-y divide-popory-border">
            {jobs.map((j) => (
              <li key={j.id}>
                <Link href={`/content/${j.id}`} className="flex items-center gap-3 py-3 hover:opacity-80">
                  <span className="flex-1 truncate text-sm text-popory-fg">{j.topic}</span>
                  <span className="shrink-0 rounded-full border border-popory-border px-2 py-0.5 text-xs text-popory-muted">
                    {STATUS_LABEL[j.status]}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 2: 타입체크 + 빌드**

Run: `pnpm --filter @popory/portal typecheck && pnpm --filter @popory/portal build`
Expected: 둘 다 PASS. `@popory/ui`의 `Header`·`Kicker` export 가 없다는 에러가 나면 import 경로를 기존 `dashboard/page.tsx`와 동일하게 맞춘다(추측 금지, 해당 파일 확인).

- [ ] **Step 3: Commit**

```bash
git add "apps/portal/src/app/(authed)/content/page.tsx"
git commit -m "feat(portal): 컨텐츠 작업 목록 페이지"
```

---

## Task 2: 새 작업 폼

**Files:**
- Create: `apps/portal/src/app/(authed)/content/new/page.tsx`
- Create: `apps/portal/src/app/(authed)/content/new/NewJobForm.tsx`

- [ ] **Step 1: 서버 셸 작성 (스타일 프로필 목록 주입)**

`apps/portal/src/app/(authed)/content/new/page.tsx`:

```tsx
// 새 컨텐츠 작업 폼 셸 — 스타일 프로필 목록을 서버에서 fetch 해 폼에 전달.
import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { NewJobForm } from "./NewJobForm";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface StyleProfile { id: string; name: string; }

async function fetchProfiles(cookie: string): Promise<StyleProfile[]> {
  const res = await fetch(`${API_BASE}/api/content/style-profiles`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  const { profiles } = (await res.json()) as { profiles: StyleProfile[] };
  return profiles;
}

export default async function NewJobPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const profiles = await fetchProfiles(cookie);

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-2xl px-4 py-10">
        <Kicker>새 작업</Kicker>
        <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">컨텐츠 만들기</h1>
        <NewJobForm profiles={profiles} />
      </main>
    </div>
  );
}
```

- [ ] **Step 2: client 폼 작성**

`apps/portal/src/app/(authed)/content/new/NewJobForm.tsx`:

```tsx
// 컨텐츠 작업 생성 client 폼 — POST /api/content/jobs.
"use client";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

const INPUT = "w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg";

interface StyleProfile { id: string; name: string; }
interface SourceInput { url: string; note: string; }

export function NewJobForm({ profiles }: { profiles: StyleProfile[] }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [topic, setTopic] = useState("");
  const [styleId, setStyleId] = useState("");
  const [sources, setSources] = useState<SourceInput[]>([]);

  function addSource() { setSources((s) => [...s, { url: "", note: "" }]); }
  function updateSource(i: number, patch: Partial<SourceInput>) {
    setSources((s) => s.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  }
  function removeSource(i: number) { setSources((s) => s.filter((_, idx) => idx !== i)); }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    try {
      const cleanSources = sources
        .map((s) => ({ url: s.url.trim(), note: s.note.trim() }))
        .filter((s) => s.url.length > 0)
        .map((s) => ({ url: s.url, note: s.note || undefined }));
      const res = await fetch(`${API_BASE}/api/content/jobs`, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          topic,
          style_profile_id: styleId || undefined,
          sources: cleanSources.length ? cleanSources : undefined,
        }),
      });
      if (!res.ok) {
        setErr(`worker-${res.status}: ${(await res.text()).slice(0, 300)}`);
        setSubmitting(false);
        return;
      }
      const { id } = (await res.json()) as { id: string };
      startTransition(() => {
        router.push(`/content/${id}`);
        router.refresh();
      });
    } catch (e) {
      setErr(`fetch: ${String(e).slice(0, 200)}`);
      setSubmitting(false);
    }
  }

  const busy = pending || submitting;

  return (
    <form onSubmit={onSubmit} className="mt-6 space-y-4">
      {err && (
        <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          <pre className="whitespace-pre-wrap break-all font-mono text-xs">{err}</pre>
        </div>
      )}

      <label className="block">
        <span className="block text-xs font-semibold text-popory-muted mb-1">주제</span>
        <input value={topic} onChange={(e) => setTopic(e.target.value)} required maxLength={200}
          placeholder="예. 전세사기 예방 체크리스트" className={INPUT} />
      </label>

      <label className="block">
        <span className="block text-xs font-semibold text-popory-muted mb-1">스타일 프로필 (선택)</span>
        <select value={styleId} onChange={(e) => setStyleId(e.target.value)} className={INPUT}>
          <option value="">(기본 톤)</option>
          {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>

      <div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-popory-muted">참고 링크 (선택)</span>
          <button type="button" onClick={addSource} className="text-xs text-popory-accent">+ 추가</button>
        </div>
        <div className="mt-2 space-y-2">
          {sources.map((s, i) => (
            <div key={i} className="flex gap-2">
              <input value={s.url} onChange={(e) => updateSource(i, { url: e.target.value })}
                placeholder="https://…" className={`${INPUT} flex-1`} />
              <input value={s.note} onChange={(e) => updateSource(i, { note: e.target.value })}
                placeholder="메모" className={`${INPUT} w-32`} />
              <button type="button" onClick={() => removeSource(i)} className="text-xs text-popory-muted">삭제</button>
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-3">
        <button type="submit" disabled={busy}
          className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          {busy ? "생성 중…" : "작업 시작"}
        </button>
        <a href="/content" className="rounded-md border border-popory-border px-4 py-2 text-sm">취소</a>
      </div>
    </form>
  );
}
```

- [ ] **Step 3: 타입체크 + 빌드**

Run: `pnpm --filter @popory/portal typecheck && pnpm --filter @popory/portal build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add "apps/portal/src/app/(authed)/content/new"
git commit -m "feat(portal): 새 컨텐츠 작업 폼"
```

---

## Task 3: 작업 상세 · 초안 에디터

**Files:**
- Create: `apps/portal/src/app/(authed)/content/[id]/page.tsx`
- Create: `apps/portal/src/app/(authed)/content/[id]/DraftEditor.tsx`

- [ ] **Step 1: 서버 셸 작성**

`apps/portal/src/app/(authed)/content/[id]/page.tsx`:

```tsx
// 컨텐츠 작업 상세 셸 — GET /api/content/jobs/:id → 상태별 렌더.
import { redirect, notFound } from "next/navigation";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { DraftEditor } from "./DraftEditor";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface JobDetail {
  id: string;
  topic: string;
  status: "queued" | "running" | "review" | "done" | "failed";
  draft?: string;
  meta_json: string | null;
  error: string | null;
  sources: Array<{ id: string; kind: string; url: string | null; title: string | null; note: string | null }>;
}

export default async function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const { id } = await params;
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/content/jobs/${id}`, { headers: { cookie }, cache: "no-store" });
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`job ${res.status}`);
  const job = (await res.json()) as JobDetail;

  const meta = job.meta_json ? (JSON.parse(job.meta_json) as Record<string, unknown>) : null;

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>컨텐츠 작업</Kicker>
        <h1 className="mt-3 font-serif text-2xl font-semibold tracking-tight text-popory-fg">{job.topic}</h1>

        {(job.status === "queued" || job.status === "running") && (
          <p className="mt-8 text-sm text-popory-muted">
            {job.status === "queued" ? "대기 중입니다. 워커가 작업을 가져가면 생성을 시작합니다." : "생성 중입니다. 잠시 후 새로고침하세요."}
          </p>
        )}

        {job.status === "failed" && (
          <div className="mt-8 rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
            <div className="font-semibold">생성 실패</div>
            <pre className="mt-1 whitespace-pre-wrap break-all font-mono text-xs">{job.error ?? "원인 미상"}</pre>
          </div>
        )}

        {(job.status === "review" || job.status === "done") && (
          <DraftEditor
            jobId={job.id}
            initialDraft={job.draft ?? ""}
            done={job.status === "done"}
            seo={meta?.seo ?? null}
            copyright={meta?.copyright ?? null}
            sources={job.sources}
          />
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 2: client 에디터 작성**

`apps/portal/src/app/(authed)/content/[id]/DraftEditor.tsx`:

```tsx
// 초안 검토·편집 client — PATCH /api/content/jobs/:id (draft 저장 / done 표시).
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

interface Props {
  jobId: string;
  initialDraft: string;
  done: boolean;
  seo: unknown;
  copyright: unknown;
  sources: Array<{ id: string; url: string | null; title: string | null; note: string | null }>;
}

export function DraftEditor({ jobId, initialDraft, done, seo, copyright, sources }: Props) {
  const router = useRouter();
  const [draft, setDraft] = useState(initialDraft);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function patch(body: Record<string, unknown>) {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}`, {
        method: "PATCH",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) { setMsg(`저장 실패 ${res.status}`); return; }
      setMsg("저장됨");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-8 space-y-6">
      {(seo != null || copyright != null) && (
        <div className="flex flex-wrap gap-2 text-xs">
          {seo != null && <span className="rounded-full border border-popory-border px-2 py-0.5 text-popory-muted">SEO: {JSON.stringify(seo)}</span>}
          {copyright != null && <span className="rounded-full border border-popory-border px-2 py-0.5 text-popory-muted">저작권: {JSON.stringify(copyright)}</span>}
        </div>
      )}

      <div>
        <span className="block text-xs font-semibold text-popory-muted mb-1">초안 (네이버 블로그에 붙여넣기)</span>
        <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={28}
          className="w-full rounded-md border border-popory-border bg-popory-card p-3 font-mono text-xs leading-relaxed text-popory-fg" />
      </div>

      {sources.length > 0 && (
        <div>
          <span className="block text-xs font-semibold text-popory-muted mb-1">출처</span>
          <ul className="space-y-1 text-xs text-popory-muted">
            {sources.map((s) => (
              <li key={s.id}>
                {s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-popory-accent">{s.title || s.url}</a> : (s.title || s.note)}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center gap-3">
        <button onClick={() => patch({ draft })} disabled={busy}
          className="rounded-md border border-popory-border px-4 py-2 text-sm disabled:opacity-50">초안 저장</button>
        <button onClick={() => navigator.clipboard.writeText(draft)} type="button"
          className="rounded-md border border-popory-border px-4 py-2 text-sm">복사</button>
        {!done && (
          <button onClick={() => patch({ draft, status: "done" })} disabled={busy}
            className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">완료 표시</button>
        )}
        {done && <span className="text-sm text-popory-muted">완료됨</span>}
        {msg && <span className="text-xs text-popory-muted">{msg}</span>}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 타입체크 + 빌드**

Run: `pnpm --filter @popory/portal typecheck && pnpm --filter @popory/portal build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add "apps/portal/src/app/(authed)/content/[id]"
git commit -m "feat(portal): 작업 상세·초안 에디터"
```

---

## Task 4: 스타일 프로필 페이지

**Files:**
- Create: `apps/portal/src/app/(authed)/content/styles/page.tsx`
- Create: `apps/portal/src/app/(authed)/content/styles/new/page.tsx`
- Create: `apps/portal/src/app/(authed)/content/styles/new/StyleProfileForm.tsx`

- [ ] **Step 1: 목록 페이지**

`apps/portal/src/app/(authed)/content/styles/page.tsx`:

```tsx
// 스타일 프로필 목록 — GET /api/content/style-profiles.
import { redirect } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface Profile { id: string; name: string; sample_count: number; }

export default async function StylesPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/content/style-profiles`, { headers: { cookie }, cache: "no-store" });
  const profiles: Profile[] = res.ok ? ((await res.json()) as { profiles: Profile[] }).profiles : [];

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-2xl px-4 py-10">
        <Kicker>스타일 프로필</Kicker>
        <div className="mt-3 flex items-baseline gap-3">
          <h1 className="font-serif text-3xl font-semibold tracking-tight text-popory-fg">내 글 스타일</h1>
          <Link href="/content/styles/new" className="ml-auto text-sm font-medium text-popory-accent">+ 새 프로필</Link>
        </div>
        <p className="mt-2 text-sm text-popory-muted">내 글 샘플을 모아두면 그 톤으로 초안을 생성합니다.</p>
        {profiles.length === 0 ? (
          <p className="mt-10 text-sm text-popory-muted">아직 프로필이 없습니다.</p>
        ) : (
          <ul className="mt-8 divide-y divide-popory-border">
            {profiles.map((p) => (
              <li key={p.id} className="flex items-center gap-3 py-3">
                <span className="flex-1 text-sm text-popory-fg">{p.name}</span>
                <span className="text-xs text-popory-muted">샘플 {p.sample_count}개</span>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 2: 생성 셸 + client 폼**

`apps/portal/src/app/(authed)/content/styles/new/page.tsx`:

```tsx
// 스타일 프로필 생성 셸.
import { redirect } from "next/navigation";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { StyleProfileForm } from "./StyleProfileForm";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default async function NewStylePage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-2xl px-4 py-10">
        <Kicker>새 스타일 프로필</Kicker>
        <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">내 글 샘플 등록</h1>
        <p className="mt-2 text-sm text-popory-muted">기존 글 1~10편을 붙여넣으세요. 많을수록 톤이 잘 잡힙니다.</p>
        <StyleProfileForm />
      </main>
    </div>
  );
}
```

`apps/portal/src/app/(authed)/content/styles/new/StyleProfileForm.tsx`:

```tsx
// 스타일 프로필 생성 client — 샘플 1~10개. POST /api/content/style-profiles.
"use client";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

const INPUT = "w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg";

export function StyleProfileForm() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [samples, setSamples] = useState<string[]>([""]);

  function updateSample(i: number, v: string) { setSamples((s) => s.map((row, idx) => (idx === i ? v : row))); }
  function addSample() { setSamples((s) => (s.length < 10 ? [...s, ""] : s)); }
  function removeSample(i: number) { setSamples((s) => s.filter((_, idx) => idx !== i)); }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    try {
      const clean = samples.map((s) => s.trim()).filter((s) => s.length > 0);
      if (clean.length === 0) { setErr("샘플을 1개 이상 입력하세요."); setSubmitting(false); return; }
      const res = await fetch(`${API_BASE}/api/content/style-profiles`, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, samples: clean }),
      });
      if (!res.ok) { setErr(`worker-${res.status}: ${(await res.text()).slice(0, 300)}`); setSubmitting(false); return; }
      startTransition(() => { router.push("/content/styles"); router.refresh(); });
    } catch (e) {
      setErr(`fetch: ${String(e).slice(0, 200)}`);
      setSubmitting(false);
    }
  }

  const busy = pending || submitting;

  return (
    <form onSubmit={onSubmit} className="mt-6 space-y-4">
      {err && (
        <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          <pre className="whitespace-pre-wrap break-all font-mono text-xs">{err}</pre>
        </div>
      )}
      <label className="block">
        <span className="block text-xs font-semibold text-popory-muted mb-1">프로필 이름</span>
        <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={100}
          placeholder="예. 내 블로그 톤" className={INPUT} />
      </label>

      <div className="space-y-3">
        {samples.map((s, i) => (
          <div key={i}>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-popory-muted">샘플 {i + 1}</span>
              {samples.length > 1 && <button type="button" onClick={() => removeSample(i)} className="text-xs text-popory-muted">삭제</button>}
            </div>
            <textarea value={s} onChange={(e) => updateSample(i, e.target.value)} rows={6}
              placeholder="기존 글 본문을 붙여넣으세요" maxLength={20000}
              className="mt-1 w-full rounded-md border border-popory-border bg-popory-card p-3 text-sm text-popory-fg" />
          </div>
        ))}
        {samples.length < 10 && <button type="button" onClick={addSample} className="text-xs text-popory-accent">+ 샘플 추가</button>}
      </div>

      <div className="flex gap-3">
        <button type="submit" disabled={busy}
          className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          {busy ? "저장 중…" : "프로필 저장"}
        </button>
        <a href="/content/styles" className="rounded-md border border-popory-border px-4 py-2 text-sm">취소</a>
      </div>
    </form>
  );
}
```

- [ ] **Step 3: 타입체크 + 빌드**

Run: `pnpm --filter @popory/portal typecheck && pnpm --filter @popory/portal build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add "apps/portal/src/app/(authed)/content/styles"
git commit -m "feat(portal): 스타일 프로필 목록·생성"
```

---

## Task 5: 대시보드 카드 교정

**Files:**
- Modify: `apps/portal/src/app/(authed)/dashboard/page.tsx`

- [ ] **Step 1: content 카드 href 를 내부 페이지로 변경**

`apps/portal/src/app/(authed)/dashboard/page.tsx`의 `AREAS` 배열에서 content 줄을 교체한다.

변경 전:
```tsx
  { key: "content", label: "컨텐츠 관리", href: (b) => `${b}/go/content` },
```
변경 후:
```tsx
  { key: "content", label: "컨텐츠 관리", href: () => "/content" },
```

`href`의 인자 `b`(apiBase)를 더 이상 쓰지 않으므로 `() =>` 로 바꾼다. 다른 줄은 건드리지 않는다(규칙 3 외과적 변경).

- [ ] **Step 2: 빌드 검증**

Run: `pnpm --filter @popory/portal build`
Expected: PASS. 대시보드 "컨텐츠 관리" 카드가 `/content` 내부 라우트로 연결됨.

- [ ] **Step 3: Commit**

```bash
git add "apps/portal/src/app/(authed)/dashboard/page.tsx"
git commit -m "fix(portal): 대시보드 컨텐츠 카드를 /content 내부 페이지로 연결"
```

---

## Task 6: 최종 검증

**Files:** 없음

- [ ] **Step 1: 포털 전체 타입체크 + 빌드**

Run: `pnpm --filter @popory/portal typecheck && pnpm --filter @popory/portal build`
Expected: 둘 다 PASS.

- [ ] **Step 2: (선택) prod 배포**

기존 portal 배포 절차(`docs/runbook/deploy-portal.md`)를 따른다. 배포 후 로그인 → 대시보드 "컨텐츠 관리" → `/content` 진입 → 새 작업 생성 시 목록에 "대기 중"으로 뜨는지 확인(워커가 없으면 queued 유지가 정상 — Phase C에서 처리).

---

## Self-Review (작성자 체크)

**Spec coverage:**
- §8 포털: 작업 목록(Task 1)·새 작업 폼 주제·시드 링크·스타일 선택(Task 2)·작업 상세=초안 에디터 검토·편집·복사(Task 3)·스타일 프로필 설정 샘플 10개(Task 4). ✅
- §4 대시보드 카드 `/content` 교정 → Task 5. ✅
- 기존 어드민 폼·Ledger 톤 재사용(`popory-*` 토큰·`NewForm.tsx` 패턴) → 전 태스크. ✅
- 상태별 렌더(queued/running/review/done/failed) → Task 1 라벨 + Task 3 분기. ✅

**Placeholder scan:** 모든 페이지·폼 실제 TSX 포함. "TBD"/"적절히" 없음. Task 1 Step 2에 `Header`/`Kicker` import 경로가 안 맞을 경우의 대응을 명시(추측 금지). ✅

**Type consistency:** API 응답 형태가 Phase A와 일치 — `{ jobs }`(목록)·`{ id }`(생성)·작업 상세의 `draft`/`meta_json`/`sources`/`error`·`{ profiles }`(스타일). 폼 POST 바디(`topic`/`style_profile_id`/`sources[{url,note}]`·`name`/`samples[]`)가 `ContentJobCreateSchema`·`StyleProfileCreateSchema`와 일치. PATCH 바디(`draft`/`status:"done"`)가 `ContentJobEditSchema`와 일치. ✅
