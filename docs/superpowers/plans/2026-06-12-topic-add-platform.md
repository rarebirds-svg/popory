# 주제 상세에서 플랫폼 추가 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 주제 상세 페이지(`/content/topics/[id]`)에서 아직 만들어지지 않은 컨텐츠 유형(플랫폼)을 추가할 수 있게 한다. 추가 작업은 `idle`로 생성되어 기존 "생성 시작" 흐름으로 돌린다.

**Architecture:** 신규 API `POST /api/content/topics/:id/jobs`가 주제 owner를 확인하고, 이미 있는 플랫폼은 skip하며 없는 것만 `idle` 작업으로 추가한다. 포털 상세 페이지에 자체 구현 `AddPlatformForm`을 두어 생성 폼과 동일한 플랫폼/옵션 UI를 재현하되 이미 있는 유형은 비활성화한다.

**Tech Stack:** Cloudflare Workers(Hono) + D1, Zod(@popory/types), Next.js 14 App Router(edge), Vitest(@cloudflare/vitest-pool-workers).

---

## File Structure

| 파일 | 책임 | 생성/수정 |
|---|---|---|
| `packages/types/src/content_job.ts` | `TopicAddJobsSchema` 추가 | 수정 |
| `workers/api/src/routes/content_topics.ts` | `POST /:id/jobs` 엔드포인트 | 수정 |
| `workers/api/src/routes/content_topics.test.ts` | 추가·skip·격리·검증 테스트 | 수정 |
| `apps/portal/src/app/(authed)/content/topics/[id]/AddPlatformForm.tsx` | 유형 추가 폼 | 생성 |
| `apps/portal/src/app/(authed)/content/topics/[id]/page.tsx` | 프로필 fetch + 폼 렌더 | 수정 |

작업 플랫폼은 4종: `naver-blog`, `youtube`, `shorts`, `instagram-image`. 생성 폼 UI의 "유튜브 쇼츠"·"인스타 쇼츠"는 둘 다 `shorts` 플랫폼 1종(`options.upload_targets`로 대상 구분).

---

## Task 1: Zod 스키마 — TopicAddJobsSchema

**Files:**
- Modify: `packages/types/src/content_job.ts`

- [ ] **Step 1: 스키마 추가**

`packages/types/src/content_job.ts` 파일 끝(기존 `TopicCreateSchema`/`TopicPlatformSchema` 정의 아래)에 추가:

```typescript
export const TopicAddJobsSchema = z.object({
  platforms: z.array(TopicPlatformSchema).min(1).max(5),
  style_profile_id: z.string().max(64).optional(),
});
export type TopicAddJobs = z.infer<typeof TopicAddJobsSchema>;
```

(`TopicPlatformSchema`는 같은 파일에 이미 정의돼 있으므로 추가 import 불필요. `@popory/types`의 `index.ts`는 이미 `export * from "./content_job"` 이므로 별도 export 수정 불필요 — 확인만.)

- [ ] **Step 2: 타입 빌드 검증**

Run: `cd /Users/daegong/projects/popory/packages/types && npx tsc --noEmit`
Expected: 에러 없음(exit 0).

- [ ] **Step 3: Commit**

```bash
cd /Users/daegong/projects/popory && git add packages/types/src/content_job.ts && git commit -m "feat(types): 주제 플랫폼 추가 요청 스키마(TopicAddJobs)"
```

---

## Task 2: API — POST /api/content/topics/:id/jobs (TDD)

**Files:**
- Modify: `workers/api/src/routes/content_topics.ts`
- Modify: `workers/api/src/routes/content_topics.test.ts`

기존 `content_topics.ts`는 `import { TopicCreateSchema } from "@popory/types"` 와 `ulid()` 헬퍼, `requireAuth`를 쓴다. 테스트는 `userCookie` 헬퍼와 `beforeEach`(content_jobs/content_topics/content_recommendations DELETE)가 있다.

