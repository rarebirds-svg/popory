<!-- portal admin · brief 카테고리 「추가」 기능 implementation plan. -->
# admin · brief 카테고리 「추가」 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** portal `/admin/brief-categories/new` 폼에서 신규 brief 카테고리를 만들고 GitHub에 새 SKILL.md 파일을 commit한다. launchd가 매일 git pull로 자동 발견.

**Architecture:** 기존 spec (2026-05-31-popory-admin-brief-categories-design.md)의 amendment. `POST /api/admin/brief-categories` 라우트 신설 + portal client-side 폼 신규 + 목록 페이지 링크 1줄. GitHub Contents API PUT을 sha 없이 호출하여 새 파일 create. server-side에서 slug 중복은 사전 getFile로, 예약어 `new`는 validateFields로 차단.

**Tech Stack:** Cloudflare Workers + Hono · vitest (`cloudflare:test`) · Next.js 15 client component · GitHub Contents API REST

**Reference spec:** [docs/superpowers/specs/2026-05-31-popory-admin-brief-categories-add-amendment.md](../specs/2026-05-31-popory-admin-brief-categories-add-amendment.md)

---

## File Map

**Create**
- `apps/portal/src/app/admin/brief-categories/new/page.tsx` — server component (헤더만), client form 호스트
- `apps/portal/src/app/admin/brief-categories/new/NewForm.tsx` — client component 신규 폼

**Modify**
- `workers/api/src/lib/skill_md.ts` — `RESERVED_SLUGS` 상수 추가, `validateFields`에 예약어 검사
- `workers/api/src/lib/skill_md.test.ts` — 예약어 `new` 거부 테스트 1건
- `workers/api/src/lib/github_contents.ts` — `PutFileInput.sha?: string` (optional), `putFile` 내부에서 sha 없으면 body에 sha 필드 omit
- `workers/api/src/routes/admin_brief_categories.ts` — `POST /api/admin/brief-categories` 핸들러 추가
- `workers/api/src/routes/admin_brief_categories.test.ts` — POST 4건 추가 (정상·slug 중복·validate 실패·비admin)
- `apps/portal/src/app/admin/brief-categories/page.tsx` — `+ 새 카테고리` 링크 1줄

---

## Task 1: skill_md.ts 예약어 + github_contents.ts sha optional

**Files:**
- Modify: `workers/api/src/lib/skill_md.ts`
- Modify: `workers/api/src/lib/skill_md.test.ts`
- Modify: `workers/api/src/lib/github_contents.ts`

- [ ] **Step 1: skill_md.test.ts에 예약어 거부 테스트 추가 (실패)**

`workers/api/src/lib/skill_md.test.ts`의 `describe("validateFields", ...)` 안 마지막에 추가.

```ts
  it("예약어 slug (new) 거부", () => {
    expect(validateFields({ ...base, slug: "new" })).toContainEqual(
      expect.stringContaining("예약어"),
    );
  });
```

- [ ] **Step 2: 테스트 실행 → 실패**

```bash
cd /Users/daegong/projects/popory/workers/api
pnpm test 2>&1 | tail -10
```

기대 출력. `예약어` 매칭 실패로 1건 FAIL.

- [ ] **Step 3: skill_md.ts에 RESERVED_SLUGS + validateFields 검사 추가**

`workers/api/src/lib/skill_md.ts` 의 상수 부분 (`SLUG_RE` 옆) 한 줄 추가.

```ts
const RESERVED_SLUGS = new Set(["new"]); // /admin/brief-categories/new 정적 라우트 충돌 회피
```

`validateFields` 함수 안 `if (!SLUG_RE.test(f.slug))` 직후에 한 줄 추가.

