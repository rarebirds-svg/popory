<!-- portal /p/brief 동적 카테고리 발견 + SKILL.md description 필드 implementation plan. -->
# portal /p/brief 동적 카테고리 발견 + SKILL.md description Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SKILL.md frontmatter에 description 필드 추가 + public worker endpoint `GET /api/brief-categories` 신설 + portal `/p/brief` 하드코딩 제거하여 카테고리를 동적 발견하도록 한다.

**Architecture:** GitHub source 그대로 유지. SKILL.md에 description 7번째 필드 추가. worker가 GitHub Contents API에서 frontmatter 읽고 enabled=true만 public JSON으로 노출. portal 허브 server fetch.

**Tech Stack:** Cloudflare Workers + Hono · vitest (`cloudflare:test`) · Next.js 15 server component · GitHub Contents API REST

**Reference spec:** [docs/superpowers/specs/2026-05-31-popory-brief-categories-dynamic-discovery-amendment.md](../specs/2026-05-31-popory-brief-categories-dynamic-discovery-amendment.md)

---

## File Map

**Modify**
- `workers/api/src/lib/skill_md.ts` — `SkillFields.description` 추가, REQUIRED + validateFields + serializeSkillMd 갱신
- `workers/api/src/lib/skill_md.test.ts` — SAMPLE에 description 포함, validate 빈 description 테스트 1건 추가
- `workers/api/src/routes/admin_brief_categories.ts` — public `GET /api/brief-categories` 핸들러 추가
- `workers/api/src/routes/admin_brief_categories.test.ts` — public endpoint 3건 추가 (정상·인증 없이 200·enabled 필터·502)
- `apps/portal/src/app/admin/brief-categories/[slug]/EditForm.tsx` — description input 추가
- `apps/portal/src/app/admin/brief-categories/new/NewForm.tsx` — description input 추가 + 기본값
- `apps/portal/src/app/p/brief/page.tsx` — BRIEF_CATEGORIES 하드코딩 제거, fetchCategories 신규
- `services/brief/categories/{realestate,anticorruption,chaebol,sanction,antitrust,legal-ai}/SKILL.md` — frontmatter에 description 1줄씩 추가 (6개 파일)

**Critical 순서:** Task 1(skill_md) → Task 2(SKILL.md 마이그레이션) → Task 3(admin 폼) → Task 4(public route) → Task 5(portal) → Task 6(deploy). 순서 깨면 prod 일시 fail.

---

## Task 1: skill_md.ts에 description 필드 추가 + 테스트 (TDD)

**Files:**
- Modify: `workers/api/src/lib/skill_md.ts`
- Modify: `workers/api/src/lib/skill_md.test.ts`

- [ ] **Step 1: test 파일 SAMPLE + 1 it 추가 (실패)**

`workers/api/src/lib/skill_md.test.ts`의 SAMPLE 변수에 description 추가.

기존.
```ts
const SAMPLE = `---
slug: realestate
name: 부동산
delivery_mode: standalone
subject_template: "[{name} 이슈 브리핑] {date}"
sender_name: "{name} 이슈 브리핑"
enabled: true
---

본문 system prompt 첫 줄.
`;
```

변경.
```ts
const SAMPLE = `---
slug: realestate
name: 부동산
delivery_mode: standalone
subject_template: "[{name} 이슈 브리핑] {date}"
sender_name: "{name} 이슈 브리핑"
enabled: true
description: "국토부·한국부동산원·기재부 정책·시장·판례"
---

본문 system prompt 첫 줄.
`;
```

`describe("parseSkillMd", ...)` 안 첫 it (`"frontmatter 6필드 + body 분리"`)의 expect에 description 추가.

기존.
```ts
    expect(r.fields).toEqual({
      slug: "realestate",
      name: "부동산",
      delivery_mode: "standalone",
      subject_template: "[{name} 이슈 브리핑] {date}",
      sender_name: "{name} 이슈 브리핑",
      enabled: true,
    });
```

변경.
```ts
    expect(r.fields).toEqual({
      slug: "realestate",
      name: "부동산",
      delivery_mode: "standalone",
      subject_template: "[{name} 이슈 브리핑] {date}",
      sender_name: "{name} 이슈 브리핑",
      enabled: true,
      description: "국토부·한국부동산원·기재부 정책·시장·판례",
    });
```

`describe("validateFields", ...)` 안 `base`에 description 추가.