- [ ] **Step 1: 실패 테스트 추가**

`content_topics.test.ts` 파일 끝에 새 describe 블록 추가:

```typescript
describe("POST /api/content/topics/:id/jobs", () => {
  async function makeTopic(ck: string, platforms: object[]) {
    const r = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "추가테스트주제", platforms }),
    });
    return (await r.json<{ topic_id: string }>()).topic_id;
  }

  it("없는 플랫폼을 idle 작업으로 추가한다", async () => {
    const ck = await userCookie();
    const topicId = await makeTopic(ck, [{ platform: "naver-blog" }]);
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topicId}/jobs`, {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ platforms: [{ platform: "youtube", options: { length: "5", voice: "male", image_style: "photo" } }] }),
    });
    expect(res.status).toBe(201);
    const out = await res.json<{ added_job_ids: string[]; skipped_platforms: string[] }>();
    expect(out.added_job_ids).toHaveLength(1);
    expect(out.skipped_platforms).toEqual([]);
    const job = await env.DB.prepare("SELECT platform, status, topic_id, params_json FROM content_jobs WHERE id=?").bind(out.added_job_ids[0]).first<{ platform: string; status: string; topic_id: string; params_json: string }>();
    expect(job?.platform).toBe("youtube");
    expect(job?.status).toBe("idle");
    expect(job?.topic_id).toBe(topicId);
    expect(JSON.parse(job!.params_json).length).toBe("5");
  });

  it("이미 있는 플랫폼은 skip한다", async () => {
    const ck = await userCookie();
    const topicId = await makeTopic(ck, [{ platform: "naver-blog" }]);
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topicId}/jobs`, {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ platforms: [{ platform: "naver-blog" }, { platform: "shorts" }] }),
    });
    const out = await res.json<{ added_job_ids: string[]; skipped_platforms: string[] }>();
    expect(out.added_job_ids).toHaveLength(1); // shorts만 추가
    expect(out.skipped_platforms).toEqual(["naver-blog"]);
    const { results } = await env.DB.prepare("SELECT platform FROM content_jobs WHERE topic_id=? ORDER BY platform").bind(topicId).all<{ platform: string }>();
    expect(results.map((r) => r.platform).sort()).toEqual(["naver-blog", "shorts"]);
  });

  it("타인 주제에 추가하면 404", async () => {
    const ck1 = await userCookie("u1", "u1@e.com");
    const topicId = await makeTopic(ck1, [{ platform: "naver-blog" }]);
    const ck2 = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topicId}/jobs`, {
      method: "POST", headers: { cookie: ck2, "content-type": "application/json" },
      body: JSON.stringify({ platforms: [{ platform: "youtube" }] }),
    });
    expect(res.status).toBe(404);
  });

  it("빈 platforms는 400", async () => {
    const ck = await userCookie();
    const topicId = await makeTopic(ck, [{ platform: "naver-blog" }]);
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topicId}/jobs`, {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ platforms: [] }),
    });
    expect(res.status).toBe(400);
  });

  it("존재하지 않는 style_profile_id는 404", async () => {
    const ck = await userCookie();
    const topicId = await makeTopic(ck, [{ platform: "naver-blog" }]);
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topicId}/jobs`, {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ platforms: [{ platform: "youtube" }], style_profile_id: "nope" }),
    });
    expect(res.status).toBe(404);
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/workers/api && npx vitest run src/routes/content_topics.test.ts`
Expected: 신규 테스트 FAIL — 404(엔드포인트 미존재) 또는 라우트 없음으로 assert 실패.

- [ ] **Step 3: 엔드포인트 구현**

`content_topics.ts`의 import에서 `TopicCreateSchema`를 가져오는 줄에 `TopicAddJobsSchema`를 추가:

```typescript
import { TopicCreateSchema, TopicAddJobsSchema } from "@popory/types";
```

`mountContentTopics(app)` 안의 `app.get("/api/content/topics/:id", ...)` 핸들러 **뒤**(닫는 `});` 다음, 함수 닫기 `}` 전)에 추가:

```typescript
  app.post("/api/content/topics/:id/jobs", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const topicId = c.req.param("id");
    const topic = await c.env.DB.prepare("SELECT id, owner_sub, topic FROM content_topics WHERE id=?")
      .bind(topicId).first<{ id: string; owner_sub: string; topic: string }>();
    if (!topic || topic.owner_sub !== u.sub) return c.text("not found", 404);
    const parsed = TopicAddJobsSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const { platforms, style_profile_id } = parsed.data;
    if (style_profile_id) {
      const sp = await c.env.DB.prepare("SELECT id FROM style_profiles WHERE id=? AND owner_sub=?")
        .bind(style_profile_id, u.sub).first();
      if (!sp) return c.text("style profile not found", 404);
    }
    const { results: existing } = await c.env.DB.prepare(
      "SELECT DISTINCT platform FROM content_jobs WHERE topic_id=?",
    ).bind(topicId).all<{ platform: string }>();
    const present = new Set(existing.map((r) => r.platform));
    const now = Math.floor(Date.now() / 1000);
    const stmts = [];
    const addedJobIds: string[] = [];
    const skippedPlatforms: string[] = [];
    for (const p of platforms) {
      if (present.has(p.platform)) { skippedPlatforms.push(p.platform); continue; }
      present.add(p.platform); // 같은 요청 내 중복도 1회만
      const jobId = ulid();
      const paramsJson = p.options ? JSON.stringify(p.options) : null;
      stmts.push(
        c.env.DB.prepare(
          `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, topic_id, created_at, updated_at)
           VALUES (?,?,?,?,'idle',?,?,?,?,?)`,
        ).bind(jobId, u.sub, topic.topic, p.platform, style_profile_id ?? null, paramsJson, topicId, now, now),
      );
      addedJobIds.push(jobId);
    }
    if (stmts.length > 0) await c.env.DB.batch(stmts);
    return c.json({ added_job_ids: addedJobIds, skipped_platforms: skippedPlatforms }, 201);
  });