```ts
export function validateFields(f: SkillFields): string[] {
  const errs: string[] = [];
  if (!SLUG_RE.test(f.slug)) errs.push(`slug 규칙 위반 (^[a-z][a-z0-9-]{1,30}$)`);
  if (RESERVED_SLUGS.has(f.slug)) errs.push(`slug "${f.slug}"는 예약어 (사용 불가)`);
  if (!VALID_MODES.has(f.delivery_mode)) errs.push(`delivery_mode 화이트리스트 위반 (standalone|bundled)`);
  if (!f.name.trim()) errs.push("name 비어있음");
  if (!f.subject_template.trim()) errs.push("subject_template 비어있음");
  if (!f.sender_name.trim()) errs.push("sender_name 비어있음");
  return errs;
}
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
pnpm test --run src/lib/skill_md.test.ts 2>&1 | tail -10
```

기대 출력. 13 passed (이전 12 + 신규 1).

- [ ] **Step 5: github_contents.ts sha optional 변경**

`workers/api/src/lib/github_contents.ts` 의 `PutFileInput` interface 수정.

```ts
export interface PutFileInput {
  path: string;
  message: string;
  contentText: string;
  sha?: string;          // optional. 없으면 새 파일 create
  actorEmail: string;
}
```

`putFile` 함수 body 직렬화 부분 수정. 기존.

```ts
  const body = JSON.stringify({
    message: input.message,
    content: contentB64,
    sha: input.sha,
    branch: BRANCH,
    committer: { name: "popory-portal-admin", email: "noreply@popory.local" },
    author: { name: "popory-portal-admin", email: "noreply@popory.local" },
  });
```

변경.

```ts
  const bodyObj: Record<string, unknown> = {
    message: input.message,
    content: contentB64,
    branch: BRANCH,
    committer: { name: "popory-portal-admin", email: "noreply@popory.local" },
    author: { name: "popory-portal-admin", email: "noreply@popory.local" },
  };
  if (input.sha) bodyObj.sha = input.sha;
  const body = JSON.stringify(bodyObj);
```

- [ ] **Step 6: 회귀 확인**

```bash
pnpm test 2>&1 | tail -5
```

기대 출력. 모든 기존 테스트 + 신규 PASS (45 + 1 = 46).

- [ ] **Step 7: commit**

```bash
cd /Users/daegong/projects/popory
git add workers/api/src/lib/skill_md.ts \
        workers/api/src/lib/skill_md.test.ts \
        workers/api/src/lib/github_contents.ts
git commit -m "$(cat <<'EOF'
feat(api): skill_md 예약어 new + github_contents putFile sha optional

신규 카테고리 추가 기능 위해 (1) skill_md validateFields에 RESERVED_SLUGS={"new"} 검사 추가 (정적 라우트 충돌 회피). (2) github_contents PutFileInput.sha optional 변경 — sha 없으면 PUT body에서 omit하여 새 파일 create 동작.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: POST /api/admin/brief-categories 라우트 + 단위 테스트

**Files:**
- Modify: `workers/api/src/routes/admin_brief_categories.ts`
- Modify: `workers/api/src/routes/admin_brief_categories.test.ts`

- [ ] **Step 1: 실패 테스트 4건 추가**

`workers/api/src/routes/admin_brief_categories.test.ts` 의 `describe("admin_brief_categories", ...)` 안 마지막에 4건 추가.

```ts
  it("POST 정상 — 신규 slug 생성, getFile 404 후 putFile create", async () => {
    let putBody: any = null;
    mockGithub({
      "contents/services/brief/categories/newcat/SKILL.md?ref=main": () =>
        new Response(JSON.stringify({ message: "Not Found" }), { status: 404 }),
      "contents/services/brief/categories/newcat/SKILL.md": async (req) => {
        if (req.method === "PUT") {
          putBody = await req.json();
          return new Response(JSON.stringify({ content: { sha: "f_new" } }), { status: 201 });
        }
        return new Response(JSON.stringify({ message: "Not Found" }), { status: 404 });
      },
    });
    const ck = await makeAdminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/brief-categories", {
      method: "POST",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({
        fields: { slug: "newcat", name: "신규", delivery_mode: "bundled", subject_template: "[{name}] {date}", sender_name: "{name}", enabled: false },
        body: "신규 카테고리 본문.\n",
      }),
    });
    expect(res.status).toBe(200);
    const out = await res.json<{ sha: string }>();
    expect(out.sha).toBe("f_new");
    expect(putBody.message).toContain("create categories/newcat/SKILL.md");
    expect(putBody.message).toContain(ADMIN_EMAIL);
    expect(putBody.sha).toBeUndefined();
  });

  it("POST slug 중복 — getFile 200 → 422", async () => {
    mockGithub({
      "contents/services/brief/categories/realestate/SKILL.md?ref=main": () =>
        Response.json({ content: btoa(unescape(encodeURIComponent(SKILL_REALESTATE))), sha: "f1", path: "services/brief/categories/realestate/SKILL.md" }),
    });
    const ck = await makeAdminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/brief-categories", {
      method: "POST",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({
        fields: { slug: "realestate", name: "x", delivery_mode: "bundled", subject_template: "x", sender_name: "x", enabled: false },
        body: "x\n",
      }),
    });
    expect(res.status).toBe(422);
    const out = await res.json<{ errors: string[] }>();
    expect(out.errors.join(",")).toContain("slug already exists");
  });

  it("POST validate 실패 — 예약어 new → 422", async () => {
    const ck = await makeAdminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/brief-categories", {
      method: "POST",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({
        fields: { slug: "new", name: "x", delivery_mode: "bundled", subject_template: "x", sender_name: "x", enabled: false },
        body: "x\n",
      }),
    });
    expect(res.status).toBe(422);
  });

  it("POST 비admin → 401/403", async () => {
    const ck = await makeMemberCookie();
    const res = await SELF.fetch("https://example.com/api/admin/brief-categories", {
      method: "POST",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({
        fields: { slug: "x1", name: "x", delivery_mode: "bundled", subject_template: "x", sender_name: "x", enabled: false },
        body: "x\n",
      }),
    });
    expect([401, 403]).toContain(res.status);
  });
