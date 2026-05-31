<!-- portal /p/brief 허브의 카테고리 목록을 worker public endpoint로 동적 발견 + SKILL.md frontmatter에 description 필드 추가하는 amendment. -->
---
title: popory — portal /p/brief 동적 카테고리 발견 + SKILL.md description 필드 (amendment)
date: 2026-05-31
status: draft
amends:
  - docs/superpowers/specs/2026-05-30-popory-f1-brief-multi-category-design.md
  - docs/superpowers/specs/2026-05-31-popory-admin-brief-categories-design.md
  - docs/superpowers/specs/2026-05-31-popory-admin-brief-categories-add-amendment.md
---

# portal /p/brief 동적 카테고리 발견 + SKILL.md description 필드 (amendment)

## 1. 변경 동기

- 원안 spec 2026-05-30-popory-f1-brief-multi-category-design §13 "향후 확장 여지"에 명시한 항목 일부 구현.
- 현재 `apps/portal/src/app/p/brief/page.tsx`의 `BRIEF_CATEGORIES`가 하드코딩된 배열. 새 카테고리 추가 시 portal 페이지 수정 + redeploy 필요 → admin이 카테고리 추가했는데 portal 허브에 안 보임 (legal-ai 사례).
- 동시에 카드의 "설명" 텍스트는 portal에 매핑되어 있어 SKILL.md와 분리되어 있음 → SKILL.md를 source of truth로 통합.

## 2. 비목표

- response cache. 초기에는 cache 없이 (no-store). 부하 발생 시 별도 amendment에서 60초 cache 등.
- 다른 frontmatter 필드 추가 (예. icon, tags, color). description 1개만.
- `services/brief/popory_brief/categories.py` (Python)의 `Category` 데이터클래스에 description 추가. generate_brief.py가 사용 안 함. 추후 메일 본문에 description 포함 등 사용 시점에 별도 추가.
- public endpoint에 rate limit 직접 구현. Cloudflare 자체 DDoS 보호로 충분.
- portal 허브에서 카테고리 정렬 변경 (현재 alphabetical 그대로).

## 3. 결정 요약

| 항목 | 결정 |
|------|------|
| SKILL.md 새 필드 | `description: "..."` (frontmatter 7번째 필수 필드) |
| validate | 비어있지 않음. 길이 제한은 안 함 (운영자 자율) |
| 새 worker route | `GET /api/brief-categories` (public, 인증 X). enabled=true 만 |
| 응답 형식 | `{ items: [{ slug, name, description, delivery_mode, enabled, sha }, ...] }` |
| portal /p/brief 변경 | BRIEF_CATEGORIES 하드코딩 제거, 동적 fetch |
| 카테고리 정렬 | 응답 그대로 (GitHub API getDir 알파벳 순) |
| Admin 폼 변경 | EditForm + NewForm에 description input 추가 |
| 기존 SKILL.md | 6개에 description 1줄 추가 마이그레이션 |
| 응답 cache | 없음 (no-store) |

## 4. 컴포넌트 변경

### 4.1 worker
- **수정** `workers/api/src/lib/skill_md.ts`
  - `SkillFields` interface에 `description: string` 추가
  - `REQUIRED` 튜플에 `"description"` 추가
  - `validateFields`에 `if (!f.description.trim()) errs.push("description 비어있음")` 추가
  - `serializeSkillMd`에 `description: "{escaped}"` 한 줄 추가 (다른 string 필드와 동일하게 큰따옴표 wrap)
- **수정** `workers/api/src/lib/skill_md.test.ts`
  - SAMPLE에 description 추가
  - validate `description 비어있음` 위반 테스트 1건 추가
  - round-trip은 SAMPLE 변경으로 자동 검증
- **수정** `workers/api/src/routes/admin_brief_categories.ts`
  - 같은 파일에 `app.get("/api/brief-categories", ...)` 핸들러 추가 (public, requireAdmin 없음)
  - 흐름. `getDir(categories) → 각 SKILL.md getFile → parseSkillMd → enabled=true 필터 → JSON`
  - 응답 item에 description 포함
  - 기존 admin GET 목록은 enabled 무관 모든 카테고리 반환 (admin은 비활성도 봐야)
- **수정** `workers/api/src/routes/admin_brief_categories.test.ts`
  - 신규 public endpoint 테스트 3건 (정상·인증 없이 200·enabled=false 필터링·GitHub 502)

### 4.2 portal
- **수정** `apps/portal/src/app/p/brief/page.tsx`
  - `BRIEF_CATEGORIES` 배열 + `BRIEF_CATEGORIES.length` 헤더 표기 제거
  - 새로 `await fetch(${API_BASE}/api/brief-categories)` server-side fetch
  - 응답 items 순회. 각 카드. name + description + latest brief (fetchLatest는 그대로)
  - footer "총 N개 카테고리" — items.length 사용
- **수정** `apps/portal/src/app/admin/brief-categories/[slug]/EditForm.tsx`
  - description input 1개 추가 (name 위 또는 아래, 폼 자연 위치)
  - InitialFields에 description 추가
