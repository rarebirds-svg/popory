<!-- YouTube 영상에 자막형 레이아웃(제목 좌상단+하단 문장 교체)과 생성 옵션(길이·목소리·배경 스타일) 선택을 추가하는 디자인 spec. -->
---
title: popory — 영상 자막 레이아웃 + 생성 옵션
date: 2026-06-07
status: draft
related:
  - docs/superpowers/specs/2026-06-07-video-quality-design.md
---

# 영상 자막 레이아웃 + 생성 옵션 design

## 1. 동기

YouTube 영상을 ① 챕터 제목은 좌상단 고정, 상세 내레이션은 하단에 한 문장씩 교체(자막형)로 바꾸고 ② 생성 시 길이·목소리·배경 스타일을 선택할 수 있게 한다.

## 2. 비목표

- 길이는 3·5·7·10분만(장기 영상의 청크 대본·타임아웃·저작권 리스크 회피 — 검토 결과).
- 누적형 자막·단어별 싱크 없음(문장 단위 교체).
- 이미지 스타일 일관성(시드)·BGM 없음(후속).
- API 라우트 계약·DB 스키마(컬럼) 불변 — 옵션은 기존 `params_json` 재활용.

## 3. 결정 요약

| 항목 | 결정 |
|------|------|
| 레이아웃 | 배경 이미지 + 좌상단 챕터 제목(caption 고정) + 하단 문장 한 줄(교체) + 하단 스크림 |
| 장면→클립 | 장면을 문장 단위로 분할, 문장별 클립(같은 배경·제목, 하단 자막만 교체) |
| 배경 | 장면당 1장(문장마다 재생성 안 함) |
| 길이 | 3/5/7/10분 → 대본 장면 수(약 5/8/12/16) |
| 목소리 | 여성·차분(ko-KR-Neural2-A) / 여성·밝은(Neural2-B) / 남성(Neural2-C). 구현 중 청취로 확정 |
| 배경 스타일 | 실사 / 일러스트 / 수채화 / 미니멀 → image_prompt 키워드 |
| 옵션 저장 | `content_jobs.params_json` 에 `{length, voice, image_style}` JSON |

## 4. 아키텍처

```
[포털 NewJobForm] youtube 선택 시 길이·목소리·배경스타일 드롭다운
  → POST /api/content/jobs { ..., options:{length,voice,image_style} }
[Worker API] params_json = JSON(options)   (현재 NULL → 저장)
  claim 응답 job.params_json 포함(SELECT *)
[로컬 워커] params 파싱:
   length → generate_scenes(scene_count)
   image_style → image_prompt 에 스타일 키워드
   voice → tts.synthesize(text, voice)
   render_video: 장면 → 문장 분할 → 문장별(좌상단 제목 + 하단 자막) 클립 → concat
```

## 5. 컴포넌트별

### 5.1 타입 (`packages/types/src/content_job.ts`)
- `ContentJobCreateSchema` 에 `options` 추가(선택):
  ```ts
  options: z.object({
    length: z.enum(["3", "5", "7", "10"]).optional(),
    voice: z.enum(["female-calm", "female-bright", "male"]).optional(),
    image_style: z.enum(["photo", "illust", "watercolor", "minimal"]).optional(),
  }).optional(),
  ```

### 5.2 작업 생성 라우트 (`workers/api/src/routes/content_jobs.ts`)
- `POST /api/content/jobs` — `params_json` 을 `parsed.data.options ? JSON.stringify(parsed.data.options) : null` 로 저장(현재 하드코딩 NULL 교체).
- 그 외 불변(claim 은 `SELECT *` 라 params_json 포함).

### 5.3 옵션 파싱·매핑 (`services/content/popory_content/options.py` 신규)
- `parse_options(params_json: str|None) -> dict` — JSON 파싱, 기본값(length="5", voice="female-calm", image_style="photo").
- 매핑 상수:
  - `SCENE_COUNT = {"3":5, "5":8, "7":12, "10":16}`.
  - `VOICE = {"female-calm":"ko-KR-Neural2-A","female-bright":"ko-KR-Neural2-B","male":"ko-KR-Neural2-C"}`.
  - `STYLE = {"photo":"photorealistic, cinematic","illust":"digital illustration, clean","watercolor":"watercolor painting","minimal":"minimalist flat design"}`.

### 5.4 대본 프롬프트 (`video_prompt.py`)
- `build_video_system_prompt(style_samples, scene_count=8, image_style_kw="photorealistic, cinematic")` — 장면 수 지시를 파라미터로(고정 6~12 → scene_count). image_prompt 지시에 스타일 키워드 포함.

### 5.5 TTS (`tts.py`)
- `synthesize(text, voice="ko-KR-Neural2-A") -> bytes|None` — voice 인자 추가(기본 유지).

### 5.6 영상 조립 (`video.py`)
- `_split_sentences(narration) -> list[str]` — 문장 분할(마침표/물음표/느낌표 기준, 빈 항목 제거).
- `_render_card(title, subtitle, out_png, bg_image_bytes)`:
  - 좌상단 **제목**(caption) 작게 고정.
  - 하단 **자막**(현재 문장) 한 줄(스크림 위).
- `render_video(scenes, job_id, image_fetcher, voice)`:
  - 장면별 배경 이미지 1장 생성.
  - 장면의 narration 을 문장으로 분할, **문장마다**: `synthesize(sentence, voice)`(폴백 say) → `_render_card(title=caption, subtitle=sentence, bg=장면이미지)` → ffmpeg 클립.
  - 모든 문장 클립 concat.
- `make_video(..., scene_count, image_style_kw, voice)` — 파라미터 전달.

### 5.7 워커 (`worker.py`)
- youtube 분기: `opts = parse_options(job.get("params_json"))` → `make_video(..., scene_count=SCENE_COUNT[opts['length']], image_style_kw=STYLE[opts['image_style']], voice=VOICE[opts['voice']], image_fetcher=...)`.

### 5.8 포털 (`NewJobForm.tsx`)
- youtube 선택 시(platform==='youtube') 길이·목소리·배경 스타일 드롭다운 노출(blog 면 숨김). POST 바디에 `options` 포함.

## 6. 데이터 흐름·계약

- 장면 계약(scenes_json) 불변(caption·narration·image_prompt). 분할은 워커 렌더 단계.
- 옵션은 params_json(문자열) → claim 응답 → 워커 파싱. API 스키마 컬럼 불변.

## 7. 에러 처리

- options 없음/일부 누락 → 기본값. 잘못된 값 → zod 거부(400) 또는 기본값.
- 배경 이미지 실패 → 단색(기존). TTS 실패 → say(기존).
- 문장 0개(빈 narration) → 캡션만 1클립(방어).

## 8. 테스트

- `options.py` pytest — 파싱·기본값·매핑.
- `_split_sentences` pytest — 분할 정확성.
- `video_prompt` — scene_count·스타일 키워드 반영.
- `tts` — voice 인자 전달(요청 바디 voice name 확인, responses).
- `video.py` — `_render_card(title, subtitle)` 렌더, render_video 문장 분할 스모크.
- 라우트 vitest — options → params_json 저장.
- 포털 — typecheck + build(youtube 옵션 UI).

## 9. 미해결·후속

- 보이스 실제 매핑(성별·톤)·속도·피치는 구현 중 청취로 확정.
- 장면 자막이 너무 길면 줄바꿈 처리(문장 길이 상한)는 구현 중 조정.
- 이미지 스타일 일관성·BGM·장기 영상은 후속.