```

- [ ] **Step 2: 테스트 실행 → 실패 (라우트 없음)**

```bash
cd /Users/daegong/projects/popory/workers/api
pnpm test --run src/routes/admin_brief_categories.test.ts 2>&1 | tail -10
```

기대 출력. 4건 신규 실패 (404 또는 method not allowed).

- [ ] **Step 3: POST 핸들러 구현**

`workers/api/src/routes/admin_brief_categories.ts` 의 `mountAdminBriefCategories` 함수 끝(`}` 직전, PUT 핸들러 다음)에 추가.

```ts
  // POST 단건 — 신규 slug 생성 (sha 없이 putFile = create)
  app.post("/api/admin/brief-categories", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const user = c.get("user")!;
    const token = c.env.BRIEF_CATEGORIES_GITHUB_TOKEN;
    const payload = await c.req.json<{ fields: SkillFields; body: string }>();
    const errs = validateFields(payload.fields);
    if (errs.length > 0) return c.json({ errors: errs }, 422);
    const slug = payload.fields.slug;
    const path = `${CATEGORIES_PATH}/${slug}/SKILL.md`;
    // 중복 검사. getFile 200 = 이미 존재
    try {
      await getFile(token, path);
      return c.json({ errors: ["slug already exists"] }, 422);
    } catch (e) {
      if (!(e instanceof GitHubApiError) || e.status !== 404) {
        if (e instanceof GitHubApiError) return c.text(`github: ${e.message}`, 502);
        throw e;
      }
      // 404 → 진행
    }
    const text = serializeSkillMd({ fields: payload.fields, body: payload.body });
    try {
      const result = await putFile(token, {
        path,
        message: `chore(brief): create categories/${slug}/SKILL.md via portal admin (by ${user.email})`,
        contentText: text,
        actorEmail: user.email,
      });
      return c.json({ sha: result.sha });
    } catch (e) {
      if (e instanceof GitHubApiError) return c.text(`github: ${e.message}`, 502);
      throw e;
    }
  });
```

- [ ] **Step 4: 테스트 실행 → 통과**

```bash
pnpm test --run src/routes/admin_brief_categories.test.ts 2>&1 | tail -10
```

기대 출력. 10건 모두 PASS (기존 6 + 신규 4).

- [ ] **Step 5: 회귀 확인**

```bash
pnpm test 2>&1 | tail -5
```

기대 출력. 모든 기존 + 신규 PASS.

- [ ] **Step 6: commit**

```bash
cd /Users/daegong/projects/popory
git add workers/api/src/routes/admin_brief_categories.ts \
        workers/api/src/routes/admin_brief_categories.test.ts
