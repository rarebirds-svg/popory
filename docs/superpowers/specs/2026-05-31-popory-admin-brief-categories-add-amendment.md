<!-- portal admin에서 brief 카테고리 신규 생성 기능 추가 spec amendment. -->
---
title: popory — admin brief 카테고리 「추가」 기능 (amendment)
date: 2026-05-31
status: draft
amends: docs/superpowers/specs/2026-05-31-popory-admin-brief-categories-design.md
---

# admin · brief 카테고리 「추가」 기능 design (amendment)

## 1. 변경 동기

원안 spec §2 비목표에 "카테고리 추가/삭제 UI 없음. 신규 카테고리는 git에서 ... 추가로 등록"으로 명시했다. 운영 중 비기술자도 portal에서 새 카테고리를 만들 수 있어야 한다는 요청. 본 amendment는 **추가**만 도입. 삭제는 여전히 비목표.

## 2. 새로 추가되는 결정

| 항목 | 결정 |
|------|------|
| 추가 라우트 | `POST /api/admin/brief-categories` (worker) |
| portal UI | 신규 페이지 `/admin/brief-categories/new` + 목록 페이지 상단 `+ 새 카테고리` 링크 1줄 |
| GitHub 새 파일 생성 | Contents API PUT을 `sha` 없이 호출 (sha 인자 미전송 = create) |
| slug 충돌 검출 | server-side `getFile` 시도 → 200이면 422 "slug already exists" |
| 예약 slug | `new` (정적 라우트와 충돌). server-side validate에서 422 "reserved slug" |
| 폼 기본값 | name 빈 / delivery_mode `bundled` / subject_template `[{name} 이슈 브리핑] {date}` / sender_name `{name} 이슈 브리핑` / enabled `false` / body 빈 + placeholder |
| commit message | `chore(brief): create categories/{slug}/SKILL.md via portal admin (by {actor_email})` |
| 삭제 | 본 amendment 범위 외 (git에서 디렉토리 직접 제거) |
| 첫 구독자 INSERT | 본 amendment 범위 외 (admin이 D1 직접 또는 portal 별도 UI) |

## 3. 컴포넌트 변경

- **신규** `apps/portal/src/app/admin/brief-categories/new/page.tsx` — client component 폼. 편집 페이지(`[slug]/EditForm.tsx`)와 유사하지만 slug input 활성·sha 없음·POST 호출
- **수정** `apps/portal/src/app/admin/brief-categories/page.tsx` — 표 상단에 `+ 새 카테고리` 링크 1줄 추가
- **수정** `workers/api/src/routes/admin_brief_categories.ts` — `app.post(...)` 핸들러 1개 추가
- **수정** `workers/api/src/lib/github_contents.ts` — `PutFileInput.sha` 를 optional로 (`sha?: string`). undefined일 때 GitHub PUT body에서 sha 필드 omit (= 새 파일 create)
- **수정** `workers/api/src/lib/skill_md.ts` — `validateFields`에 예약어 검사 (`new`는 reserved slug)

## 4. POST 라우트 동작

```
POST /api/admin/brief-categories
Headers: cookie (admin session)
Body: { fields: SkillFields, body: string }
```

흐름.
1. `requireAdmin` 가드. 실패 → 401
2. `validateFields(payload.fields)` — slug regex + 예약어 + delivery_mode + 필수 필드. 실패 → 422 `{ errors }`
3. server-side 중복 검사. `getFile(${CATEGORIES_PATH}/${slug}/SKILL.md)` 시도.
   - 200 → 422 `{ errors: ["slug already exists"] }`
   - 404 → 계속 진행
   - 그 외 GitHub 에러 → 502
4. `serializeSkillMd({ fields, body })` → text
5. `putFile(token, { path, message: "chore(brief): create ...", contentText: text, actorEmail })` — sha 인자 생략
6. 응답 `{ sha }` (200)

## 5. portal `/admin/brief-categories/new` 페이지