기존.
```ts
  const base: SkillFields = {
    slug: "realestate",
    name: "부동산",
    delivery_mode: "standalone",
    subject_template: "[{name}] {date}",
    sender_name: "{name}",
    enabled: true,
  };
```

변경.
```ts
  const base: SkillFields = {
    slug: "realestate",
    name: "부동산",
    delivery_mode: "standalone",
    subject_template: "[{name}] {date}",
    sender_name: "{name}",
    enabled: true,
    description: "국토부 정책·시장 동향",
  };
```

`describe("validateFields", ...)` 안 마지막에 it 1건 추가.

```ts
  it("description 빈 문자열 위반", () => {
    expect(validateFields({ ...base, description: "" })).toContainEqual(
      expect.stringContaining("description"),
    );
  });
```

`describe("serializeSkillMd", ...)` 안 `"template value 안의 따옴표 escape"` it의 fields에 description 추가.

기존.
```ts
    const out = serializeSkillMd({
      fields: {
        slug: "x",
        name: "X",
        delivery_mode: "bundled",
        subject_template: 'A "B" C',
        sender_name: "S",
        enabled: false,
      },
      body: "body\n",
    });
```

변경 (description 한 줄 추가).
```ts
    const out = serializeSkillMd({
      fields: {
        slug: "x",
        name: "X",
        delivery_mode: "bundled",
        subject_template: 'A "B" C',
        sender_name: "S",
        enabled: false,
        description: "desc",
      },
      body: "body\n",
    });
```

`describe("serializeSkillMd", ...)` 안 `"sender_name 안의 따옴표·역슬래시 escape round-trip"` it의 fields에 description 추가.

기존.
```ts
    const fields = {
      slug: "x",
      name: "X",
      delivery_mode: "bundled" as const,
      subject_template: "x",
      sender_name: 'a "b" \\\\c',
      enabled: true,
    };
```

변경.
```ts
    const fields = {
      slug: "x",
      name: "X",
      delivery_mode: "bundled" as const,
      subject_template: "x",
      sender_name: 'a "b" \\\\c',
      enabled: true,
      description: "desc",
    };
```

`describe("parseSkillMd body 안의 --- 구분선 보존", ...)` 안의 txt에 description 한 줄 추가.

기존.
```ts
    const txt = `---
slug: foo
name: Foo
delivery_mode: bundled
subject_template: "x"
sender_name: "x"
enabled: true
---
```

변경.
```ts
    const txt = `---
slug: foo
name: Foo
delivery_mode: bundled
subject_template: "x"
sender_name: "x"
enabled: true
description: "desc"
---
```

- [ ] **Step 2: 테스트 실행 → 실패 (description missing field 등)**

```bash
cd /Users/daegong/projects/popory/workers/api
pnpm test --run src/lib/skill_md.test.ts 2>&1 | tail -10
```

기대 출력. `missing field: description` 또는 `description` 위반으로 일부 it FAIL.

- [ ] **Step 3: skill_md.ts에 description 적용**

`workers/api/src/lib/skill_md.ts`.

`SkillFields` interface 7번째 필드 추가.
```ts
export interface SkillFields {
  slug: string;
  name: string;
  delivery_mode: "standalone" | "bundled";
  subject_template: string;
  sender_name: string;
  enabled: boolean;
  description: string;
}
```

`REQUIRED` 튜플에 `"description"` 추가.
```ts
const REQUIRED = ["slug", "name", "delivery_mode", "subject_template", "sender_name", "enabled", "description"] as const;
```

`parseSkillMd` 안 fields 생성 부분에 description 한 줄 추가 (다른 string 필드와 동일하게 `String(raw.description)` 호출).
```ts
  const fields: SkillFields = {
    slug: String(raw.slug),
    name: String(raw.name),
    delivery_mode: String(raw.delivery_mode) as SkillFields["delivery_mode"],
    subject_template: String(raw.subject_template),
    sender_name: String(raw.sender_name),
    enabled: raw.enabled === true || raw.enabled === "true",
    description: String(raw.description),
  };
```

`serializeSkillMd` 함수의 `fm` 배열에 description 한 줄 추가 (큰따옴표 wrap, escape).
```ts
  const fm = [
    `slug: ${fields.slug}`,
    `name: ${fields.name}`,
    `delivery_mode: ${fields.delivery_mode}`,
    `subject_template: "${esc(fields.subject_template)}"`,
    `sender_name: "${esc(fields.sender_name)}"`,
    `enabled: ${fields.enabled ? "true" : "false"}`,
    `description: "${esc(fields.description)}"`,
  ].join("\n");
```