git commit -m "$(cat <<'EOF'
feat(api): POST /api/admin/brief-categories 신규 카테고리 생성 라우트

validateFields → server-side slug 중복 검사 (getFile 200 → 422 slug already exists) → serializeSkillMd → putFile sha 없이 create. commit message `chore(brief): create categories/{slug}/SKILL.md via portal admin (by {actor_email})`. 4 단위 테스트 (정상·slug 중복·예약어·비admin).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: portal /admin/brief-categories/new 페이지 + NewForm client

**Files:**
- Create: `apps/portal/src/app/admin/brief-categories/new/page.tsx`
- Create: `apps/portal/src/app/admin/brief-categories/new/NewForm.tsx`

- [ ] **Step 1: NewForm.tsx 작성 (client component)**

`apps/portal/src/app/admin/brief-categories/new/NewForm.tsx` 신규. 첫 줄 한국어 헤더.

```tsx
// admin · 신규 brief 카테고리 생성 폼 client component — POST /api/admin/brief-categories.
"use client";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

const INPUT = "w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm";
const SLUG_PATTERN = "[a-z][a-z0-9-]{1,30}";

const DEFAULT_SUBJECT = "[{name} 이슈 브리핑] {date}";
const DEFAULT_SENDER = "{name} 이슈 브리핑";
const BODY_PLACEHOLDER = `system prompt를 작성하세요. 예시 섹션 구성.

## 1. 수집 윈도우 (엄격)
- 기간. 작성일 포함 직전 3일 [작성일-2, 작성일]
- 윈도우 밖 자료는 본문 포함 금지

## 2. 매체 우선순위
**Tier 1 — ...**
**Tier 2 — ...**

## 3. 사법부 모니터링

## 4. 주제 카테고리

## 5. 이슈 선정 기준

## 6. 하위 태그 시스템

## 7. WebFetch 폴백 체인

## 8. 출력 형식 (반드시 마지막 응답에 두 XML 태그를 정확히 포함)

<body_markdown>
...
</body_markdown>

