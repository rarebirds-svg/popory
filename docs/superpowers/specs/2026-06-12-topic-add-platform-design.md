# 주제 상세에서 플랫폼(컨텐츠 유형) 추가 설계

작성일: 2026-06-12

## 배경·목적

주제 그룹(`content_topics`)의 작업(플랫폼별 `content_jobs`)은 **주제 생성 시점에 고른 플랫폼으로만** 만들어진다. 생성 후 주제 상세 페이지(`/content/topics/[id]`)에서 빠진 컨텐츠 유형(예: 인스타 쇼츠, 인스타 이미지 캐러셀)을 나중에 추가할 방법이 없다.

이 설계는 주제 상세 페이지에서 **아직 만들어지지 않은 컨텐츠 유형을 추가**할 수 있게 한다. 추가된 작업은 기존과 동일하게 `idle`로 생성되어 "생성 시작" 버튼으로 돌린다.

비목표: 기존 작업의 옵션 수정·삭제, 주제 자체 편집. 생성 폼(`NewJobForm`) 리팩터링.

## 도메인 모델 결정

- **작업 플랫폼은 4종**: `naver-blog`, `youtube`, `shorts`, `instagram-image`. (생성 폼 UI의 5개 체크박스 중 "유튜브 쇼츠"·"인스타 쇼츠"는 둘 다 `shorts` 플랫폼 1종으로, `options.upload_targets` 배열로 대상을 구분한다.)
- **이미 있는 유형은 추가 불가**: 주제에 특정 플랫폼 작업이 이미 있으면 그 유형은 비활성화. `shorts`가 있으면 "유튜브 쇼츠"·"인스타 쇼츠" 둘 다 비활성화한다(shorts 1종 원칙).
- 추가 작업의 초기 상태는 `idle` — 주제 생성과 동일. 사용자가 상세에서 "생성 시작"으로 `queued` 전환.

## API — `POST /api/content/topics/:id/jobs`

`workers/api/src/routes/content_topics.ts`의 `mountContentTopics`에 추가.

- 인증: `requireAuth`. 주제 owner 격리 — `content_topics`에서 `id`로 조회해 `owner_sub !== u.sub`이면 404.
- body 스키마(신규 `TopicAddJobsSchema`, `@popory/types`):
  ```typescript
  {
    platforms: TopicPlatform[],        // 기존 TopicPlatformSchema 배열, min 1 max 5
    style_profile_id?: string,          // 선택. 있으면 owner 소유 확인
  }
  ```
- 동작:
  1. 주제 존재·owner 확인(404 분기).
  2. `style_profile_id` 있으면 `SELECT id FROM style_profiles WHERE id=? AND owner_sub=?` 확인(없으면 404).
  3. 주제의 기존 작업 플랫폼 집합 조회: `SELECT DISTINCT platform FROM content_jobs WHERE topic_id=?`.
  4. 요청 `platforms` 중 **기존 집합에 없는 것만** 골라 `idle` 작업으로 INSERT(생성 폼과 동일한 컬럼: `id, owner_sub, topic, platform, status='idle', style_profile_id, params_json, topic_id, created_at, updated_at`). `topic`은 주제의 topic 문자열을 그대로 복사. `params_json`은 `platform.options`를 JSON 직렬화. `D1.batch`로 일괄.
  5. 응답 `{ added_job_ids: string[], skipped_platforms: string[] }` (201).
- 빈 결과(모두 이미 있음): `added_job_ids` 빈 배열로 201.

> 같은 주제에 같은 플랫폼이 2개 생기지 않도록 서버가 skip을 강제한다(UI 비활성화와 이중 가드).

## UI — `AddPlatformForm.tsx` (신규)

위치: `apps/portal/src/app/(authed)/content/topics/[id]/AddPlatformForm.tsx`. `"use client"`.

