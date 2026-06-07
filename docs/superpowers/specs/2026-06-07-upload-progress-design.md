<!-- YouTube 업로드 진행상태(스피너+경과시간, 자체 폴링)를 상세 페이지에 표시하는 디자인 spec. -->
---
title: popory — 업로드 진행상태 표시
date: 2026-06-07
status: draft
related:
  - docs/superpowers/specs/2026-06-07-youtube-upload-design.md
---

# 업로드 진행상태 표시 design

## 1. 동기

"YouTube에 업로드(비공개)" 클릭 후 완료까지 진행상태가 "업로드 중…" 한 줄뿐이라 답답하다. 스피너 + 경과시간으로 진행을 정직하게 보여주고, 전체 새로고침 없이 자체 폴링으로 부드럽게 갱신한다.

## 2. 비목표

- 정확한 바이트 % 진행률 없음(단일 전송이라 측정 불가 — 가짜 % 금지).
- 백엔드 변경 없음(기존 `GET /api/content/jobs/:id` 가 youtube_status·video_id·error 포함).

## 3. 결정 요약

| 항목 | 결정 |
|------|------|
| 표현 | 스피너 + "올리는 중… (N초 경과)" + 완료/실패 |
| 갱신 | 자체 폴링(3초) + 경과 타이머(1초). 전체 새로고침 제거 |
| 범위 | `YoutubeUpload.tsx` 한 파일 + page.tsx 의 업로드 AutoRefresh 제거 |

## 4. 컴포넌트 (`YoutubeUpload.tsx`)

- props: `jobId, connected, initialStatus, initialVideoId, initialError`.
- state: `status, videoId, error, elapsed`.
- 진행 상태(`requested`|`uploading`)이면:
  - `useEffect` 폴링 — 3초마다 `GET /api/content/jobs/${jobId}`(credentials include) → `youtube_status`/`youtube_video_id`/`youtube_error` 로 state 갱신. `done`/`failed` 되면 폴링 정지.
  - `useEffect` 타이머 — 1초마다 `elapsed += 1`.
- `request()` — POST `/:id/youtube-upload` → ok 면 `setStatus("requested")`, elapsed 0 으로 시작.
- 렌더:
  - `!connected` → "YouTube 연결 먼저" 링크.
  - `requested` → ⟳ "업로드 준비 중… (N초 경과)".
  - `uploading` → ⟳ "YouTube에 올리는 중… (N초 경과)".
  - `done`+videoId → "✓ 업로드 완료(비공개) → YouTube에서 보기"(youtu.be 링크).
  - `failed` → 에러 + "다시 시도" 버튼.
  - 그 외(미업로드) → "YouTube에 업로드(비공개)" 버튼.

## 5. page.tsx

- `YoutubeUpload` 에 `initialStatus`/`initialVideoId`/`initialError` props 로 전달(이름만 변경).
- 업로드용 `AutoRefresh` 줄 제거(컴포넌트 자체 폴링).

## 6. 에러·엣지

- 페이지 로드 시 이미 `uploading` 이면 마운트 시 폴링·타이머 시작(경과는 로드 시점부터 — 근사).
- 폴링 fetch 실패는 무시(다음 주기 재시도).
- 언마운트·상태 종료 시 인터벌 정리.

## 7. 테스트

- 포털 typecheck + build. e2e — 업로드 눌러 스피너·경과·완료 전환 확인.
