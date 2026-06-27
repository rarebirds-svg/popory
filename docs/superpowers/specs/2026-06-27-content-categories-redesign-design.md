<!-- 컨텐츠 목록 카테고리 우선 재설계(스케일·다카테고리·채널바인딩 자리) 설계 문서. -->

# 컨텐츠 목록 카테고리 우선 재설계

작성일 2026-06-27.

## 목표

컨텐츠 관리 목록 페이지를 **카테고리 우선 2단 구조**로 재설계한다. 콘텐츠 수가 계속 늘고(스케일), 책 리뷰 외에 영화 후기·역사 이야기 등 새 카테고리가 추가되며(다카테고리), 카테고리마다 다른 유튜브/인스타 채널에 배포될 수 있다(채널 바인딩)는 점을 반영한다.

이번 범위 = **A(목록 UI/UX·스케일) + B(카테고리 데이터모델·그룹핑)**. **C(카테고리별 채널 연결·다채널 배포)는 데이터모델 자리만** 마련하고 실제 OAuth·배포는 후속 슬라이스로 둔다.

## 비목표

- 카테고리별 다채널 OAuth 연결·업로드(C 실구현). 컬럼만 두고 UI는 "미연결" 표시까지.
- 카테고리별 자동화(추천·생성). recommend_weekly·auto_create는 당분간 **책 리뷰 카테고리에만** 작동. 다른 카테고리는 수동 생성.
- 상태/플랫폼 필터. v1은 **텍스트 검색 + 더 보기(load more)** 까지. 필터는 fast-follow.

## 정보 구조 (확정)

**1단 — `/content` 카테고리 홈.** 카테고리 카드 그리드. 각 카드 = 아이콘·이름 + 연결 채널 요약(유튜브/인스타, 지금은 대부분 "미연결") + 콘텐츠 수·진행중 수. 상단에 `[+ 카테고리]`·`[+ 콘텐츠]`. "전체 보기"도 제공.

**2단 — `/content/c/[id]` 카테고리 상세.** 상단에 그 카테고리의 채널 섹션(`[채널 설정]` 자리) → 검색창 + 콘텐츠 목록(주제 그룹 + 레거시 작업, 더 보기 페이지네이션) → 그 카테고리의 추천 컨텐츠.

기존 단일 목록(`/content`)의 주제/레거시/추천 렌더는 카테고리 상세로 이동한다.

## 데이터모델 (마이그레이션 `0013_content_categories.sql`)

신규 테이블.

```sql
CREATE TABLE content_categories (
  id            TEXT PRIMARY KEY,
  owner_sub     TEXT NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  slug          TEXT NOT NULL,
  icon          TEXT,                  -- 이모지 1자 (선택)
  sort_order    INTEGER NOT NULL DEFAULT 0,
  youtube_channel_id     TEXT,         -- C 자리(다채널 배포). v1 미사용 nullable
  youtube_channel_title  TEXT,
  instagram_account_id   TEXT,
  instagram_username     TEXT,
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL
);
CREATE UNIQUE INDEX idx_content_cat_owner_slug ON content_categories(owner_sub, slug);
```

기존 3개 테이블에 `category_id TEXT REFERENCES content_categories(id)` 추가(nullable). SQLite는 ADD COLUMN 가능하므로 테이블 재생성 불필요.

```sql
ALTER TABLE content_topics          ADD COLUMN category_id TEXT REFERENCES content_categories(id);
ALTER TABLE content_jobs            ADD COLUMN category_id TEXT REFERENCES content_categories(id);
ALTER TABLE content_recommendations ADD COLUMN category_id TEXT REFERENCES content_categories(id);
CREATE INDEX idx_content_topics_cat ON content_topics(category_id, created_at DESC);
CREATE INDEX idx_content_jobs_cat   ON content_jobs(category_id, created_at DESC);
CREATE INDEX idx_content_rec_cat    ON content_recommendations(category_id, status);
```

**백필.** 마이그레이션 적용 후 운영 스크립트로 owner별 "책 리뷰" 카테고리를 시드하고 기존 topics·jobs·recommendations의 `category_id`를 그 카테고리로 채운다(코드가 아닌 운영 단계, 본문 §배포 참조). 시드 slug=`book-review`, name=`책 리뷰`, icon=`📚`.

`category_id` NULL 콘텐츠는 백필로 해소되고, 모든 신규 생성 경로가 category_id를 세팅하므로 "미분류" 카드는 렌더하지 않는다(의도적으로 제거됨).

## Backend 엔드포인트

모두 기존 `requireAuth`(사용자) 패턴. owner 격리 필수.

**카테고리 CRUD** (`content_categories.ts`, 신규 라우트 파일)
- `GET /api/content/categories` → 카테고리 목록 + 각 카운트(content_topics+레거시 jobs 수, 진행중 수) + 채널 바인딩. sort_order, created_at 순.
- `POST /api/content/categories` `{name, icon?}` → slug 자동 생성(이름 기반, 충돌 시 suffix), 201 {id}.
- `PATCH /api/content/categories/:id` `{name?, icon?, sort_order?}`.
- `DELETE /api/content/categories/:id` → 콘텐츠가 있으면 409(거부) + 안내. 비었을 때만 삭제(데이터 유실 방지).