`validateFields` 함수에 description 빈 검사 한 줄 추가.
```ts
export function validateFields(f: SkillFields): string[] {
  const errs: string[] = [];
  if (!SLUG_RE.test(f.slug)) errs.push(`slug 규칙 위반 (^[a-z][a-z0-9-]{1,30}$)`);
  if (RESERVED_SLUGS.has(f.slug)) errs.push(`slug "${f.slug}"는 예약어 (사용 불가)`);
  if (!VALID_MODES.has(f.delivery_mode)) errs.push(`delivery_mode 화이트리스트 위반 (standalone|bundled)`);
  if (!f.name.trim()) errs.push("name 비어있음");
  if (!f.subject_template.trim()) errs.push("subject_template 비어있음");
  if (!f.sender_name.trim()) errs.push("sender_name 비어있음");
  if (!f.description.trim()) errs.push("description 비어있음");
  return errs;
}
```

- [ ] **Step 4: 테스트 실행 → 통과**

```bash
pnpm test --run src/lib/skill_md.test.ts 2>&1 | tail -10
```

기대 출력. 14 passed (이전 13 + 신규 1).

- [ ] **Step 5: 회귀 확인 (다른 worker 테스트가 SAMPLE_REALESTATE 사용 → description 없어서 깨질 수 있음)**

```bash
pnpm test 2>&1 | tail -10
```

기대 결과 분석.
- skill_md.test.ts → PASS
- admin_brief_categories.test.ts → SKILL_REALESTATE 상수가 그 파일 안에도 정의되어 있음. description 없으면 parseSkillMd가 `missing field: description` error 반환 → 일부 it (GET 목록·GET 단건·PUT) FAIL 가능.

확인 후 admin_brief_categories.test.ts의 SKILL_REALESTATE에도 description 추가.

`workers/api/src/routes/admin_brief_categories.test.ts` 의 `SKILL_REALESTATE` 변수에 description 한 줄 추가.

기존.
```ts
const SKILL_REALESTATE = `---
slug: realestate
name: 부동산
delivery_mode: standalone
subject_template: "[{name} 이슈 브리핑] {date}"
sender_name: "{name} 이슈 브리핑"
enabled: true
---
```

변경.
```ts
const SKILL_REALESTATE = `---
slug: realestate
name: 부동산
delivery_mode: standalone
subject_template: "[{name} 이슈 브리핑] {date}"
sender_name: "{name} 이슈 브리핑"
enabled: true
description: "국토부·한국부동산원·기재부 정책·시장·판례"
---
`;
```

또 `admin_brief_categories.test.ts` 안의 PUT/POST 케이스에서 `fields: { ... }` 객체에 description 추가 (5건 정도). 각각 `description: "desc"` 또는 자연스러운 짧은 description 추가.

```ts
fields: { slug: "realestate", name: "부동산", delivery_mode: "standalone", subject_template: "[{name}] {date}", sender_name: "{name}", enabled: false, description: "desc" },
```

(PUT 정상·sha mismatch·POST 정상·POST slug 중복·POST 예약어·POST 비admin — `fields:` 가 들어가는 모든 case)

다시 회귀 실행.
```bash
pnpm test 2>&1 | tail -10
```

기대 출력. 모든 테스트 PASS.

- [ ] **Step 6: commit**

```bash
cd /Users/daegong/projects/popory
git add workers/api/src/lib/skill_md.ts \
        workers/api/src/lib/skill_md.test.ts \
        workers/api/src/routes/admin_brief_categories.test.ts
git commit -m "$(cat <<'EOF'
feat(api): SKILL.md frontmatter에 description 필드 추가

SkillFields 7번째 필수 필드 description 추가. REQUIRED·serializeSkillMd·validateFields 갱신. skill_md.test.ts SAMPLE/base + 새 validate 테스트 1건. admin_brief_categories.test.ts SKILL_REALESTATE + fields payloads에도 description 추가 (회귀 호환).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 기존 SKILL.md 6개 description 마이그레이션

**Files:**
- Modify: `services/brief/categories/realestate/SKILL.md`
- Modify: `services/brief/categories/anticorruption/SKILL.md`
- Modify: `services/brief/categories/chaebol/SKILL.md`
- Modify: `services/brief/categories/sanction/SKILL.md`
- Modify: `services/brief/categories/antitrust/SKILL.md`
- Modify: `services/brief/categories/legal-ai/SKILL.md`