<meta_json>
{"title": "...", "summary": "...", "tags": [...], "published_at": <unix>}
</meta_json>
`;

export function NewForm() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [deliveryMode, setDeliveryMode] = useState<"standalone" | "bundled">("bundled");
  const [subjectTemplate, setSubjectTemplate] = useState(DEFAULT_SUBJECT);
  const [senderName, setSenderName] = useState(DEFAULT_SENDER);
  const [enabled, setEnabled] = useState(false);
  const [body, setBody] = useState("");

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/admin/brief-categories`, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          fields: {
            slug,
            name,
            delivery_mode: deliveryMode,
            subject_template: subjectTemplate,
            sender_name: senderName,
            enabled,
          },
          body,
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        setErr(`worker-${res.status}: ${text.slice(0, 400)}`);
        setSubmitting(false);
        return;
      }
      startTransition(() => {
        router.push("/admin/brief-categories");
        router.refresh();
      });
    } catch (e) {
      setErr(`fetch: ${String(e).slice(0, 300)}`);
      setSubmitting(false);
    }
  }

  const busy = pending || submitting;

  return (
    <form onSubmit={onSubmit} className="mt-6 space-y-4">
      {err && (
        <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          <div className="font-semibold">생성 실패</div>
          <pre className="mt-1 whitespace-pre-wrap break-all font-mono text-xs">{err}</pre>
        </div>
      )}

      <Field label="slug (영문 소문자·숫자·하이픈, 2~31자)">
        <input
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          required
          pattern={SLUG_PATTERN}
          placeholder="예. esg, sanction"
          className={`${INPUT} font-mono`}
        />
      </Field>

      <Field label="이름 (name)">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          placeholder="예. ESG, 제재"
          className={INPUT}
        />
      </Field>

      <Field label="전송 모드 (delivery_mode)">
        <select
          value={deliveryMode}
          onChange={(e) => setDeliveryMode(e.target.value as "standalone" | "bundled")}
          className={INPUT}
        >
          <option value="standalone">standalone (카테고리당 1통)</option>
          <option value="bundled">bundled (수신자별 묶음 1통)</option>
        </select>
      </Field>

      <Field label="제목 템플릿 (subject_template). {name}·{date} placeholder">
        <input value={subjectTemplate} onChange={(e) => setSubjectTemplate(e.target.value)} required className={INPUT} />
      </Field>

      <Field label="발신자 이름 (sender_name). {name} placeholder">
        <input value={senderName} onChange={(e) => setSenderName(e.target.value)} required className={INPUT} />
      </Field>

      <Field label="활성 (enabled)">
        <label className="inline-flex items-center gap-2">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          <span className="text-sm text-popory-muted">본문 완성 전이라면 비활성 권장 (편집 페이지에서 후에 활성화)</span>
        </label>
      </Field>

      <Field label="System prompt (body)">
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={32}
          placeholder={BODY_PLACEHOLDER}
          className="w-full rounded-md border border-popory-border bg-popory-card p-3 font-mono text-xs leading-relaxed"
        />
      </Field>

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "생성 중…" : "생성 (GitHub commit)"}
        </button>
        <a
          href="/admin/brief-categories"
          className="rounded-md border border-popory-border px-4 py-2 text-sm"
        >
          취소
        </a>
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-popory-muted mb-1">{label}</span>
      {children}
    </label>
  );
}
```

- [ ] **Step 2: page.tsx 작성 (server component, NewForm 호스트)**

`apps/portal/src/app/admin/brief-categories/new/page.tsx` 신규.

```tsx
// admin · 신규 brief 카테고리 생성 페이지 — server 헤더 + client NewForm.
import Link from "next/link";
import { NewForm } from "./NewForm";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default function NewCategoryPage() {
  return (
    <main>
      <div className="flex items-baseline gap-3">
        <h1 className="text-xl font-semibold">새 브리핑 카테고리</h1>
        <Link href="/admin/brief-categories" className="ml-auto text-sm text-popory-muted">← 목록</Link>
      </div>
      <p className="mt-2 text-sm text-popory-muted">
        slug는 영문 소문자·숫자·하이픈만 (예. esg, sanction). 저장 시 GitHub의 services/brief/categories/&#123;slug&#125;/SKILL.md 새 파일이 main 브랜치에 commit됨. enabled가 true면 다음 09:00 KST 자동 실행에 포함.
      </p>
      <NewForm />
    </main>
  );
}
```

- [ ] **Step 3: portal build 검증**

```bash
cd /Users/daegong/projects/popory
pnpm --filter @popory/portal build 2>&1 | tail -15
```

기대 출력. `Compiled successfully` + Route 표에 `ƒ /admin/brief-categories/new` 줄 포함.

- [ ] **Step 4: commit**

```bash
git add apps/portal/src/app/admin/brief-categories/new/
git commit -m "$(cat <<'EOF'
feat(portal): /admin/brief-categories/new 신규 카테고리 생성 페이지

NewForm.tsx (client component) + page.tsx (server 헤더 + client form 호스트). slug regex pattern + 폼 7필드 (delivery_mode default bundled, enabled default false). body textarea에 SKILL.md 섹션 구성 placeholder. POST /api/admin/brief-categories 호출 후 목록 redirect.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: portal 목록 페이지 「+ 새 카테고리」 링크

**Files:**
- Modify: `apps/portal/src/app/admin/brief-categories/page.tsx`

- [ ] **Step 1: 헤더 부분에 링크 추가**

`apps/portal/src/app/admin/brief-categories/page.tsx` 의 `<h1>` 라인 주변 변경.

기존.
```tsx
return (
    <main>
      <h1 className="text-xl font-semibold">브리핑 카테고리</h1>
      <p className="mt-2 text-sm text-popory-muted">
        services/brief/categories/&#123;slug&#125;/SKILL.md 를 GitHub에서 read/edit. 저장 시 main 브랜치에 commit.
      </p>
```

