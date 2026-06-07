<!-- 업로드 시 공개범위 선택 저장 + 완료 후 YouTube 스튜디오 공개전환 딥링크(앱 감사 전 비공개 강제 전제) 디자인 spec. -->
---
title: popory — YouTube 공개범위 선택 + 공개 전환 헬퍼
date: 2026-06-07
status: draft
related:
  - docs/superpowers/specs/2026-06-07-youtube-upload-design.md
---

# YouTube 공개범위 + 공개 전환 헬퍼 design

## 1. 동기

업로드가 비공개 고정이라 "공개" 경로가 없다. ① 업로드 시 공개범위를 선택·저장하고 ② 완료 후 YouTube 스튜디오로 가는 원클릭 "공개로 전환" 딥링크를 제공한다.

## 2. 제약 (전제)

YouTube API 감사 미통과 앱은 업로드 영상이 **비공개로 강제**된다. `privacyStatus=public`을 보내도 감사 전까지 비공개. 따라서 선택값은 **저장·전송만**(감사 통과 시 자동 적용)이고, 지금 공개는 스튜디오에서 사용자가 수동 전환한다.

## 3. 비목표

- 감사 신청 자동화 없음(별도 외부 절차).
- API 강제 공개 없음(감사 전 불가).

## 4. 결정 요약

| 항목 | 결정 |
|------|------|
| 공개범위 | public / unlisted / private, 기본 public |
| 저장 | content_jobs 신규 컬럼 youtube_privacy (마이그레이션 0006) |
| 업로드 | worker 가 privacyStatus=선택값 전송(감사 전엔 비공개 강제) |
| 전환 헬퍼 | 완료 후 `studio.youtube.com/video/{id}/edit` 딥링크 + 안내 |

## 5. 컴포넌트별

### 5.1 D1 (`infra/migrations/0006_youtube_privacy.sql`)
```sql
ALTER TABLE content_jobs ADD COLUMN youtube_privacy TEXT;
```

### 5.2 youtube-upload 라우트 (`content_youtube_upload.ts`)
- `POST /:id/youtube-upload` body `{privacy?: "public"|"unlisted"|"private"}`. zod 미사용 영역이라 인라인 검증: 허용값 외/누락 → "public". `youtube_privacy` 저장 + 기존 조건·requested 전이.
- `claim-upload` 응답에 `privacy: youtube_privacy ?? "public"` 추가(SELECT 에 컬럼 포함).

### 5.3 업로드 모듈 (`youtube_upload.py`)
- `upload(access_token, mp4_bytes, title, description, tags, privacy="private") -> str` — `status.privacyStatus = privacy`.

### 5.4 worker (`worker.py`)
- `run_upload_once` — `upload(..., privacy=data.get("privacy", "public"))`.

### 5.5 포털 (`YoutubeUpload.tsx`)
- 대기(미업로드) 상태: 공개범위 `<select>`(공개/일부공개/비공개, 기본 공개) + 업로드 버튼. POST body 에 `privacy` 포함.
- 완료 상태: "YouTube에서 보기"(youtu.be) + **"공개로 전환"**(`https://studio.youtube.com/video/{videoId}/edit`, 새 탭) + "앱 감사 전이라 현재 비공개입니다" 안내.

## 6. 데이터 흐름

- privacy: 포털 select → youtube-upload 저장 → claim-upload 반환 → worker → privacyStatus.
- youtube_privacy 컬럼은 claim 의 `SELECT ... meta_json` 옆에 추가 조회.

## 7. 에러·엣지

- privacy 누락/오값 → "public" 기본.
- 감사 전 업로드는 비공개 강제 — 완료 화면이 항상 공개전환 링크·안내 노출.

## 8. 테스트

- 라우트 vitest — youtube-upload 가 privacy 저장(public 기본·지정값), claim-upload 응답은 외부(토큰교환)라 저장 검증까지.
- 워커 pytest — youtube_upload privacyStatus 반영(요청 바디 검증), run_upload_once 가 privacy 전달.
- 포털 — typecheck + build.

## 9. 후속

- YouTube API 감사 신청(통과 시 선택 "공개"가 실제 API 공개로 자동 동작).