- [ ] **Step 1: 각 SKILL.md frontmatter에 description 1줄씩 추가**

각 파일의 `enabled: true` 직후 (frontmatter 닫힘 `---` 직전)에 `description: "..."` 한 줄 추가.

`services/brief/categories/realestate/SKILL.md` — 추가.
```yaml
description: "국토부·한국부동산원·기재부 정책·시장·판례"
```

`services/brief/categories/anticorruption/SKILL.md` — 추가.
```yaml
description: "권익위·검찰·공수처·감사원 공직 비위·청탁금지법"
```

`services/brief/categories/chaebol/SKILL.md` — 추가.
```yaml
description: "공정위 대규모기업집단·동일인·DART 공시"
```

`services/brief/categories/sanction/SKILL.md` — 추가.
```yaml
description: "OFAC·UN·EU·외교부 국제 제재 동향"
```

`services/brief/categories/antitrust/SKILL.md` — 추가.
```yaml
description: "공정위 카르텔·M&A·표시광고·플랫폼 규제"
```

`services/brief/categories/legal-ai/SKILL.md` — 추가.
```yaml
description: "AI 기본법·EU AI Act·LegalTech·알고리즘 거버넌스"
```

- [ ] **Step 2: Python categories.py 호환성 확인**

Python의 `categories.py` REQUIRED는 description 모름. SKILL.md에 description 추가해도 Python parser는 무시. 즉시 검증.

```bash
cd /Users/daegong/projects/popory/services/brief
.venv/bin/python -c "
from popory_brief.categories import load_category, list_categories
for slug in ['realestate', 'anticorruption', 'chaebol', 'sanction', 'antitrust', 'legal-ai']:
    c = load_category(slug)
    print(f'{slug}: name={c.name}, mode={c.delivery_mode}, enabled={c.enabled}, prompt_len={len(c.system_prompt)}')
"
```

기대 출력. 6개 모두 정상 로드 (이전과 동일 prompt_len). description 라인은 Python parser가 frontmatter에서 raw로 읽되 Category 데이터클래스에 매핑 안 됨.

- [ ] **Step 3: commit**

```bash
cd /Users/daegong/projects/popory
git add services/brief/categories/realestate/SKILL.md \
        services/brief/categories/anticorruption/SKILL.md \
        services/brief/categories/chaebol/SKILL.md \
        services/brief/categories/sanction/SKILL.md \
        services/brief/categories/antitrust/SKILL.md \
        services/brief/categories/legal-ai/SKILL.md
git commit -m "$(cat <<'EOF'
chore(brief): 6개 SKILL.md frontmatter에 description 필드 추가

portal /p/brief 허브의 카드 설명 텍스트를 source of truth(SKILL.md)로 이전. 현재 portal 하드코딩 description을 그대로 옮김. Python categories.py는 description 모름 (영향 없음, raw 무시).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: admin EditForm + NewForm에 description input 추가

**Files:**
- Modify: `apps/portal/src/app/admin/brief-categories/[slug]/EditForm.tsx`
- Modify: `apps/portal/src/app/admin/brief-categories/new/NewForm.tsx`

- [ ] **Step 1: EditForm.tsx에 description state + input 추가**

`apps/portal/src/app/admin/brief-categories/[slug]/EditForm.tsx`.

`InitialFields` interface에 description 추가.
```ts
interface InitialFields {
  slug: string;
  name: string;
  delivery_mode: "standalone" | "bundled";
  subject_template: string;
  sender_name: string;
  enabled: boolean;
  description: string;
}
```

useState 추가 (다른 필드 옆).
```ts
  const [description, setDescription] = useState(initialFields.description);
```

submit handler의 fields 객체에 description 추가.
```ts
        body: JSON.stringify({
          fields: {
            slug,
            name,
            delivery_mode: deliveryMode,
            subject_template: subjectTemplate,
            sender_name: senderName,
            enabled,
            description,
          },
          body,
          sha: initialSha,
        }),
```

폼 안의 적절한 위치 (이름 input 직후)에 description input 추가.
```tsx
      <Field label="설명 (description). 카드에 노출되는 1~2줄 카테고리 소개">
        <input value={description} onChange={(e) => setDescription(e.target.value)} required className={INPUT} />
      </Field>