```

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/workers/api && npx vitest run src/routes/content_topics.test.ts`
Expected: PASS (신규 4개 포함 전체 green).

- [ ] **Step 5: 전체 회귀**

Run: `cd /Users/daegong/projects/popory/workers/api && npx vitest run`
Expected: 전체 PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/daegong/projects/popory && git add workers/api/src/routes/content_topics.ts workers/api/src/routes/content_topics.test.ts && git commit -m "feat(api): 주제에 누락 플랫폼 작업 추가 엔드포인트"
```

---

## Task 3: 포털 — AddPlatformForm 컴포넌트

**Files:**
- Create: `apps/portal/src/app/(authed)/content/topics/[id]/AddPlatformForm.tsx`

생성 폼(`NewJobForm.tsx`)의 플랫폼 체크박스·옵션 패널·제출 변환 규칙을 자체 구현으로 재현하되, 주제·sources 입력은 없고 `existingPlatforms`로 비활성화한다. 제출 대상은 `POST /api/content/topics/:id/jobs`.

- [ ] **Step 1: 컴포넌트 작성**

`apps/portal/src/app/(authed)/content/topics/[id]/AddPlatformForm.tsx`:

```tsx
"use client";
// 주제 상세에서 아직 없는 컨텐츠 유형(플랫폼)을 추가하는 폼.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

const INPUT = "w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg";
const CHECK_LABEL = "flex items-center gap-2 cursor-pointer text-sm text-popory-fg";
const CHECK_DISABLED = "flex items-center gap-2 text-sm text-popory-muted opacity-50";

interface StyleProfile { id: string; name: string; }

