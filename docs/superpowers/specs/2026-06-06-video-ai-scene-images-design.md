<!-- YouTube 영상의 장면 배경을 Cloudflare Workers AI(flux)로 생성한 이미지로 채우는 디자인 spec. -->
---
title: popory — 영상 AI 장면 이미지 (Workers AI flux)
date: 2026-06-06
status: draft
related:
  - docs/superpowers/specs/2026-06-06-youtube-video-generation-design.md
---

# 영상 AI 장면 이미지 design

## 1. 동기

YouTube 영상(텍스트카드 슬라이드쇼)의 장면 배경을 단색에서 **AI 생성 이미지**로 바꿔 품질을 높인다. Cloudflare Workers AI(`@cf/black-forest-labs/flux-1-schnell`)를 Worker `[ai]` 바인딩으로 호출한다(토큰 권한 불필요, 무료 티어).

## 2. 비목표 (이번 제외)

- **이미지 스타일 일관성(시드·캐릭터 고정) 없음.** 장면별 독립 생성.
- **사용자 이미지 업로드 없음.**
- **BGM·전환 효과 없음.**
- **YouTube 자동 업로드 없음(Slice 2).**
- **외부 이미지 API 없음.** Cloudflare Workers AI만.

## 3. 결정 요약

| 항목 | 결정 |
|------|------|
| 이미지 생성 | Worker `[ai]` 바인딩 → `env.AI.run("@cf/black-forest-labs/flux-1-schnell", {prompt})` |
| 생성 위치 | Worker 엔드포인트 `POST /api/content/ai-image`(서비스 JWT) → PNG 바이트 반환 |
| 장면 프롬프트 | claude 가 장면별 `image_prompt`(영어) 생성. 선택값(없으면 단색 폴백) |
| 합성 | Pillow — AI 이미지 풀블리드 배경 + 어두운 오버레이 + 텍스트(헤드라인·자막) |
| 폴백 | 이미지 생성/누락 실패 시 기존 단색 카드 |
| 의존성 | video.py 는 포털 모름 — 워커가 `image_fetcher` 주입 |

## 4. 아키텍처

```
[로컬 워커] youtube 작업
  generate_scenes(claude) → 장면[{caption, narration, image_prompt}]
  make_video(image_fetcher=…)
    장면별: image_fetcher(image_prompt) ──POST /api/content/ai-image──▶ [Worker env.AI flux] → PNG bytes
            Pillow 합성(배경 이미지 + 오버레이 + 텍스트) → 카드 PNG
            say 내레이션 + ffmpeg → 클립
    concat → MP4 → PUT /:id/video
```

## 5. 컴포넌트별

### 5.1 Worker 바인딩·타입 (`infra/wrangler/api.toml`, `workers/api/src/types.ts`)
- `api.toml` 기본 + `[env.prod]` 에 AI 바인딩 추가:
  ```toml
  [ai]
  binding = "AI"
  ```
  (prod 는 `[env.prod.ai]` 블록.)
- `Env` 인터페이스에 `AI: Ai;` 추가(`Ai` 타입은 `@cloudflare/workers-types`).

### 5.2 이미지 라우트 (`workers/api/src/routes/content_ai_image.ts` 신규)
- `POST /api/content/ai-image` — `requireService`, area=content-worker. 본문 `{prompt: string}`.
- `const out = await c.env.AI.run("@cf/black-forest-labs/flux-1-schnell", { prompt })`. flux 응답은 `{ image: base64 }`. base64 디코드 → `new Response(bytes, { headers: { "content-type": "image/png" } })`.
- 빈/긴 prompt 검증(1~1500자). `app.ts` 에 mount.

### 5.3 대본 프롬프트·파서 (`video_prompt.py`, `video_contract.py`)
- `video_prompt` — 장면에 `image_prompt`(영어, 장면 분위기 묘사) 추가 지시. 출력 계약 scene = `{caption, narration, image_prompt}`.
- `video_contract` — caption·narration 필수 유지, image_prompt 는 선택(검증 안 함).

### 5.4 합성·조립 (`video.py`)
- `post_for_bytes` 로 받은 이미지 바이트를 `_render_card(caption, narration, out_png, bg_image_bytes=None)` 에 전달.
  - bg_image_bytes 있으면: PIL 로 열어 1920×1080 cover-crop → 어두운 반투명 오버레이(예: 검정 45%) → 텍스트.
  - 없으면: 기존 단색 배경 + 텍스트.
- `render_video(scenes, job_id, image_fetcher=None)` — 장면별 `img = image_fetcher(scene.get("image_prompt")) if image_fetcher and scene.get("image_prompt") else None`. image_fetcher 예외/None 은 폴백.
- `make_video(*, topic, sources, style_samples, job_id, image_fetcher=None)`.

### 5.5 포털 클라이언트·워커 (`portal_client.py`, `worker.py`)
- `portal_client` — `post_for_bytes(path, *, json) -> bytes`: JSON POST, 바이너리 응답 반환(`resp.content`). 4xx/5xx → PortalError.
- `worker.py` youtube 분기 — `image_fetcher = lambda p: _safe_image(client, p)` 를 만들어 `make_video` 에 주입. `_safe_image` 는 `client.post_for_bytes("/api/content/ai-image", json={"prompt": p})` 호출, 어떤 예외든 None 반환(영상은 폴백으로 완성).

## 6. 에러 처리

- 이미지 생성 실패(AI 오류·한도·네트워크) → 해당 장면 단색 폴백. 영상 전체는 성공.
- `env.AI` 미설정/바인딩 누락 → 라우트 500이지만 `_safe_image` 가 None 처리 → 폴백.
- 장면당 flux 수 초 → 영상 생성 시간 증가. 워커 타임아웃 1200초 내.

## 7. 테스트

- `video_prompt` pytest — image_prompt 지시 포함.
- `video_contract` pytest — image_prompt 있는 scene 파싱, 없어도 통과.
- `video.py` pytest — `_render_card` 가 bg_image_bytes(작은 가짜 PNG) 있을 때/없을 때 PNG 생성. `render_video` 가 image_fetcher 주입받아 폴백(None 반환)으로도 MP4 생성(스모크).
- API vitest — `POST /api/content/ai-image` 인증(서비스 JWT·area)·검증. `env.AI` 는 테스트에서 stub(`{ image: <base64> }` 반환) 으로 주입 가능하면 PNG 반환까지, 아니면 인증·검증까지.
- 포털 변경 없음.

## 8. 미해결·후속

- `[ai]` 바인딩 실동작은 prod 배포 후 e2e 로 최종 검증(로컬 miniflare 에 실제 AI 없음).
- 스타일 일관성(시드 고정)·이미지 캐싱은 후속.
- flux 무료 티어 한도 초과 시 동작은 운영 중 관측.