```

- [ ] **Step 2: NewForm.tsx에 description state + input + 기본값 추가**

`apps/portal/src/app/admin/brief-categories/new/NewForm.tsx`.

useState 추가 (slug·name 옆).
```ts
  const [description, setDescription] = useState("");
```

submit handler의 fields 객체에 description 추가.
```ts
          fields: {
            slug,
            name,
            delivery_mode: deliveryMode,
            subject_template: subjectTemplate,
            sender_name: senderName,
            enabled,
            description,
          },
```

폼 안 이름 input 직후에 description input 추가.
```tsx
      <Field label="설명 (description). 카드에 노출되는 1~2줄 카테고리 소개">
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          required
          placeholder="예. AI 기본법·EU AI Act·LegalTech"
          className={INPUT}
        />
      </Field>
```

- [ ] **Step 3: portal build 검증**

```bash
cd /Users/daegong/projects/popory
pnpm --filter @popory/portal build 2>&1 | tail -5
```

기대 출력. `Compiled successfully`.

- [ ] **Step 4: commit**

```bash
git add apps/portal/src/app/admin/brief-categories/\[slug\]/EditForm.tsx \
        apps/portal/src/app/admin/brief-categories/new/NewForm.tsx
git commit -m "$(cat <<'EOF'
feat(portal): admin 편집/생성 폼에 description input 추가

EditForm + NewForm에 description input 1개씩 추가. payload·useState·required 모두 처리. SKILL.md frontmatter 7번째 필수 필드와 일치.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: public worker route GET /api/brief-categories + 테스트

**Files:**
- Modify: `workers/api/src/routes/admin_brief_categories.ts` (public 라우트 1개 추가)
- Modify: `workers/api/src/routes/admin_brief_categories.test.ts` (3 it 추가)

- [ ] **Step 1: 실패 테스트 3건 추가**

`workers/api/src/routes/admin_brief_categories.test.ts` 의 `describe("admin_brief_categories", ...)` 안 마지막에 추가.

```ts
  it("public GET /api/brief-categories — 인증 없이 200 + enabled=true만", async () => {
    const SKILL_ENABLED = `---\nslug: realestate\nname: 부동산\ndelivery_mode: standalone\nsubject_template: "x"\nsender_name: "x"\nenabled: true\ndescription: "부동산 desc"\n---\n\n본문\n`;
    const SKILL_DISABLED = `---\nslug: hidden\nname: 숨김\ndelivery_mode: bundled\nsubject_template: "x"\nsender_name: "x"\nenabled: false\ndescription: "hidden desc"\n---\n\n본문\n`;
    mockGithub({
      "contents/services/brief/categories?ref=main": () =>
        Response.json([
          { type: "dir", name: "realestate", path: "services/brief/categories/realestate", sha: "d1" },
          { type: "dir", name: "hidden", path: "services/brief/categories/hidden", sha: "d2" },
        ]),
      "contents/services/brief/categories/realestate/SKILL.md?ref=main": () =>
        Response.json({ content: btoa(unescape(encodeURIComponent(SKILL_ENABLED))), sha: "f1", path: "services/brief/categories/realestate/SKILL.md" }),
      "contents/services/brief/categories/hidden/SKILL.md?ref=main": () =>
        Response.json({ content: btoa(unescape(encodeURIComponent(SKILL_DISABLED))), sha: "f2", path: "services/brief/categories/hidden/SKILL.md" }),
    });
    // cookie 없이 호출
    const res = await SELF.fetch("https://example.com/api/brief-categories");
    expect(res.status).toBe(200);
    const body = await res.json<{ items: Array<{ slug: string; name: string; description: string; enabled: boolean }> }>();
    expect(body.items).toHaveLength(1);
    expect(body.items[0]).toMatchObject({ slug: "realestate", name: "부동산", description: "부동산 desc", enabled: true });
  });

  it("public GET — GitHub API 502 시 502 반환", async () => {
    mockGithub({
      "contents/services/brief/categories?ref=main": () =>
        new Response(JSON.stringify({ message: "Server Error" }), { status: 500 }),
    });
    const res = await SELF.fetch("https://example.com/api/brief-categories");
    expect(res.status).toBe(502);
  });

  it("public GET — 빈 디렉토리 시 빈 items", async () => {
    mockGithub({
      "contents/services/brief/categories?ref=main": () => Response.json([]),
    });
    const res = await SELF.fetch("https://example.com/api/brief-categories");
    expect(res.status).toBe(200);
    const body = await res.json<{ items: unknown[] }>();
    expect(body.items).toEqual([]);
  });
```

