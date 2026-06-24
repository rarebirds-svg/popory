<!-- 페이스북 릴스 배포 기능 설계 스펙. -->

# 페이스북 릴스 배포 기능 설계

작성일 2026-06-24.

## 목표

popory 콘텐츠 스튜디오에서 생성한 쇼츠(1080×1920 MP4)를 **페이스북 페이지 릴스**로 게시하는 기능을 추가한다. 기존 인스타그램 릴스·유튜브 업로드와 동일한 패턴(사용자 수동 버튼 → 워커 claim → API 게시)을 미러링한다.

## 핵심 결정

- **Meta 앱·자격증명 재사용** — 인스타 연동이 쓰는 `INSTAGRAM_CLIENT_ID/SECRET`(같은 Meta 앱)을 그대로 사용한다. 새 앱·새 client secret 불필요.
- **연결은 독립 페이지** — `/content/facebook` (인스타 연결 페이지 미러).
- **스코프** — `pages_show_list,pages_read_engagement,pages_manage_posts`.
- **토큰 암호화 키** — 새 `FACEBOOK_TOKEN_KEY`(분리 위생). 에이전트가 `wrangler secret put`으로 주입.
- **대상 콘텐츠** — 쇼츠만. 이미 릴스 규격(9:16) 충족.

## 페이스북 릴스 API (검증: Meta Video API, v25.0)

3단계 resumable 업로드, 호스팅 URL(`file_url`) 방식.

1. **start** — `POST https://graph.facebook.com/v23.0/{page_id}/video_reels?upload_phase=start&access_token=...` → `{ video_id, upload_url }`.
2. **upload** — `POST https://rupload.facebook.com/video-upload/v23.0/{video_id}` 헤더 `Authorization: OAuth {page_access_token}`, `file_url: {R2 공개 URL}` (본문 없음).
3. **finish** — `POST https://graph.facebook.com/v23.0/{page_id}/video_reels?upload_phase=finish&video_id=...&video_state=PUBLISHED&description=...&access_token=...`.
4. **status** — `GET https://graph.facebook.com/v23.0/{video_id}?fields=status&access_token=...` 폴링.

필요 권한 `pages_show_list,pages_read_engagement,pages_manage_posts`.

## 구성요소 (각각 기존 파일 미러)

| # | 파일 | 미러 원본 | 내용 |
|---|------|-----------|------|
| 1 | `infra/migrations/0012_facebook.sql` | `0008_instagram.sql` | `facebook_connections` 테이블 + `content_jobs`에 `facebook_status/video_id/error` 컬럼 |
| 2 | `workers/api/src/routes/content_facebook.ts` | `content_instagram.ts` | OAuth connect/callback/status/disconnect. 페이지 토큰 저장 |
| 3 | `workers/api/src/routes/content_facebook_upload.ts` | `content_instagram_upload.ts` | upload 요청 / claim-upload / result |
| 4 | `services/content/popory_content/facebook_upload.py` | `instagram_upload.py` | 릴스 3단계 업로드 |
| 5 | `services/content/popory_content/worker.py` | (편집) | `run_facebook_upload_once` 추가 + 메인 루프 연결 |
| 6 | `apps/portal/src/app/(authed)/content/[id]/FacebookUpload.tsx` | `InstagramUpload.tsx` | 상세 페이지 업로드 버튼 |
| 7 | `apps/portal/src/app/(authed)/content/facebook/page.tsx` + `DisconnectButton.tsx` | `instagram/*` | 연결 관리 페이지 |
| 8 | `apps/portal/.../content/[id]/page.tsx` | (편집) | `facebook_*` 필드·연결조회·버튼 렌더 |
| 9 | `apps/portal/.../content/new/NewJobForm.tsx` | (편집) | 쇼츠 업로드 대상에 페이스북 체크박스(기본 on) |
| 10 | `workers/api/src/types.ts` + `app.ts` | (편집) | `FACEBOOK_TOKEN_KEY` Env, 라우트 마운트 |

## connect/callback 흐름 (content_facebook.ts)

`content_instagram.ts`와 동일하되 callback에서 페이지 토큰을 저장한다.

1. `/connect` → FB OAuth dialog, scope에 `pages_manage_posts` 포함.
2. `/callback` → code → 단기 토큰 → `fb_exchange_token`으로 장기 user 토큰.
3. `GET me/accounts?fields=id,name,access_token&access_token={장기user토큰}` → 첫 페이지의 `id`(page_id)·`name`·`access_token`(페이지 토큰) 사용.
4. 페이지 토큰을 `FACEBOOK_TOKEN_KEY`로 암호화해 `facebook_connections`에 저장.

다중 페이지는 첫 항목 사용(인스타와 동일, YAGNI).

## DB 스키마

```sql
CREATE TABLE facebook_connections (
  sub TEXT PRIMARY KEY REFERENCES users(sub) ON DELETE CASCADE,
  page_id TEXT NOT NULL,
  page_name TEXT NOT NULL,
  enc_token TEXT NOT NULL,
  connected_at INTEGER NOT NULL
);
ALTER TABLE content_jobs ADD COLUMN facebook_status TEXT;
ALTER TABLE content_jobs ADD COLUMN facebook_video_id TEXT;
ALTER TABLE content_jobs ADD COLUMN facebook_error TEXT;
```

## 상태 흐름

`facebook_status`: `null → requested → uploading → done/failed` (인스타와 동일).

## 테스트·검증

- 라우트 유닛테스트(connect/upload) — 기존 `content_instagram*.test.ts` 미러.
- 포털 타입체크·빌드.
- end-to-end 게시는 Meta 앱 `pages_manage_posts` 활성화 + 본인 페이지 연결 필요. 본인 관리 페이지면 개발 모드에서 게시 가능(현재 IG와 동일).

## YAGNI 제외

다중 페이지 선택 UI, 일반 동영상(비릴스) 게시, 예약 게시.
