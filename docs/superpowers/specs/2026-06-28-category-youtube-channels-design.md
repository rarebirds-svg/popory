<!-- 카테고리별 유튜브 채널 연결·업로드 라우팅(C 슬라이스) 설계 문서. -->

# 카테고리별 유튜브 채널 (C)

작성일 2026-06-28.

## 목표

카테고리마다 다른 유튜브 채널에 게시할 수 있게 한다. 각 카테고리 상세에서 그 카테고리 전용 유튜브 채널을 OAuth로 연결하고, 그 카테고리의 영상·쇼츠 업로드는 그 채널로 간다. 예: 책 리뷰 → 포포리 책방, 영화 후기 → 별도 채널.

[[project-content-studio]]의 카테고리 재설계(2026-06-28) 후속. 그 재설계에서 마련한 `content_categories.youtube_channel_id/title` "자리"를 실제로 채운다.

## 비목표

- 인스타그램 카테고리별 연결. 유효한 Meta 앱이 없어 런타임 검증 불가(별도, Meta 앱 생성 후).
- Google 앱 검증. 미검증 앱이라 업로드는 채널 수와 무관하게 비공개 강제(공개 전환은 기존대로 수동/검증 후).
- 채널 라이브러리(공유). 카테고리마다 직접 연결(한 채널을 여러 카테고리가 공유하는 모델은 채택 안 함).
- 계정단위 레거시 `/content/youtube` 페이지 제거. 그대로 둔다(레거시, C와 공존).

## 핵심 설계 결정

- **카테고리마다 직접 OAuth 연결.** 각 카테고리 상세의 "채널 설정"에서 그 채널 Google 계정으로 연결.
- **기존 OAuth 콜백 재사용 → 새 redirect URI 불필요.** KV state를 `{sub, category_id}` JSON으로 확장하고, 기존 `/api/content/youtube/callback`이 category_id 유무로 분기. Google 콘솔 변경(외부 설정) 없음.
- **업로드는 폴백 없이 카테고리 채널만.** 카테고리에 연결이 없으면 업로드를 거부한다(계정단위로 폴백하면 영화 후기가 포포리 책방에 잘못 올라가는 사고 발생).
- **암호화 토큰 격리.** refresh_token은 신규 테이블에만, 표시용 채널명/ID는 content_categories에.

## 데이터모델 (마이그레이션 `0014_category_youtube.sql`)

```sql
CREATE TABLE category_youtube_tokens (
  category_id   TEXT PRIMARY KEY REFERENCES content_categories(id) ON DELETE CASCADE,
  refresh_token TEXT NOT NULL,     -- AES-GCM 암호화(YOUTUBE_TOKEN_KEY), youtube_connections와 동일 키
  connected_at  INTEGER NOT NULL
);
```

표시용 채널 식별자는 기존 `content_categories.youtube_channel_id`·`youtube_channel_title` 컬럼을 쓴다(0013에서 추가됨). GET /categories는 이 테이블(토큰)을 절대 읽지 않는다.

## Backend

### 연결 시작 (카테고리별)
`GET /api/content/categories/:id/youtube/connect` (`requireAuth`)
- 카테고리 소유 확인. KV에 `oauth:youtube:state:{state}` = `JSON.stringify({ sub, category_id })` 저장(TTL 기존과 동일).
- 기존 connect와 동일한 Google 인가 URL(같은 redirect_uri `${PUBLIC_BASE_URL}/api/content/youtube/callback`, 같은 SCOPE, access_type offline, prompt consent) 로 302.

### 콜백 분기 (기존 라우트 수정)
`GET /api/content/youtube/callback` (`content_youtube.ts` 수정)
- KV state 값을 읽어 파싱. `JSON.parse` 성공 + `category_id` 있으면 **per-category**, 아니면(평문 sub 문자열) **레거시 계정단위**(현행 그대로).
- per-category 경로. category가 sub 소유인지 확인 → refresh_token·channel 조회(기존 로직 재사용) → `content_categories.youtube_channel_id/title` UPDATE + `category_youtube_tokens` INSERT OR REPLACE(암호화 토큰) → `${PORTAL_ORIGIN}/content/c/{category_id}?connected=1` 로 리다이렉트.
- 레거시 경로. 기존 youtube_connections 동작·리다이렉트 유지.

### 연결 해제 (카테고리별)
`DELETE /api/content/categories/:id/youtube` (`requireAuth`)
- 소유 확인 → `content_categories` youtube_channel_id/title NULL UPDATE + `category_youtube_tokens` 행 삭제 → 204.

### 업로드 라우팅 (수정)
- `POST /api/content/jobs/:id/youtube-upload` (사용자): 현재 `youtube_connections WHERE sub` 체크를 **잡의 category_id로 category_youtube_tokens 존재 확인**으로 교체. 없으면 400 "이 카테고리에 유튜브 채널을 연결하세요". (잡에 category_id가 없으면 동일 400.)
- `POST /api/content/youtube/claim-upload` (서비스): refresh_token을 `youtube_connections WHERE sub`가 아니라 **잡의 category_id → category_youtube_tokens.refresh_token**에서 가져와 access_token 교환. 토큰 없으면 그 잡을 youtube_status=failed + error="카테고리 유튜브 미연결"로 기록하고 다음으로(204).