**기존 라우트에 category 스코프 + 페이지네이션 추가**
- `GET /api/content/topics?category_id=&q=&limit=&offset=` → category_id로 필터, q는 topic LIKE, limit(기본 20)·offset로 더 보기. `{topics, has_more}` 반환.
- `GET /api/content/jobs?category_id=&q=&limit=&offset=`(레거시 standalone, topic_id IS NULL) 동일.
- `GET /api/content/recommendations?category_id=` → 카테고리별 pending.
- 생성 시 category_id 수용. `POST /api/content/topics`·`POST /api/content/jobs`·`POST /api/content/jobs/service-create`·추천 bulk/service-bulk에 `category_id`(또는 service는 `category_slug`) 추가.

**스키마(@popory/types).** 카테고리 zod 스키마(`CategoryCreateSchema`, `CategoryPatchSchema`) 신규. 기존 생성 스키마에 `category_id`(optional) 추가.

## 자동화 (책 리뷰 고정)

- recommend_weekly·auto_create는 책 리뷰 카테고리에만 작동. 서비스가 슬러그로 카테고리를 찾도록 service-bulk/service-create에 `category_slug="book-review"` 전달(서버가 slug→id 해석, 없으면 무시하고 NULL). known-titles도 책 리뷰 스코프로 좁힐 수 있으나 v1은 owner 전체 유지(중복 방지 우선).

## UI 컴포넌트

- `/content/page.tsx` → **카테고리 홈**으로 교체. 서버 컴포넌트가 `GET /categories` 호출 → 카드 그리드. `CategoryCard`(이름·아이콘·채널요약·카운트), `CreateCategory`(인라인/모달 생성), 기존 상단 nav(생성 상태·스타일·YouTube·Instagram) 유지.
- `/content/c/[id]/page.tsx` → **카테고리 상세**(신규). 채널 섹션(`CategoryChannels`, 컬럼값 읽어 "연결됨/미연결" 표시, 설정 버튼은 C 자리) + `ContentList`(검색 input + 주제/레거시 목록 + `LoadMore` 클라이언트 컴포넌트) + 추천 섹션(기존 `RecommendationActions`·`BulkAddRecommendations` 재사용, 카테고리 스코프).
- `ContentList`/`LoadMore`: 클라이언트 컴포넌트. 초기 20건 SSR, "더 보기"가 offset 증가시켜 `GET /topics?...offset=` 추가 fetch·append. 검색은 입력 디바운스 후 offset 리셋 재조회.
- `new/NewJobForm.tsx`: 카테고리 선택 드롭다운 추가(진입 시 쿼리 `?category=`로 기본 선택). 카테고리 미선택 불가(기본=책 리뷰).
- 기존 status/styles/youtube/instagram 페이지는 유지(전역). 카테고리별 채널 설정은 C에서 분기.

## 파일 구조

- 신규. `workers/api/src/routes/content_categories.ts`(+test), `packages/types/src/content_category.ts`(+test), `infra/migrations/0013_content_categories.sql`, `apps/portal/src/app/(authed)/content/c/[id]/page.tsx`·`ContentList.tsx`·`CategoryChannels.tsx`, `apps/portal/src/app/(authed)/content/CategoryCard.tsx`·`CreateCategory.tsx`.
- 수정. `content_topics.ts`·`content_jobs.ts`·`content_recommendations.ts`(category 스코프·페이지네이션·생성 수용), `content/page.tsx`(홈 교체), `new/NewJobForm.tsx`(카테고리 선택), `recommend_weekly.py`·`auto_create.py`(category_slug 전달).

## 에러·엣지

- 카테고리 0개(첫 진입): 홈이 "책 리뷰" 시드를 안내하거나 자동 생성 후 표시. 백필이 시드를 만들므로 정상 운영에선 최소 1개 존재.
- category_id NULL 콘텐츠: 백필과 신규 생성 경로 category_id 상속으로 발생하지 않아 "미분류" 카드는 렌더하지 않는다.
- 카테고리 삭제는 빈 경우만(409 가드) — 콘텐츠 유실 방지.
- 페이지네이션: has_more=false면 "더 보기" 숨김. 검색 중 결과 0건이면 안내문.

## 테스트

- vitest. 카테고리 CRUD(생성·slug중복 suffix·빈것만 삭제 409·owner격리), topics/jobs/recommendations의 category 필터·페이지네이션(limit/offset·has_more)·q 검색.
- vitest(types). Category 스키마.
- pytest. recommend_weekly·auto_create가 category_slug를 페이로드에 싣는지.
- 포털. 빌드·typecheck. (UI 상호작용은 휴먼 e2e.)

## 배포·셋업 (구현 후)

1. `0013_content_categories.sql` prod D1 적용.
2. 워커 재배포(새 라우트·스키마).
3. 포털 재배포(`wrangler pages deploy`).
4. **백필**(1회, prod D1). owner별 책 리뷰 카테고리 INSERT → 기존 topics·jobs·recommendations의 category_id를 그 id로 UPDATE. 단일 owner 환경이라 수동 SQL로 충분.

## 롤백

포털·워커 이전 버전 재배포. category_id는 nullable이라 구버전 코드도 무시하고 동작(컬럼 잔존 무해). 마이그레이션은 되돌리지 않음(가산적).

## 후속 (C 및 그 외)

- **C. 카테고리별 채널 연결**. youtube_connections·instagram_connections를 카테고리 스코프로 확장, 카테고리 상세 `[채널 설정]`에서 OAuth 연결, 업로드 claim이 카테고리의 채널 토큰 사용. 별도 스펙.
- 상태/플랫폼 필터, 카테고리별 자동화(전용 프롬프트), 카테고리 정렬 드래그.
