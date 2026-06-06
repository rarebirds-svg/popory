<!-- 컨텐츠 관리 YouTube 영상 생성 Slice 1 — claude 대본 + macOS say TTS + ffmpeg 텍스트카드 슬라이드쇼로 MP4를 만드는 디자인 spec. -->
---
title: popory — YouTube 영상 생성 (Video Slice 1, 텍스트카드 슬라이드쇼)
date: 2026-06-06
status: draft
related:
  - docs/superpowers/specs/2026-06-05-content-studio-naver-design.md
  - docs/superpowers/specs/2026-06-06-content-studio-rich-html-design.md
---

# YouTube 영상 생성 design (Video Slice 1)

## 1. 동기

네이버 블로그 외에 **YouTube용 영상 파일**을 생성한다. claude는 텍스트만 만들므로, 로컬 워커가 claude 대본 + macOS `say`(한국어 TTS) + `ffmpeg`(텍스트 카드 슬라이드쇼)로 MP4를 조립한다. 첫 슬라이스는 이미지 없는 **텍스트 카드 슬라이드쇼**로 파이프라인을 끝까지 검증하고, 이후 AI 이미지 슬라이드로 고도화한다.

## 2. 비목표 (이번 제외)

- **스톡/AI 이미지 슬라이드 없음.** 텍스트 카드만(후속).
- **YouTube 자동 업로드 없음.** MP4는 R2 저장 + 포털 미리보기까지(업로드는 Slice 2 자동배포).
- **음악·효과음·전환 효과 없음.**
- **단어별 자막 싱크 없음.** 장면 단위 자막.
- **영상 편집 UI 없음.** 재생성만(실패 시 retry).
- **유료 TTS 없음.** macOS `say`.

## 3. 결정 요약

| 항목 | 결정 |
|------|------|
| 영상 스타일 | 텍스트 카드 슬라이드쇼(헤드라인 + 하단 자막 + 내레이션) |
| 대본 | claude → 장면 배열 `[{caption, narration}]` + 메타(제목·설명·태그) |
| TTS | macOS `say -v Yuna`(한국어, 무료·로컬), 장면별 음성 |
| 조립 | ffmpeg drawtext(한국어 폰트) + 장면 concat → 1080p 16:9 MP4 |
| 플랫폼 | 기존 작업에 `platform=youtube` 추가, 워커가 분기 |
| 영상 저장 | 워커가 `PUT /api/content/jobs/:id/video`(서비스 JWT)로 R2 `content/video/{id}.mp4` |
| 표시 | 포털 상세에서 `<video>` 플레이어 + 대본 |

## 4. 아키텍처

```
[포털 새 작업] platform 선택(naver-blog | youtube)
      ▼ POST /api/content/jobs
[Worker API] content_jobs(platform=youtube, queued)
      ▲ claim ▼
[로컬 워커] platform 분기:
   blog   → 기존 HTML 생성 → PATCH /result(draft=HTML)
   youtube→ claude 대본(scenes) → say TTS → ffmpeg MP4
            → PUT /:id/video (MP4 → R2) → PATCH /result(draft=대본, status=review)
      ▼
[포털 상세] youtube면 <video src="GET /:id/video"> + 대본 / blog면 기존 HTML 미리보기
```

## 5. 컴포넌트별

### 5.1 타입 (`packages/types/src/content_job.ts`)
- `ContentJobCreateSchema.platform` 을 `z.literal("naver-blog")` → `z.enum(["naver-blog", "youtube"]).default("naver-blog")` 로 변경. `StyleProfileCreateSchema.platform` 은 그대로(스타일은 블로그용).

### 5.2 대본 프롬프트 (`services/content/popory_content/video_prompt.py` 신규)
- system prompt — YouTube 영상 대본 작성 지시. 장면 6~12개, 각 `{caption(짧은 헤드라인), narration(2~4문장)}`. 자연스러운 한국어.
- 출력 계약 — `<scenes_json>[{"caption":"...","narration":"..."}]</scenes_json>` + `<video_meta>{"title","description","tags":[...]}</video_meta>`.
- `build_video_system_prompt(style_samples)` + `build_video_user_message(topic, sources)`.

### 5.3 대본 파서 (`services/content/popory_content/video_contract.py` 신규)
- `parse_video(text) -> (scenes: list[dict], meta: dict)`. `<scenes_json>`·`<video_meta>` 정규식 추출 + JSON 파싱. 누락/파싱 실패 시 `ContractError`(기존 재사용).

