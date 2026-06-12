# 추천 컨텐츠 (Recommended Content) 설계

작성일: 2026-06-12

## 배경·목적

현재 포털의 `/content` 화면은 사용자가 직접 만든 "내 컨텐츠"(주제 그룹 + 레거시 단독 작업)만 보여준다. 사용자가 "다음에 다룰 만한" 책·주제를 미리 모아두고, 시스템이 기존 컨텐츠 패턴을 분석해 주기적으로 후보를 제안하는 **추천 컨텐츠** 레인이 없다.

이 설계는 다음을 추가한다.

- 계정별로 분리된 **추천 컨텐츠** 목록 — "내 컨텐츠"와 시각적·데이터적으로 분리.
- 추천자 표기 — 사용자가 직접 올린 것은 `대공`, 시스템이 생성한 것은 `시스템`.
- 사용자 직접 추가(단건·벌크), 수정, 삭제, 숨김.
- 추천 항목을 실제 주제로 등록(`/content/new` 연동).
- 매주 토요일 03:00 KST에 기존 컨텐츠를 LLM으로 검토해 10~15건을 자동 추천하는 launchd 잡.

비목표: 추천 항목 자체의 본문 생성·발행은 하지 않는다. 추천은 "주제 후보"일 뿐이며, 등록 시 기존 `content_topics` 생성 흐름으로 넘어간다.

## 데이터 모델

신규 마이그레이션 `infra/migrations/0010_content_recommendations.sql`.

```sql
-- 계정별 추천 컨텐츠(주제 후보) 테이블
CREATE TABLE content_recommendations (
  id          TEXT    PRIMARY KEY,
  owner_sub   TEXT    NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  title       TEXT    NOT NULL,
  author      TEXT,
  recommender TEXT    NOT NULL,              -- 표기 라벨: '대공' | '시스템'
  status      TEXT    NOT NULL DEFAULT 'pending', -- pending | registered | dismissed
  note        TEXT,
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL
);
CREATE INDEX idx_content_rec_owner ON content_recommendations(owner_sub, status);
CREATE UNIQUE INDEX idx_content_rec_owner_title ON content_recommendations(owner_sub, title);
```

- `owner_sub` — 계정별 분리의 축. 모든 사용자 API는 본인 행만 접근.
- `recommender` — 화면 배지에 그대로 노출되는 라벨. 사용자 경유 등록은 `대공`, 주간 잡 등록은 `시스템`. (확장 대비 자유 문자열이되 현재 두 값만 사용.)
- `status`
  - `pending` — 목록에 노출.
  - `registered` — 추천 → 주제로 등록 완료. 목록에서 빠지되 이력으로 행 유지(중복 재추천 방지).
  - `dismissed` — 사용자가 "숨김". 목록에서 빠지되 행 유지(같은 책 재추천 방지).
- `UNIQUE(owner_sub, title)` — 같은 계정에 같은 제목 중복 금지. 벌크·주간 잡의 중복 자동 skip 근거.
- **삭제(delete)** 는 행을 물리적으로 제거 — 숨김과 달리 같은 책이 추후 다시 추천될 수 있다. 숨김(dismiss)과 삭제(delete)를 둘 다 제공한다.

## API — `workers/api/src/routes/content_recommendations.ts`

`app.ts`에 `mountContentRecommendations` 추가. ULID 헬퍼·`now` 패턴은 `content_topics.ts`와 동일.

### 사용자 세션 인증 (requireAuth)

- `GET /api/content/recommendations`
  본인 `pending` 목록을 `created_at DESC`로 반환. `{ recommendations: [...] }`.

- `POST /api/content/recommendations`
  단건 추가. body `{ title, author?, note? }`. recommender=`대공`, status=`pending`. 같은 제목이 이미 있으면 409.

- `POST /api/content/recommendations/bulk`
  벌크 추가. body `{ items: [{ title, author?, note? }] }` 또는 `{ text: "한 줄에 한 권..." }`.
  - `text` 형식: 한 줄당 `제목 - 저자`. 마지막 ` - ` 기준으로 제목/저자 분리(제목에 하이픈이 있을 수 있으므로 rsplit). 빈 줄 무시.
  - recommender=`대공`. 기존 토픽 제목(content_topics·레거시 content_jobs) 및 기존 추천과 중복이면 skip.
  - `D1.batch()`로 일괄 INSERT(부분 실패 방지). 응답 `{ added: n, skipped: m, skipped_titles: [...] }`.