기존 `[slug]/EditForm.tsx`와 동일 구조에 다음 차이.
- slug input 활성 (`required`, regex pattern `[a-z][a-z0-9-]{1,30}`)
- sha hidden field 없음
- 제출 button 라벨 `생성 (GitHub commit)`
- fetch URL `${API_BASE}/api/admin/brief-categories` (POST)
- body에 `sha` 미포함

기본값.
- delivery_mode = `bundled`
- enabled = `false`
- 나머지 placeholder

성공 시 `router.push("/admin/brief-categories")`. 실패 시 인라인 빨간 박스 (기존 패턴).

## 6. 목록 페이지 표 상단 변경

기존.
```tsx
<h1 className="text-xl font-semibold">브리핑 카테고리</h1>
<p ...>services/brief/categories/...</p>
<table ...>
```

변경.
```tsx
<div className="flex items-baseline gap-3">
  <h1 className="text-xl font-semibold">브리핑 카테고리</h1>
  <Link href="/admin/brief-categories/new" className="ml-auto text-sm text-popory-accent">
    + 새 카테고리
  </Link>
</div>
<p ...>services/brief/categories/...</p>
<table ...>
```

## 7. github_contents.ts 변경

`PutFileInput.sha?: string` (optional).

`putFile` 내부 body 직렬화 시.
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

PUT 동작.
- sha 있음 + 파일 존재 → 업데이트
- sha 없음 + 파일 부재 → 새 파일 create (201 응답)
- sha 없음 + 파일 존재 → GitHub 422 "sha required" (우리는 그 전에 server-side 중복 검사로 차단)

## 8. skill_md.ts 변경

예약어 추가.
```ts
const RESERVED_SLUGS = new Set(["new"]); // /admin/brief-categories/new 정적 라우트 충돌 회피

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

## 9. Error handling

| 실패 지점 | 응답 |
|---|---|
| 비admin | 401 |
| validate 실패 (regex·예약어·필수 필드·mode) | 422 `{ errors: [...] }` |
| slug 이미 존재 | 422 `{ errors: ["slug already exists"] }` |
| GitHub PAT 권한 부족 / rate limit | 502 |
| GitHub 5xx | 502 |
| portal client fetch network 실패 | 인라인 빨간 박스 `fetch: ...` |

## 10. Testing

### 10.1 worker route 단위 추가 (`admin_brief_categories.test.ts`)
- POST 정상 — 신규 slug, validate OK, getFile 404, putFile 201 → 200 + sha
- POST slug 중복 — getFile 200 → 422
- POST validate 실패 (slug regex 또는 예약어 또는 필수 필드 누락) → 422
- POST 비admin → 401

### 10.2 skill_md.ts validate 테스트 추가
- 예약어 `new` slug → error

### 10.3 portal smoke
- `pnpm --filter @popory/portal build` 성공 + `ƒ /admin/brief-categories/new` 라우트 등록

## 11. 운영 절차

신규 카테고리 추가 흐름.
1. admin이 `/admin/brief-categories/new` 접속
2. slug (영문 소문자·숫자·하이픈) + name (한글) + delivery_mode + subject_template + sender_name + system prompt body 입력
3. enabled는 일단 false 권장 (본문 검수 후 활성화)
4. [생성] → GitHub commit + 목록 redirect
5. 편집 페이지에서 본문 다듬고 enabled = true 토글
6. portal D1에 admin이 첫 구독자 INSERT (또는 portal 다른 UI)
7. 다음 09:00 KST에 launchd `git pull --ff-only`로 새 SKILL.md 가져와 generate·publish·발송

## 12. 비목표 (재확인)

- 삭제 UI — git에서 직접 `services/brief/categories/{slug}/` 디렉토리 제거 후 commit·push (운영자 작업)
- 카테고리 비활성화 — 기존 편집 페이지 `enabled` 체크박스로 충분
- 첫 구독자 등록 — D1 INSERT 또는 portal 별도 UI (본 amendment 범위 외)
- 신규 카테고리 추가 후 즉시 launchd 트리거 — 다음 09:00 cron에 자동 적용 (수동 트리거는 사용자가 `bash run_daily.sh` 직접 실행)
