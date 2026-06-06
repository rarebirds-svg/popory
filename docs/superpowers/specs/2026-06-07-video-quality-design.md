<!-- YouTube 영상 품질 개선 — Google Cloud TTS 자연 음성, 이미지 합성 경량화, 화면 자막 축소 디자인 spec. -->
---
title: popory — 영상 품질 개선 (자연 음성·이미지·텍스트)
date: 2026-06-07
status: draft
related:
  - docs/superpowers/specs/2026-06-06-youtube-video-generation-design.md
  - docs/superpowers/specs/2026-06-06-video-ai-scene-images-design.md
---

# 영상 품질 개선 design

## 1. 동기

생성된 YouTube 영상의 완성도가 낮다는 피드백 — ① 내레이션이 로봇 같음(macOS `say`) ② 배경 이미지가 칙칙·단순(전면 어두운 오버레이) ③ 화면 텍스트 과다(헤드라인 + 전체 내레이션 자막). 세 가지를 로컬 워커 파이프라인에서 개선한다.

## 2. 비목표

- API·포털·DB 변경 없음(전부 워커 파이프라인).
- BGM·전환 효과·이미지 스타일 일관성 없음(후속).
- 이미지 모델 교체 없음(flux-1-schnell 유지, 프롬프트·합성만 개선).

## 3. 결정 요약

| 항목 | 결정 |
|------|------|
| TTS | Google Cloud Text-to-Speech, 한국어 Neural2(`ko-KR-Neural2-C`), MP3. 실패/키없음 시 `say` 폴백 |
| TTS 인증 | API 키(`GOOGLE_TTS_API_KEY`, 워커 secrets) |
| 이미지 프롬프트 | cinematic·photorealistic·이미지 내 글자 금지 지시 강화 |
| 이미지 합성 | 전면 45% 오버레이 제거 → 하단 그라데이션 스크림만 |
| 화면 텍스트 | 전체 내레이션 자막 제거. 짧은 캡션(헤드라인)만 하단 로어서드 |

## 4. 아키텍처 (워커 파이프라인 변경)

```
generate_scenes(claude) → 장면[{caption, narration, image_prompt(개선)}]
render_video:
  장면별:
    narration → tts.synthesize(text) → MP3   (실패시 say 폴백)
    image_fetcher(image_prompt) → flux 이미지
    _render_card: 이미지 배경(스크림 하단만) + 짧은 캡션  (자막 없음)
    ffmpeg(이미지+오디오) → 클립
  concat → MP4
```

## 5. 컴포넌트별

### 5.1 TTS (`services/content/popory_content/tts.py` 신규)
- `synthesize(text: str) -> bytes | None`:
  - `GOOGLE_TTS_API_KEY` 환경변수 없으면 None(호출측이 say 폴백).
  - REST `POST https://texttospeech.googleapis.com/v1/text:synthesize?key=...` body `{input:{text}, voice:{languageCode:"ko-KR", name:"ko-KR-Neural2-C"}, audioConfig:{audioEncoding:"MP3"}}`.
  - 응답 `{audioContent: base64}` → 디코드 바이트 반환. 오류/비200 → None(폴백).
- `VOICE_NAME` 상수(구현 중 보이스 청취 후 택 가능).

### 5.2 영상 조립 (`services/content/popory_content/video.py`)
- `render_video` 의 음성 생성 부분 변경:
  - `audio_bytes = synthesize(narration)`; None 이면 기존 `say -o aiff` 로 폴백.
  - Google TTS 는 MP3 → `work/{i}.mp3` 저장; say 는 aiff. 둘 다 ffprobe 로 길이.
- `_render_card(caption, narration, out_png, bg_image_bytes)`:
  - narration 자막 그리기 제거.
  - bg_image_bytes 있으면: 이미지 cover-crop(오버레이 없음) + **하단 그라데이션 스크림**(아래쪽 35% 높이, 검정 0→70% 알파) 합성 → 그 위에 캡션.
  - 캡션: 하단 좌측 로어서드(예: x=80, 하단에서 위로). 폰트 약간 작게. 없으면 단색 배경(스크림 불필요).
- `_run` 헬퍼·concat 동일.

### 5.3 대본 프롬프트 (`services/content/popory_content/video_prompt.py`)
- image_prompt 지시 강화 — "cinematic, photorealistic, high detail, no text/letters in the image". caption 은 짧게(≤16자) 유지 강조.

## 6. 데이터 흐름·계약

- 장면 계약(scenes_json) 불변(caption·narration·image_prompt). 변경은 렌더링·음성·프롬프트 문구뿐.
- 워커 외부 인터페이스(claim/result/PUT video) 불변.

## 7. 에러 처리

- Google TTS 실패(키 없음·비200·네트워크) → `say` 폴백(로그). 영상 완성 보장.
- 이미지 실패 → 기존대로 단색 카드 폴백.
- MP3/aiff 혼용 — ffmpeg 가 둘 다 입력 처리(확장자 기반).

## 8. 테스트

- `tts.py` pytest — `responses` 로 REST 모킹: 200(audioContent) → 바이트 반환; 비200/키없음 → None.
- `video.py` pytest — `_render_card` 가 자막 없이(캡션만) PNG 생성, 스크림 합성(가짜 배경)으로도 생성. render_video 는 synthesize·say 폴백 경로 모두 스모크(synthesize monkeypatch).
- 회귀 — 기존 워커 pytest 통과.

## 9. 외부 설정 (사용자, e2e 전)

- Google Cloud `popory-497615` → **Cloud Text-to-Speech API 사용 설정**.
- API 키 발급(가능하면 TTS API 로 제한) → 워커 `secrets/env.sh` 에 `GOOGLE_TTS_API_KEY` 추가 → 워커 재시작.

## 10. 미해결·후속

- 보이스 선택(Neural2 vs 신형 Chirp3-HD)·속도·피치 튜닝은 구현 중 청취로 결정.
- 이미지 모델 업그레이드·스타일 일관성·BGM 은 후속.