- `PATCH /api/content/recommendations/:id`
  본인 행의 `title`·`author`·`note` 수정. 제목 변경 시 `UNIQUE` 충돌이면 409. `updated_at` 갱신.

- `DELETE /api/content/recommendations/:id`
  본인 행 물리 삭제. 200.

- `POST /api/content/recommendations/:id/dismiss`
  본인 행 `status='dismissed'`. 목록에서 빠지되 행 유지.

### 서비스 인증 (requireService) — 주간 잡 전용

- `POST /api/content/recommendations/service-bulk`
  body `{ owner_sub, items: [{ title, author?, note? }] }`. recommender=`시스템`.
  - 서비스 토큰(ES256, brief publish와 동일한 서명 키 인프라)으로 인증. 호출자가 대상 `owner_sub`를 명시.
  - 중복 skip 로직은 사용자 벌크와 공유(내부 헬퍼). 응답 동일 형태.

> 사용자 벌크와 서비스 벌크를 라우트로 분리하는 이유: 인증 미들웨어(requireAuth vs requireService)와 owner_sub 출처(세션 sub vs body)가 다르기 때문. 중복 검사·INSERT 코어는 공유 함수로 둔다.

### 주제 등록 연동 (`content_topics.ts` 수정)

`POST /api/content/topics`가 201로 성공한 직후, 같은 `owner_sub`·같은 `topic`(== 추천 title)의 `pending` 추천이 있으면 `status='registered'`로 UPDATE. 이 UPDATE는 주제 생성 batch와 **별개의 후속 쿼리**로, 실패해도 주제 생성 자체는 성공으로 둔다(추천 상태 동기화는 부가 기능).

## UI — `apps/portal/src/app/(authed)/content/`

### `/content` 페이지 (`page.tsx` 수정)

기존 "내 컨텐츠"(topics + legacyJobs) 렌더 아래에 **"추천 컨텐츠"** 섹션 추가. 서버 컴포넌트에서 `GET /api/content/recommendations`를 병렬 fetch.

- 섹션 헤더: `Kicker`로 "추천 컨텐츠" + 우측에 **[여러 개 추가]** 버튼.
- 각 행: `제목` — `저자`(있으면) — 추천자 배지(`대공`/`시스템`, 색 구분) — 우측 액션 [등록] [수정] [숨김] [삭제].
- 빈 상태: "아직 추천 컨텐츠가 없습니다." 안내.

기존 디자인 토큰(`text-popory-fg`/`text-popory-muted`/`border-popory-border` 등) 사용. 배지 색은 기존 `StatusBadge` 팔레트 재사용(대공=accent 계열, 시스템=muted 계열).

### 상호작용 컴포넌트 (클라이언트)

`runtime = "edge"` 서버 페이지 + 액션은 작은 클라이언트 컴포넌트로 분리(기존 `StartJobButton` 패턴):

- `RecommendationActions.tsx` — 등록/수정/숨김/삭제 버튼. 각 API 호출 후 `router.refresh()`.
  - [등록] → `router.push("/content/new?topic=" + encodeURIComponent(title + (author ? " - " + author : "")))`.
  - [수정] → 인라인 편집(제목·저자·메모) → `PATCH`.
  - [숨김] → `POST .../dismiss`. [삭제] → `DELETE`(확인 후).
- `BulkAddRecommendations.tsx` — [여러 개 추가] 클릭 시 텍스트영역 토글. 붙여넣기 → `POST .../bulk { text }` → 결과(added/skipped) 토스트 → refresh.

### `/content/new` 수정 (필요)

현재 `new/page.tsx`는 `searchParams`를 읽지 않고 `NewJobForm`에 주제 초기값을 넘기지 않는다. 다음을 추가한다.
- `page.tsx`가 `searchParams: Promise<{ topic?: string }>`를 받아 `NewJobForm`에 `initialTopic` prop으로 전달.
- `NewJobForm`이 `initialTopic`을 주제 입력 필드의 기본값으로 사용.

사용자는 폼에서 플랫폼·옵션을 직접 골라 등록.

## 초기 시드 — 사용자 제공 책 목록

주신 약 95줄의 목록을 1회성 시드로 주입한다.