변경 — `<h1>`을 flex 컨테이너로 감싸고 `+ 새 카테고리` 링크 추가.

```tsx
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
```

(`Link`는 이미 import되어 있음 — 추가 import 불필요.)

- [ ] **Step 2: portal build 검증**

```bash
cd /Users/daegong/projects/popory
pnpm --filter @popory/portal build 2>&1 | tail -5
```

기대 출력. `Compiled successfully`.

- [ ] **Step 3: commit**

```bash
git add apps/portal/src/app/admin/brief-categories/page.tsx
git commit -m "$(cat <<'EOF'
feat(portal): /admin/brief-categories 목록에 + 새 카테고리 링크

표 상단 헤더에 /admin/brief-categories/new 로 이동하는 + 새 카테고리 링크 1줄 추가. 기존 표·표 행은 그대로.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 빌드·deploy + push + end-to-end 검증

**Files:** (코드 수정 없음)

- [ ] **Step 1: push origin/main**

```bash
cd /Users/daegong/projects/popory
git push origin main 2>&1 | tail -2
```

기대. Task 1~4 commit 4개가 origin/main에 push.

- [ ] **Step 2: worker 재배포**

```bash
pnpm --filter @popory/api exec wrangler deploy --config ../../infra/wrangler/api.toml --env prod 2>&1 | tail -5
```

기대 출력. `Deployed popory-api-prod triggers ...`.

- [ ] **Step 3: portal build:cf + deploy**

```bash
pnpm --filter @popory/portal build 2>&1 | tail -3
pnpm --filter @popory/portal build:cf 2>&1 | tail -2
cd apps/portal
npx wrangler pages deploy .vercel/output/static --project-name=popory-portal --branch=main 2>&1 | tail -2
```

기대 출력. `✨ Deployment complete!` + preview URL.

- [ ] **Step 4: 비인증 검증**

```bash
echo "===worker POST 비admin 401===" && curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "content-type: application/json" -d '{}' "https://api.poporyfamily.com/api/admin/brief-categories"
echo "===portal /admin/brief-categories/new 페이지 응답===" && curl -s -o /dev/null -w "%{http_code}\n" "https://poporyfamily.com/admin/brief-categories/new"
```

기대 출력. worker POST 401, portal new 페이지 200 (form 렌더).

- [ ] **Step 5: 사용자 작업 — admin 로그인 후 카테고리 추가 시도**

브라우저에서 `https://poporyfamily.com/admin/brief-categories` 접속.

1. 상단 `+ 새 카테고리` 링크 클릭 → `/admin/brief-categories/new` 폼 노출
2. slug = `esg` (예시), name = `ESG`, delivery_mode = bundled, enabled = false
3. body textarea는 일단 짧게 (`test body\n` 정도)
4. [생성] 클릭
5. 목록 페이지로 redirect → esg 행 표시 (sha 7자)
6. GitHub `https://github.com/rarebirds-svg/popory/commits/main` 에 `chore(brief): create categories/esg/SKILL.md via portal admin (by {admin@email})` commit 1개 생성 확인

- [ ] **Step 6: slug 충돌 검증 (선택)**

같은 slug `esg`로 한 번 더 생성 시도 → 인라인 빨간 박스 `worker-422: {"errors":["slug already exists"]}` 표시.

- [ ] **Step 7: 예약어 검증 (선택)**

slug = `new`로 시도 → 인라인 빨간 박스 `worker-422: ...예약어...` 표시.

- [ ] **Step 8: 정리 (선택, 테스트 카테고리 esg 삭제)**

사용자 로컬 git에서.
```bash
cd /Users/daegong/projects/popory
git pull --ff-only origin main
rm -rf services/brief/categories/esg/
git add services/brief/categories/esg/
git commit -m "chore(brief): remove test category esg"
git push origin main
```

(또는 esg를 진짜 운영할 거면 유지.)

- [ ] **Step 9: 완료 보고**

```bash
git log --oneline -10
```

기대. Task 1~4 commit 4개 + 사용자 시도로 생성된 GitHub commit 1~2개. 작업 종료.