- props: `{ topicId: string; existingPlatforms: string[]; profiles: { id: string; name: string }[] }`.
- 생성 폼(`NewJobForm`)의 플랫폼 체크박스 + 옵션 패널 UI를 **자체 구현으로 재현**한다(공유 컴포넌트 추출 안 함 — NewJobForm 회귀 위험 회피). 옵션 enum·라벨 등 순수 상수는 공유 가능하면 작은 상수 모듈로 분리해 중복을 줄인다.
  - 체크박스 5종: 네이버 블로그 / 유튜브 동영상 / 유튜브 쇼츠 / 인스타 쇼츠(릴스) / 인스타 이미지(캐러셀).
  - 옵션 패널: 유튜브(길이·목소리·배경), 쇼츠(길이·목소리·배경 + 업로드 대상은 체크된 유튜브쇼츠/인스타쇼츠로 결정), 인스타 이미지(슬라이드 수).
  - 스타일 프로필 드롭다운(선택).
- **비활성화 판정**(`existingPlatforms` 기준):
  - `naver-blog` 포함 → "네이버 블로그" disable.
  - `youtube` 포함 → "유튜브 동영상" disable.
  - `shorts` 포함 → "유튜브 쇼츠"·"인스타 쇼츠" 둘 다 disable.
  - `instagram-image` 포함 → "인스타 이미지" disable.
  - 추가 가능한 유형이 하나도 없으면 폼 대신 "추가할 유형이 없습니다" 안내.
- 제출: 체크된 항목을 생성 폼과 동일 규칙으로 `platforms` 배열로 변환(유튜브쇼츠·인스타쇼츠는 하나의 `shorts` + `upload_targets`로 합침) → `POST /api/content/topics/:id/jobs` (`credentials: "include"`) → 성공 시 `router.refresh()`. 실패 시 상태코드 노출.
- 중복 클릭 방지(`busy`/`disabled`).

## 상세 페이지 수정 — `topics/[id]/page.tsx`

- 서버 컴포넌트에서 스타일 프로필 목록을 추가 fetch(`/api/content/style-profiles`, 생성 폼과 동일 소스). 기존 topic fetch와 `Promise.all`로 병렬.
- 작업 그리드(`<div className="mt-8 grid ...">`) 아래에 `<AddPlatformForm topicId={topic.id} existingPlatforms={topic.jobs.map(j => j.platform)} profiles={profiles} />` 렌더.

## 컴포넌트 경계

| 단위 | 책임 | 생성/수정 |
|---|---|---|
| `TopicAddJobsSchema`(@popory/types) | 추가 요청 zod 스키마 | 생성(content_job.ts에 추가) |
| `content_topics.ts` `POST /:id/jobs` | 주제에 누락 플랫폼 작업 추가 | 수정 |
| `content_topics.test.ts` | 추가·skip·격리·검증 테스트 | 수정 |
| `AddPlatformForm.tsx` | 유형 추가 폼(비활성화 판정 포함) | 생성 |
| `topics/[id]/page.tsx` | 프로필 fetch + 폼 렌더 | 수정 |

## 테스트

API Vitest(`content_topics.test.ts`에 추가):
- 기존 주제(naver-blog만)에 `youtube` 추가 → 201, `added_job_ids` 1개, 해당 작업이 `idle`·`topic_id` 연결·`params_json` 저장.
- 이미 있는 플랫폼(naver-blog) 재요청 → skip(`skipped_platforms`에 포함, 새 작업 안 생김).
- 타인 주제에 추가 → 404.
- 존재하지 않는 `style_profile_id` → 404.
- 잘못된 body(빈 platforms) → 400.

UI는 타입체크(`tsc --noEmit`)로 검증. 비활성화·제출 변환 로직은 기존 NewJobForm 규칙과 동일하므로 수동 확인.

## 구현·검증 순서

1. `TopicAddJobsSchema` 추가 → `tsc`(types).
2. API 엔드포인트 + 테스트(TDD) → Vitest green.
3. `AddPlatformForm.tsx` + 상세 페이지 수정 → portal `tsc`.
4. 전체 회귀(workers/api vitest, types·portal tsc).

배포: API `wrangler deploy`, 포털 Pages 빌드·배포.