- **중복 제거**: 강방천의 관점(2), 사피엔스(2), 붙잡지 않는 삶(2) 등 동일 제목 1건으로 축약.
- **기존 등록 제외**: 이미 `content_topics`/레거시에 있는 제목(강방천의 관점·가슴이 뛰는 한 나이는 없다·Zero to One/제로 투 원·사피엔스 등)은 API의 중복 skip이 자동 처리.
- **방법**: 목록을 `제목 - 저자` 텍스트로 정리해 사용자 세션 벌크 API(`POST .../bulk { text }`)로 주입. recommender=`대공`. 별도 시드 스크립트 없이 벌크 경로 재사용(= 기능 자체의 통합 검증도 겸함).
- "미상" 저자는 author=null로.

## 주간 시스템 추천 잡 — Mac launchd

기존 brief·content-worker와 동일한 호스트(맥미니 launchd) + claude CLI(Claude Max 구독, LLM 비용 $0) 패턴.

### 구성

- **트리거**: `~/Library/LaunchAgents/com.popory.content-recommend.plist`. `StartCalendarInterval` 매주 토요일(Weekday=7) 03:00 KST. 레포 사본 `services/content/com.popory.content-recommend.plist`.
- **entry**: `services/content/recommend_weekly.sh` → secrets source 후 `python -m popory_content.recommend_weekly` 실행.
- **본문 로직** (`services/content/popory_content/recommend_weekly.py`):
  1. 포털 API에서 대상 계정 목록 확보 — 토픽이 1개 이상 있는 owner_sub. (현재는 사실상 대공 계정 1개. MVP는 단일 계정 고정도 허용하되, 토픽 보유 계정 순회 구조로 작성.)
  2. 각 계정에 대해 기존 토픽 제목 + 기존 추천 제목을 읽는다.
  3. claude CLI(`--print --model claude-sonnet-4-6 --allowed-tools WebSearch WebFetch`)로 "이미 다룬 컨텐츠 목록을 줄 테니, 겹치지 않으면서 같은 독자층이 좋아할 책/주제 **10~15건**을 `제목 | 저자` 형식으로"를 생성. 출력 계약은 brief와 동일하게 XML 태그(`<recommendations>...</recommendations>`)로 감싸 regex 추출.
  4. 파싱 결과를 `POST /api/content/recommendations/service-bulk { owner_sub, items }`로 등록(recommender=`시스템`). 중복은 서버가 skip.
  5. 로그 1줄(`services/content/logs/YYYY-MM-DD.log` 또는 전용 로그).
- **인증**: brief와 동일한 ES256 서비스 키(`POPORY_*_KEY_FILE`)로 area 토큰 발급. recommend 잡 전용 area 라벨(예: `content-recommend`) 사용.

### 실패 모드

- Claude Max 5시간 윈도우 공유 — 한도 시 해당 주 skip(다음 주 재시도). brief의 한도 마커 감지·백오프 패턴 참고.
- 태그 누락(파싱 실패) 시 해당 계정 skip + 로그. 부분 성공 허용.

## 컴포넌트 경계 요약

| 단위 | 책임 | 의존 |
|---|---|---|
| `0010_content_recommendations.sql` | 테이블·인덱스 정의 | D1 |
| `content_recommendations.ts` | 추천 CRUD·벌크·서비스 벌크 API | DB, 인증 미들웨어 |
| `content_topics.ts`(수정) | 주제 등록 시 추천 상태 동기화 | content_recommendations 테이블 |
| `page.tsx`(수정) | 추천 섹션 렌더 | recommendations API |
| `RecommendationActions.tsx` | 행 액션(등록/수정/숨김/삭제) | 추천 API |
| `BulkAddRecommendations.tsx` | 벌크 입력·파싱 | bulk API |
| `recommend_weekly.py` | 주간 LLM 추천 생성·등록 | claude CLI, service-bulk API |
| `com.popory.content-recommend.plist` | 토요일 03:00 트리거 | launchd |

## 구현·검증 순서

1. 마이그레이션 0010 → `wrangler d1 migrations apply`(local·remote). verify: 테이블 존재.
2. API + Vitest(`content_recommendations.test.ts`) — CRUD·벌크 중복 skip·계정 격리·서비스 인증. verify: 테스트 green.
3. `content_topics.ts` 등록 동기화 + 테스트. verify: 추천 status 전이.
4. UI(page.tsx·두 클라이언트 컴포넌트). verify: 로컬에서 추천 노출·액션 동작.
5. 초기 시드 벌크 주입. verify: 목록에 ~90건 노출, 기존 등록분 skip.
6. 주간 잡(py·sh·plist) + launchctl load. verify: `--now` 수동 1회 실행 시 시스템 추천 등록.

배포: API는 `wrangler deploy`(prod), 포털은 Pages 빌드·배포, 잡은 `launchctl load`.