### 5.4 영상 조립 (`services/content/popory_content/video.py` 신규)
- `render_video(scenes, job_id) -> Path`:
  - 장면별. `say -v Yuna -o /tmp/{job}_{i}.aiff "{narration}"` → `ffprobe`로 길이.
  - 장면별 클립. ffmpeg `lavfi`(배경) + `drawtext`(헤드라인 중앙 + narration 하단 자막) + 오디오, `-t {dur}` → `/tmp/{job}_{i}.mp4`.
  - concat(파일 리스트) → `/tmp/{job}.mp4`(libx264, yuv420p, 1920x1080).
  - 한국어 폰트. `/System/Library/Fonts/AppleSDGothicNeo.ttc`(없으면 대체 탐색).
  - 실패 시 `VideoError`(메시지에 ffmpeg/say stderr 포함).
- `CLAUDE_BIN`처럼 `SAY_BIN`·`FFMPEG_BIN`·`FFPROBE_BIN` 상수.

### 5.5 워커 분기 (`services/content/popory_content/worker.py`)
- `run_once` 에서 `job["platform"]` 확인:
  - `youtube` → `_run_youtube(client, job)`: 대본 생성(video_prompt+claude+video_contract) → `render_video` → MP4 바이트를 `PUT /api/content/jobs/{id}/video` → `_report(review, draft=대본요약/스크립트)`.
  - 그 외 → 기존 `generate`(HTML) 흐름.
- 실패는 기존대로 failed 회신.
- claude 호출은 기존 `generate.py` 패턴 재사용(별도 `generate_video` 추가 또는 generate에 prompt 주입). 본 spec은 `video.py`에 대본 생성까지 포함하지 않고, 워커가 claude CLI 호출을 조율.

### 5.6 Worker API (`workers/api/src/routes/content_jobs.ts`)
- `PUT /api/content/jobs/:id/video` — `requireService`, area=content-worker. 요청 본문(MP4 바이너리)을 R2 `content/video/{id}.mp4`(contentType video/mp4)에 저장. 200.
- `GET /api/content/jobs/:id/video` — `requireAuth`, 소유자. R2에서 스트리밍 반환(contentType video/mp4). 없으면 404.
- result/PATCH 등 기존 라우트 변경 없음.

### 5.7 포털
- 새 작업 폼(`NewJobForm.tsx`) — platform 선택 추가(naver-blog | youtube). youtube면 스타일/시드 동일 사용.
- 상세 페이지(`[id]/page.tsx`) — `job.platform === "youtube"` 이고 status review/done이면 `<video src="${API_BASE}/api/content/jobs/${id}/video" controls>` + 대본(draft) 표시. 아니면 기존 DraftEditor.

## 6. 데이터 흐름·계약

- 워커 claim 응답에 `job.platform` 포함(이미 `SELECT *`라 포함됨).
- youtube 결과. 영상=R2(`content/video/{id}.mp4`), 대본=`draft`(텍스트), meta_json=video_meta(title/description/tags).
- `GET /:id` 응답의 `platform`으로 포털이 분기.

## 7. 에러 처리

- `say`/`ffmpeg`/`ffprobe` 비정상 종료 → `VideoError`(stderr 포함) → 워커 failed 회신(stdout/stderr 진단 포함, 기존 패턴).
- 대본 계약 위반 → `ContractError` → failed.
- 생성 시간 길어도 워커 타임아웃(1200초) 내. 초과 시 timeout→failed.
- MP4 업로드 실패(PortalError) → `_report` 가 swallow(작업 running 잔류) + 로그. (기존 회신 실패 처리와 동일 철학)

## 8. 테스트

- `video_prompt.py` pytest — system prompt에 scenes_json·video_meta·한국어 지시 포함.
- `video_contract.py` pytest — scenes_json·video_meta 추출, 누락 시 ContractError.
- `video.py` — ffmpeg/say 통합이라 단위테스트 대신 **2장면 스모크**(짧은 narration → 실제 MP4 생성 확인, 로컬 e2e 단계).
- API vitest — PUT/GET video(서비스 JWT·소유자·R2 라운드트립·404).
- 포털 — typecheck + build(플랫폼 선택·영상 플레이어 분기).

## 9. 미해결·후속

- 장면 이미지(텍스트 카드 → AI 생성/스톡)·BGM·전환 효과.
- 자막 정밀 싱크(현재 장면 단위).
- YouTube 자동 업로드(Slice 2).
- 워커 단일 스레드 — 영상 생성 중 다른 작업 장시간 대기. 다중화는 후속.
- 한국어 폰트 경로가 환경마다 다를 수 있어 구현 시 실제 확인.