### GET /categories 폴백 제거
2026-06-28 임시로 넣은 계정단위 표시 폴백(`youtube_connections`/`instagram_connections`로 채우기)을 **제거**한다. 이제 카드/상세는 `content_categories`의 자체 바인딩만 표시(책 리뷰=포포리 책방, 영화 후기=미연결). 폴백이 영화 후기에 포포리 책방을 잘못 보여주던 문제도 해소.

## 마이그레이션 (배포 단계, 1회)

기존 계정 연결(포포리 책방)을 책 리뷰 카테고리에 이전.
- `content_categories.youtube_channel_id/title` ← `youtube_connections`(owner)의 channel_id/title.
- `category_youtube_tokens(book-review-cat-id, refresh_token, connected_at)` ← `youtube_connections`의 암호화 refresh_token **그대로 복사**(같은 YOUTUBE_TOKEN_KEY라 복호화 불필요).
- 따라서 책 리뷰 업로드는 끊김 없이 동작. 레거시 youtube_connections 행은 남겨둠(전역 페이지용).

## UI

카테고리 상세(`/content/c/[id]`) 채널 섹션을 표시 전용 → **연결 액션 포함**으로 교체.
- 신규 클라이언트 컴포넌트 `CategoryYoutube`: 연결됨(category.youtube_channel_title 존재)이면 "유튜브: {채널명} [연결 해제]"(해제는 DELETE 호출 후 refresh), 미연결이면 "[유튜브 채널 연결]"(링크 `/api/content/categories/{id}/youtube/connect`).
- `CategoryChannels`는 유튜브 줄을 `CategoryYoutube`로 대체, 인스타 줄은 "미연결" 표시 유지(범위 밖).
- 콜백이 `/content/c/{id}?connected=1`로 돌아오므로 상세에서 결과 확인.

## 파일 구조

- 신규. `infra/migrations/0014_category_youtube.sql`, `apps/portal/src/app/(authed)/content/c/[id]/CategoryYoutube.tsx`.
- 수정. `workers/api/src/routes/content_youtube.ts`(콜백 분기), `content_categories.ts`(connect 시작·disconnect 라우트 추가 + GET 폴백 제거), `content_youtube_upload.ts`(업로드 라우팅을 카테고리 토큰으로), `apps/portal/.../c/[id]/CategoryChannels.tsx`(유튜브 줄 교체)·`page.tsx`(필요 시 category id 전달).

## 에러·엣지

- 카테고리 미연결 상태로 업로드 시도 → 400 + 안내(사용자), claim 단계에서도 토큰 없으면 failed 기록.
- 같은 Google 계정을 두 카테고리에 연결 → 각자 자기 토큰 보유(중복 무해). 다른 채널은 OAuth 계정 선택으로 분기.
- 콜백 state 만료/위조 → 기존 error 리다이렉트 재사용.
- 카테고리 삭제(빈 경우만, 0013) 시 `category_youtube_tokens`는 ON DELETE CASCADE로 정리.
- 미검증 앱 → 업로드 비공개 강제(불변).

## 테스트

- vitest. 콜백 분기(category_id 있는 state → category_youtube_tokens 기록 + content_categories 갱신 / 평문 sub → 레거시 경로). 카테고리 connect 시작(state JSON·소유확인·302), disconnect(토큰·컬럼 정리·소유격리). 업로드: 카테고리 토큰 없으면 youtube-upload 400; claim이 카테고리 토큰으로 access 교환. GET /categories 폴백 제거 후 자체 바인딩만 반환.
- 포털. 빌드·typecheck. (OAuth 왕복은 휴먼 e2e.)

## 배포·셋업

1. `0014_category_youtube.sql` prod D1 적용.
2. 마이그레이션 데이터 이전(책 리뷰 ← 포포리 책방, 위 SQL).
3. 워커 재배포(콜백 분기·업로드 라우팅·카테고리 라우트).
4. 포털 재배포(CategoryYoutube).
5. 휴먼 e2e. 책 리뷰 상세 = "유튜브: 포포리 책방" + 해제 버튼 / 영화 후기 = "유튜브 채널 연결" 버튼 → 다른 채널 계정으로 OAuth → 연결 확인 → 영화 잡 업로드가 그 채널로.

## 롤백

워커·포털 이전 버전 재배포. `category_youtube_tokens`·content_categories 컬럼은 가산적이라 잔존 무해. 업로드 라우팅을 되돌리면 youtube_connections(계정단위)로 복귀.

## 후속

- 인스타 카테고리별 연결(Meta 앱 생성 후).
- 레거시 전역 `/content/youtube` 페이지 정리(카테고리 모델로 일원화).
- Google 앱 검증 → 업로드 공개 허용.