- **수정** `apps/portal/src/app/admin/brief-categories/new/NewForm.tsx`
  - description input 1개 추가 + 기본값 빈 문자열
- **수정** `apps/portal/src/app/admin/brief-categories/page.tsx` 목록 — 변경 없음 (이미 sha·name 표시만)

### 4.3 SKILL.md 마이그레이션
기존 6개 SKILL.md에 frontmatter `description` 1줄 추가 (별도 git commit, 운영자가 admin UI에서 추가 안 해도 일괄 처리).

| slug | description (제안값, 변경 가능) |
|------|------|
| realestate | `국토부·한국부동산원·기재부 정책·시장·판례` |
| anticorruption | `권익위·검찰·공수처·감사원 공직 비위·청탁금지법` |
| chaebol | `공정위 대규모기업집단·동일인·DART 공시` |
| sanction | `OFAC·UN·EU·외교부 국제 제재 동향` |
| antitrust | `공정위 카르텔·M&A·표시광고·플랫폼 규제` |
| legal-ai | `AI 기본법·EU AI Act·LegalTech·알고리즘 거버넌스` |

(현재 `apps/portal/src/app/p/brief/page.tsx` 하드코딩 description 그대로 옮긴 값.)

## 5. 새 worker route 상세

```ts
// 같은 admin_brief_categories.ts 파일 안. requireAdmin 없음.
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

## 6. portal /p/brief 변경 (요약)

```tsx
interface CategoryItem {
  slug: string;
  name: string;
  description: string;
  delivery_mode: "standalone" | "bundled";
  enabled: boolean;
  sha: string;
}

async function fetchCategories(): Promise<CategoryItem[]> {
  const res = await fetch(`${API_BASE}/api/brief-categories`, { cache: "no-store" });
  if (!res.ok) return [];
  const { items } = (await res.json()) as { items: CategoryItem[] };
  return items;
}

export default async function BriefHubPage() {
  const cats = await fetchCategories();
  const cards = await Promise.all(
    cats.map(async (c) => ({ ...c, latest: await fetchLatest(c.slug) })),
  );
  // ... render
}
```

(기존 BRIEF_CATEGORIES 하드코딩 제거. label·description은 API 응답에서.)

## 7. Error handling

| 실패 지점 | 처리 |
|---|---|
| skill_md validate description 빈 | 422 |
| public endpoint GitHub API fail | 502 |
| portal /p/brief fetch fail | 빈 grid + 메시지 "카테고리 목록 로드 실패" |
| 기존 SKILL.md 마이그레이션 전 portal fetch | parseSkillMd 시 description missing → required field 위반 → public endpoint가 그 카테고리 skip (그래도 portal 카드 1개 안 보임) |

**마이그레이션 순서 중요.** SKILL.md 6개에 description 한 줄씩 추가 → commit/push → worker redeploy → portal 변경 deploy. 순서 바뀌면 일시적 빈 카드.

## 8. Testing

### 8.1 worker
- skill_md round-trip (SAMPLE에 description 포함) — 자동
- validate description 빈 → 422 (1 테스트 추가)
- public `GET /api/brief-categories` 인증 없이 200 + 응답 items
- public endpoint enabled=false 필터링
- public endpoint GitHub mock 5xx → 502

### 8.2 portal
- build 성공
- (선택) Playwright. /p/brief 페이지에서 6개 카드 노출

## 9. Migration 절차

배포 순서.
1. skill_md.ts에 description 추가 + 테스트
2. 기존 6개 SKILL.md에 description 1줄씩 추가
3. admin EditForm + NewForm에 description input 추가
4. 새 public worker route `GET /api/brief-categories` 추가 + 테스트
5. portal /p/brief 동적 fetch로 변경
6. push → worker redeploy → portal build/deploy
7. 검증. https://poporyfamily.com/p/brief 에 6개 카드 + description 노출

## 10. 위험 요소

- **public endpoint 무인증 호출.** 카테고리 메타는 공개 정보라 정보 leak 위험 없음. GitHub PAT은 worker secret에서만 사용 — 외부 노출 없음. Cloudflare DDoS 보호로 abuse 제한.
- **GitHub rate limit.** 인증 PAT 5000/hour. portal /p/brief 페이지 로드당 N+1 호출 (목록 1 + 각 SKILL.md GET N). 6개면 7 req/load. 한 시간 700+ 페이지뷰까지 OK. 초과 시 cache 도입.
- **마이그레이션 순서 위반.** description 추가 안 한 SKILL.md가 portal에 노출되면 parseSkillMd 422 → 그 카테고리 안 보임. §9 순서 엄수 필요.

## 11. 향후 확장 여지 (본 amendment 범위 밖)

- response cache (60초 KV cache)
- 카테고리 정렬 정책 (frontmatter `order` 필드)
- icon·color·tags 같은 메타 추가
- portal /p/brief 페이지에 카테고리 group (분류) 표시
- description 다국어