- [ ] **Step 2: 테스트 실행 → 실패 (라우트 없음 → 404)**

```bash
cd /Users/daegong/projects/popory/workers/api
pnpm test --run src/routes/admin_brief_categories.test.ts 2>&1 | tail -10
```

기대 출력. 3건 신규 FAIL (404).

- [ ] **Step 3: public 라우트 구현**

`workers/api/src/routes/admin_brief_categories.ts` 의 `mountAdminBriefCategories` 함수 안 시작 부분 (admin 라우트 들 전에) 추가.

```ts
  // public 목록 — enabled=true 만 + 인증 없음
  app.get("/api/brief-categories", async (c) => {
    const token = c.env.BRIEF_CATEGORIES_GITHUB_TOKEN;
    try {
      const entries = await getDir(token, CATEGORIES_PATH);
      const dirs = entries.filter((e) => e.type === "dir");
      const all = await Promise.all(
        dirs.map(async (d) => {
          const file = await getFile(token, `${CATEGORIES_PATH}/${d.name}/SKILL.md`);
          const text = decodeBase64Utf8(file.content);
          const parsed = parseSkillMd(text);
          return parsed.fields
            ? {
                slug: d.name,
                name: parsed.fields.name,
                description: parsed.fields.description,
                delivery_mode: parsed.fields.delivery_mode,
                enabled: parsed.fields.enabled,
                sha: file.sha,
              }
            : null;
        }),
      );
      const items = all.filter((i): i is NonNullable<typeof i> => i !== null && i.enabled);
      return c.json({ items });
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

기대 출력. 13건 모두 PASS (기존 10 + 신규 3).

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
feat(api): public GET /api/brief-categories (인증 X, enabled=true 필터)

portal /p/brief 허브용 public 라우트. requireAdmin 없음. GitHub Contents API에서 enabled=true 카테고리만 frontmatter(slug·name·description·delivery_mode·enabled·sha) JSON 반환. 단위 테스트 3건 (정상·502·빈 디렉토리).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: portal /p/brief 동적 fetch로 변경

**Files:**
- Modify: `apps/portal/src/app/p/brief/page.tsx`

- [ ] **Step 1: BRIEF_CATEGORIES 하드코딩 제거 + fetchCategories 추가**

`apps/portal/src/app/p/brief/page.tsx` 전체 재작성.

```tsx
// popory 일일 브리핑 카테고리 허브 페이지. worker /api/brief-categories에서 동적 발견 후 최신 brief 카드 노출.
import Link from "next/link";
import { API_BASE } from "@/lib/env";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface Item {
  id: string;
  title: string;
  summary: string | null;
  published_at: number;
}

interface CategoryMeta {
  slug: string;
  name: string;
  description: string;
  delivery_mode: "standalone" | "bundled";
  enabled: boolean;
  sha: string;
}

interface CategoryCard extends CategoryMeta {
  latest: Item | null;
}

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

async function fetchLatest(slug: string): Promise<Item | null> {
  try {
    const res = await fetch(
      `${API_BASE}/api/published_items?area=brief-${slug}&limit=1`,
      { cache: "no-store" },
    );
    if (!res.ok) return null;
    const { items } = (await res.json()) as { items: Item[] };
    return items[0] ?? null;
  } catch {
    return null;
  }
}

function formatDate(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toISOString().slice(0, 10);
}