export function AddPlatformForm({ topicId, existingPlatforms, profiles }: {
  topicId: string; existingPlatforms: string[]; profiles: StyleProfile[];
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const present = new Set(existingPlatforms);
  const naverDisabled = present.has("naver-blog");
  const youtubeDisabled = present.has("youtube");
  const shortsDisabled = present.has("shorts");
  const instaImageDisabled = present.has("instagram-image");
  const allPresent = naverDisabled && youtubeDisabled && shortsDisabled && instaImageDisabled;

  const [styleId, setStyleId] = useState("");
  const [naverBlog, setNaverBlog] = useState(false);
  const [youtube, setYoutube] = useState(false);
  const [youtubeShorts, setYoutubeShorts] = useState(false);
  const [instaShorts, setInstaShorts] = useState(false);
  const [instaImage, setInstaImage] = useState(false);

  const [ytLength, setYtLength] = useState<"3"|"5"|"7"|"10">("5");
  const [ytVoice, setYtVoice] = useState<"female-calm"|"female-bright"|"male">("female-calm");
  const [ytStyle, setYtStyle] = useState<"photo"|"illust"|"watercolor"|"minimal">("photo");
  const [shLength, setShLength] = useState<"15"|"30"|"60">("30");
  const [shVoice, setShVoice] = useState<"female-calm"|"female-bright"|"male">("female-calm");
  const [shStyle, setShStyle] = useState<"photo"|"illust"|"watercolor"|"minimal">("photo");
  const [slideCount, setSlideCount] = useState(7);

  const showShorts = youtubeShorts || instaShorts;
  const noneSelected = !naverBlog && !youtube && !youtubeShorts && !instaShorts && !instaImage;

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (noneSelected) { setErr("하나 이상의 유형을 선택하세요."); return; }
    setErr(null);
    setSubmitting(true);
    try {
      const platforms: Array<{ platform: string; options?: object }> = [];
      if (naverBlog) platforms.push({ platform: "naver-blog" });
      if (youtube) platforms.push({ platform: "youtube", options: { length: ytLength, voice: ytVoice, image_style: ytStyle } });
      if (showShorts) {
        const targets: string[] = [];
        if (youtubeShorts) targets.push("youtube");
        if (instaShorts) targets.push("instagram");
        platforms.push({ platform: "shorts", options: { length: shLength, voice: shVoice, image_style: shStyle, upload_targets: targets } });
      }
      if (instaImage) platforms.push({ platform: "instagram-image", options: { slide_count: slideCount } });

      const res = await fetch(`${API_BASE}/api/content/topics/${topicId}/jobs`, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ platforms, style_profile_id: styleId || undefined }),
      });
      if (!res.ok) { setErr(`오류 ${res.status}: ${(await res.text()).slice(0, 200)}`); return; }
      setNaverBlog(false); setYoutube(false); setYoutubeShorts(false); setInstaShorts(false); setInstaImage(false);
      startTransition(() => router.refresh());
    } catch (e) {
      setErr(`fetch: ${String(e).slice(0, 200)}`);
    } finally {
      setSubmitting(false);
    }
  }

  if (allPresent) {
    return <p className="mt-8 text-sm text-popory-muted">추가할 유형이 없습니다.</p>;
  }

  const busy = pending || submitting;

  return (
    <form onSubmit={onSubmit} className="mt-10 border-t border-popory-border pt-6 space-y-4">
      <p className="text-xs font-semibold text-popory-muted">유형 추가</p>
      {err && (
        <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          <pre className="whitespace-pre-wrap break-all font-mono text-xs">{err}</pre>
        </div>
      )}

      <div className="space-y-2 rounded-md border border-popory-border p-3">
        <label className={naverDisabled ? CHECK_DISABLED : CHECK_LABEL}>
          <input type="checkbox" checked={naverBlog} disabled={naverDisabled} onChange={(e) => setNaverBlog(e.target.checked)} />
          네이버 블로그{naverDisabled && " (이미 있음)"}
        </label>
        <label className={youtubeDisabled ? CHECK_DISABLED : CHECK_LABEL}>
          <input type="checkbox" checked={youtube} disabled={youtubeDisabled} onChange={(e) => setYoutube(e.target.checked)} />
          유튜브 동영상{youtubeDisabled && " (이미 있음)"}
        </label>
        <label className={shortsDisabled ? CHECK_DISABLED : CHECK_LABEL}>
          <input type="checkbox" checked={youtubeShorts} disabled={shortsDisabled} onChange={(e) => setYoutubeShorts(e.target.checked)} />
          유튜브 쇼츠{shortsDisabled && " (이미 있음)"}
        </label>
        <label className={shortsDisabled ? CHECK_DISABLED : CHECK_LABEL}>
          <input type="checkbox" checked={instaShorts} disabled={shortsDisabled} onChange={(e) => setInstaShorts(e.target.checked)} />
          인스타 쇼츠 (릴스){shortsDisabled && " (이미 있음)"}
        </label>
        <label className={instaImageDisabled ? CHECK_DISABLED : CHECK_LABEL}>
          <input type="checkbox" checked={instaImage} disabled={instaImageDisabled} onChange={(e) => setInstaImage(e.target.checked)} />
          인스타 이미지 (캐러셀){instaImageDisabled && " (이미 있음)"}
        </label>
      </div>

      {youtube && (
        <div className="rounded-md border border-popory-border p-3 space-y-3">
          <p className="text-xs font-semibold text-popory-muted">유튜브 동영상 옵션</p>
          <div className="grid grid-cols-3 gap-3">
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">길이</span>
              <select value={ytLength} onChange={(e) => setYtLength(e.target.value as typeof ytLength)} className={INPUT}>
                <option value="3">3분</option><option value="5">5분</option><option value="7">7분</option><option value="10">10분</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">목소리</span>
              <select value={ytVoice} onChange={(e) => setYtVoice(e.target.value as typeof ytVoice)} className={INPUT}>
                <option value="female-calm">여성·차분</option><option value="female-bright">여성·밝은</option><option value="male">남성</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">배경</span>
              <select value={ytStyle} onChange={(e) => setYtStyle(e.target.value as typeof ytStyle)} className={INPUT}>
                <option value="photo">실사</option><option value="illust">일러스트</option><option value="watercolor">수채화</option><option value="minimal">미니멀</option>
              </select>
            </label>
          </div>
        </div>
      )}

      {showShorts && (
        <div className="rounded-md border border-popory-border p-3 space-y-3">
          <p className="text-xs font-semibold text-popory-muted">
            쇼츠 옵션 ({[youtubeShorts && "유튜브 쇼츠", instaShorts && "인스타 쇼츠"].filter(Boolean).join(" + ")})
          </p>
          <div className="grid grid-cols-3 gap-3">
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">길이</span>
              <select value={shLength} onChange={(e) => setShLength(e.target.value as typeof shLength)} className={INPUT}>
                <option value="15">15초</option><option value="30">30초</option><option value="60">60초</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">목소리</span>
              <select value={shVoice} onChange={(e) => setShVoice(e.target.value as typeof shVoice)} className={INPUT}>
                <option value="female-calm">여성·차분</option><option value="female-bright">여성·밝은</option><option value="male">남성</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">배경</span>
              <select value={shStyle} onChange={(e) => setShStyle(e.target.value as typeof shStyle)} className={INPUT}>
                <option value="photo">실사</option><option value="illust">일러스트</option><option value="watercolor">수채화</option><option value="minimal">미니멀</option>
              </select>
            </label>
          </div>
        </div>
      )}

      {instaImage && (
        <div className="rounded-md border border-popory-border p-3">
          <p className="text-xs font-semibold text-popory-muted mb-2">인스타 이미지 옵션</p>
          <label className="block">
            <span className="block text-xs text-popory-muted mb-1">슬라이드 수 ({slideCount}장)</span>
            <input type="range" min={3} max={10} value={slideCount} onChange={(e) => setSlideCount(Number(e.target.value))} className="w-full" />
          </label>
        </div>
      )}

      <label className="block">
        <span className="block text-xs font-semibold text-popory-muted mb-1">스타일 프로필 (선택)</span>
        <select value={styleId} onChange={(e) => setStyleId(e.target.value)} className={INPUT}>
          <option value="">(기본 톤)</option>
          {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>

      <button type="submit" disabled={busy || noneSelected}
        className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
        {busy ? "추가 중…" : "선택한 유형 추가"}
      </button>
    </form>
  );
}
```

- [ ] **Step 2: 타입체크**

Run: `cd /Users/daegong/projects/popory/apps/portal && npx tsc --noEmit`
Expected: 에러 없음. (실패 시 import 경로·prop 타입 수정.)

- [ ] **Step 3: Commit**

```bash
cd /Users/daegong/projects/popory && git add "apps/portal/src/app/(authed)/content/topics/[id]/AddPlatformForm.tsx" && git commit -m "feat(portal): 주제 상세 유형 추가 폼 컴포넌트"
```

---

## Task 4: 상세 페이지에 폼 연결

**Files:**
- Modify: `apps/portal/src/app/(authed)/content/topics/[id]/page.tsx`

- [ ] **Step 1: import + 프로필 fetch + 렌더 추가**

`page.tsx` 수정:

1) import 추가(파일 상단 import 블록):

```tsx
import { AddPlatformForm } from "./AddPlatformForm";
```

2) 프로필 fetch 헬퍼 추가(`TopicDetailPage` 함수 위, 다른 인터페이스/상수 근처):

```tsx
async function fetchProfiles(cookie: string): Promise<{ id: string; name: string }[]> {
  const res = await fetch(`${API_BASE}/api/content/style-profiles`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  return ((await res.json()) as { profiles: { id: string; name: string }[] }).profiles;
}
```

3) 컴포넌트 본문에서 topic fetch 직후 프로필도 fetch. 기존:

```tsx
  const topic = (await res.json()) as TopicDetail;

  const hasActive = topic.jobs.some((j) => j.status === "queued" || j.status === "running");
```

를 다음으로 변경(프로필 fetch 추가):

```tsx
  const topic = (await res.json()) as TopicDetail;
  const profiles = await fetchProfiles(cookie);

  const hasActive = topic.jobs.some((j) => j.status === "queued" || j.status === "running");
```

4) 작업 그리드 `</div>`(`{topic.jobs.map(...)}`를 감싼 `<div className="mt-8 grid ...">`의 닫기) **다음**, `</main>` 전에 폼 렌더 추가:

```tsx
        <AddPlatformForm
          topicId={topic.id}
          existingPlatforms={topic.jobs.map((j) => j.platform)}
          profiles={profiles}
        />
```

- [ ] **Step 2: 타입체크**

Run: `cd /Users/daegong/projects/popory/apps/portal && npx tsc --noEmit`
Expected: 에러 없음.

- [ ] **Step 3: Commit**

```bash
cd /Users/daegong/projects/popory && git add "apps/portal/src/app/(authed)/content/topics/[id]/page.tsx" && git commit -m "feat(portal): 주제 상세에 유형 추가 폼 연결"
```

---

## 마무리

- [ ] **전체 회귀**: `cd workers/api && npx vitest run`(전체 green), `cd packages/types && npx tsc --noEmit`, `cd apps/portal && npx tsc --noEmit`.
- [ ] **배포(머지 후)**: API `npx wrangler deploy --config infra/wrangler/api.toml --env prod`, 포털 `pnpm --filter @popory/portal build:cf` → `npx wrangler pages deploy apps/portal/.vercel/output/static --project-name popory-portal --branch main`.
- [ ] **수동 확인**: 주제 상세에서 빠진 유형 추가 → 카드 생성(idle) → "생성 시작" 동작. 이미 있는 유형은 "(이미 있음)" 비활성. 모두 있으면 "추가할 유형이 없습니다".
