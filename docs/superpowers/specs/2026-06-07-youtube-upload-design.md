<!-- Slice 2-B: 생성된 YouTube 영상을 멤버 채널에 비공개 업로드(수동 버튼)하는 디자인 spec. -->
---
title: popory — YouTube 업로드 (Slice 2-B)
date: 2026-06-07
status: draft
related:
  - docs/superpowers/specs/2026-06-06-youtube-connect-design.md
  - docs/superpowers/specs/2026-06-06-youtube-video-generation-design.md
---

# YouTube 업로드 design (Slice 2-B)

## 1. 동기

연결(2-A)된 멤버 채널에, 생성된 영상을 **수동 버튼**으로 업로드한다. 로컬 워커가 R2의 MP4를 받아 YouTube Data API(resumable)로 올린다.

## 2. 비목표

- **공개 업로드 없음.** 미검증 앱이라 Google 이 업로드 영상을 **비공개로 강제**. privacyStatus=private 고정. 공개·앱검증은 후속.
- **썸네일 업로드 없음**(YouTube 자동).
- **자동 업로드 없음**(수동 버튼만).
- **재시도 UI 최소**(실패 시 다시 버튼).

## 3. 결정 요약

| 항목 | 결정 |
|------|------|
| 업로드 주체 | 로컬 워커(REST resumable). CF Worker 직접 업로드는 시간·용량 제한 회피 |
| 트리거 | 상세 페이지 "YouTube에 업로드" 버튼(연결·영상 있을 때) |
| 가시성 | private 고정(미검증 앱 제약) |
| 메타 | 작업 meta_json 의 title/description/tags |
| 상태 추적 | content_jobs 신규 컬럼 youtube_status·youtube_video_id·youtube_error (마이그레이션 0005) |
| 토큰 | Worker 가 refresh→access 교환(키·refresh token 은 Worker 에만). 워커엔 access_token 만 전달 |
| MP4 다운로드 | GET /:id/video 를 서비스 JWT 도 허용 |

## 4. 아키텍처

```
[상세] youtube·review/done·연결됨 → "YouTube에 업로드"
  → POST /api/content/jobs/:id/youtube-upload (쿠키, 소유자) → youtube_status='requested'
[워커 업로드 폴링] POST /api/content/youtube/claim-upload (서비스 JWT)
  → requested 1건 원자 claim(uploading)
  → 소유자 refresh token 복호화 → Google token(grant_type=refresh_token) → access_token
  → { job_id, title, description, tags, access_token } 반환
  → 워커: GET /:id/video(서비스 JWT)로 MP4 → youtube_upload.upload(access_token, bytes, meta) → video_id
  → PATCH /api/content/jobs/:id/youtube-result (서비스) → done+video_id (또는 failed+error)
[상세] done 이면 "YouTube에서 보기"(https://youtu.be/{id}, 비공개) / failed 면 에러+다시 버튼
```

## 5. 컴포넌트별

### 5.1 D1 (`infra/migrations/0005_youtube_upload.sql`)
```sql
ALTER TABLE content_jobs ADD COLUMN youtube_status TEXT;
ALTER TABLE content_jobs ADD COLUMN youtube_video_id TEXT;
ALTER TABLE content_jobs ADD COLUMN youtube_error TEXT;
```