export default async function BriefHubPage() {
  const cats = await fetchCategories();
  const cards: CategoryCard[] = [];
  for (const c of cats) {
    cards.push({ ...c, latest: await fetchLatest(c.slug) });
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <header className="mb-10">
        <h1 className="text-3xl font-semibold tracking-tight text-popory-fg">
          일일 브리핑
        </h1>
        <p className="mt-2 text-sm text-popory-muted">
          매일 09:00 KST에 카테고리별로 새 브리핑이 발행됩니다. 카드를 눌러 카테고리별 전체 목록을 확인하세요.
        </p>
      </header>
      {cards.length === 0 ? (
        <p className="text-sm text-popory-muted">카테고리 목록을 불러오지 못했습니다.</p>
      ) : (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {cards.map((c) => (
            <li key={c.slug}>
              <Link
                href={`/p/brief-${c.slug}`}
                className="group block h-full rounded-xl border border-popory-border bg-popory-card p-5 transition hover:border-popory-accent"
              >
                <div className="text-[11px] uppercase tracking-wider text-popory-muted">
                  brief-{c.slug}
                </div>
                <div className="mt-1 text-lg font-semibold text-popory-fg group-hover:text-popory-accent">
                  {c.name}
                </div>
                <div className="mt-1 text-xs text-popory-muted">{c.description}</div>
                {c.latest ? (
                  <div className="mt-4 border-t border-popory-border pt-3">
                    <div className="text-[11px] uppercase tracking-wider text-popory-muted">
                      최신 · {formatDate(c.latest.published_at)}
                    </div>
                    <div className="mt-1 line-clamp-2 text-sm font-medium text-popory-fg">
                      {c.latest.title}
                    </div>
                    {c.latest.summary && (
                      <div className="mt-1 line-clamp-2 text-xs text-popory-muted">
                        {c.latest.summary}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="mt-4 border-t border-popory-border pt-3 text-xs text-popory-muted">
                    아직 발행된 브리핑이 없습니다.
                  </div>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
      <footer className="mt-10 border-t border-popory-border pt-4 text-xs text-popory-muted">
        총 {cards.length}개 카테고리. 새 카테고리는 admin /admin/brief-categories/new에서 추가합니다.
      </footer>
    </main>
  );
}
```

- [ ] **Step 2: build 검증**

```bash
cd /Users/daegong/projects/popory
pnpm --filter @popory/portal build 2>&1 | tail -5
```

기대 출력. `Compiled successfully`.

- [ ] **Step 3: commit**

```bash
git add apps/portal/src/app/p/brief/page.tsx
git commit -m "$(cat <<'EOF'
feat(portal): /p/brief 동적 카테고리 발견 (BRIEF_CATEGORIES 하드코딩 제거)

worker GET /api/brief-categories에서 fetch → 카드 grid. label·description은 응답에서. footer 카테고리 수도 동적. fetch 실패 시 빈 grid + 메시지.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: push + worker/portal deploy + 검증

**Files:** (코드 수정 없음)

- [ ] **Step 1: push origin/main**

```bash
cd /Users/daegong/projects/popory
git push origin main 2>&1 | tail -2
```

기대. Task 1~5 commit 5개 push.

- [ ] **Step 2: worker 재배포**

```bash
pnpm --filter @popory/api exec wrangler deploy --config ../../infra/wrangler/api.toml --env prod 2>&1 | tail -5
```

기대 출력. `Deployed popory-api-prod triggers ...`.

- [ ] **Step 3: public endpoint 검증 (cookie 없이 200)**

```bash
curl -s "https://api.poporyfamily.com/api/brief-categories" | python3 -m json.tool | head -40
```

기대 출력. `items` 배열에 6개 카테고리 (description 포함, enabled=true 모두).

- [ ] **Step 4: portal build:cf + deploy**

```bash
pnpm --filter @popory/portal build 2>&1 | tail -3
pnpm --filter @popory/portal build:cf 2>&1 | tail -2
cd apps/portal
npx wrangler pages deploy .vercel/output/static --project-name=popory-portal --branch=main 2>&1 | tail -2
```

기대 출력. `✨ Deployment complete!` + preview URL.

- [ ] **Step 5: prod /p/brief 검증**

```bash
sleep 3 && curl -s "https://poporyfamily.com/p/brief?cb=$(date +%s)" -o /tmp/brief_hub_dyn.html && python3 << 'EOF'
import re
with open('/tmp/brief_hub_dyn.html', 'r') as f: html = f.read()
slugs = re.findall(r'brief-<!-- -->(\w[\w-]*)', html)
total = re.search(r'총 <!-- -->(\d+)<!-- -->개', html)
descs = re.findall(r'text-xs text-popory-muted">([^<]{10,})</div>', html)
print(f"slug 목록: {slugs}")
print(f"footer 카운트: {total.group(1) if total else '?'}")
print(f"description 후보 (앞 6개): {descs[:6]}")
EOF
```

기대 출력. 6개 slug 표시 + footer 6 + description 노출.

- [ ] **Step 6: 완료 보고**

```bash
git log --oneline -10
```

기대. Task 1~5 commit 5개 + 사용자가 향후 admin에서 카테고리 추가 시 자동 발견·노출.