### 5.2 Worker API (`workers/api/src/routes/content_youtube_upload.ts` 신규)
- `POST /api/content/jobs/:id/youtube-upload` — requireAuth, 소유자. 조건: 작업 platform='youtube', R2 영상 존재(`content/video/{id}.mp4`), 사용자 youtube_connections 존재. 충족 시 `UPDATE content_jobs SET youtube_status='requested'`. 미연결/영상없음 → 400/409.
- `POST /api/content/youtube/claim-upload` — requireService, area content-worker. 원자 claim(`UPDATE … SET youtube_status='uploading' WHERE youtube_status='requested'` 가장 오래된 1건). 작업 소유자의 refresh token 복호화 → Google `oauth2/token`(grant_type=refresh_token, client_id/secret) → access_token. meta_json 에서 title/description/tags. 반환 `{job_id, title, description, tags, access_token}`. 없으면 204. 토큰 교환 실패 → youtube_status='failed'+error 후 204.
- `PATCH /api/content/jobs/:id/youtube-result` — requireService. body `{status:"done", video_id}` 또는 `{status:"failed", error}` → 컬럼 갱신.
- `GET /api/content/jobs/:id/video`(기존, content_jobs.ts) 수정 — 쿠키 소유자 외 **서비스 JWT(area content-worker)** 도 허용(워커 다운로드).
- `app.ts` mount.

### 5.3 로컬 워커
- `youtube_upload.py` 신규 — `upload(access_token, mp4_bytes, title, description, tags) -> str(video_id)`:
  - resumable 시작 `POST https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status` (Bearer, body snippet/status privacyStatus=private, 헤더 X-Upload-Content-Type/Length) → Location.
  - `PUT {location}` 바이트 → 응답 `id`.
  - 실패 → `UploadError`.
- `worker.py` — 업로드 폴링 추가. `run_upload_once(client)`: `POST /api/content/youtube/claim-upload` → 없으면 False. 있으면 GET /:id/video(서비스) → upload → `PATCH /:id/youtube-result done+video_id` (실패 시 failed+error). `main()` 루프: 생성 claim 없으면 업로드 claim 시도, 둘 다 없으면 sleep.
- `portal_client.py` — `get_bytes(path) -> bytes`(서비스 GET 바이너리).

### 5.4 포털 (`apps/portal/src/app/(authed)/content/[id]/`)
- youtube·review/done 인 영상 블록에 업로드 영역 추가(`YoutubeUpload.tsx` client):
  - GET status(youtube_status)·연결여부에 따라: 미연결 → "YouTube 연결 먼저" 링크. 연결+미업로드 → "YouTube에 업로드" 버튼(POST). requested/uploading → "업로드 중…"(자동 새로고침). done → "YouTube에서 보기" 링크(비공개 안내). failed → 에러+다시.
- 상세 page.tsx 가 job 의 youtube_status·youtube_video_id 를 내려줌(GET /:id 응답에 포함 — SELECT \* 라 자동).

## 6. 데이터 흐름·계약

- youtube_status 상태기계: null → requested(버튼) → uploading(claim) → done|failed(result).
- claim-upload 응답의 access_token 은 단명(워커가 즉시 업로드에 사용). refresh token·키는 Worker 에만.
- GET /:id 응답에 youtube_status·youtube_video_id 포함(포털 분기).

## 7. 에러 처리

- 채널 없음/권한 만료 → 업로드 REST 4xx → youtube-result failed+error → 상세 표시.
- 토큰 교환 실패 → claim 단계에서 failed.
- 업로드 중 워커 크래시 → uploading 잔류(후속에 타임아웃 리셋. 지금은 수동 재요청).
- 비공개 고정 안내 문구 표시.

## 8. 테스트

- 라우트 vitest — youtube-upload(소유자·연결·영상조건·상태전이), claim-upload(서비스·원자 claim, 토큰교환은 외부라 인증·claim까지), youtube-result, GET video 서비스 JWT 허용.
- 워커 pytest — youtube_upload REST 모킹(resumable 2단계 → video_id), run_upload_once 분기(mock client).
- 포털 — typecheck + build.

## 9. 외부 설정

- 추가 없음(2-A 에서 스코프·redirect·API 완료). 단 **업로드하려는 Google 계정에 YouTube 채널이 존재**해야 함(없으면 업로드 실패).

## 10. 미해결·후속

- 공개 전환·앱 검증, 썸네일, 자동 업로드, uploading 잔류 타임아웃 리셋은 후속.
