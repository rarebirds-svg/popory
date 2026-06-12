# YouTube 영상 품질 개선 — 자연 음성 중심 (설계)

날짜: 2026-06-13
대상: `services/content`(로컬 워커) 전반. Worker API·포털·D1 **무변경**.
선행: [[2026-06-07-video-quality-design]], [[2026-06-07-video-options-layout-design]], [[2026-06-06-video-ai-scene-images-design]]

## 목표

생성되는 YouTube 영상의 체감 품질을 무료 수단만으로 끌어올린다. 우선순위는 **음성 자연도**이며, 함께 모션·전환·BGM·음량정규화·이미지 톤 일관성을 얹는다. 모든 변경은 로컬 워커에 집중되고, 추가 비용은 0원이다.

## 비목표 (이번 범위 제외)

- 구운 자막(burned-in subtitle)·카라오케 자막. 현 ffmpeg가 `libass/freetype` 없이 빌드돼 불가. ffmpeg 재설치를 동반하는 별도 작업(Tier 3)으로 분리.
- 이미지 고정 시드. Worker API(`/api/content/ai-image`) 변경이 필요하므로 이번엔 제외. 톤 일관성은 **스타일 접미사**로만 확보.
- BGM 음원 자체의 배포. 라이선스 안전을 위해 음원 파일은 사용자가 직접 배치한다(아래 참조).
- 쇼츠(세로형) 파이프라인의 동등 적용은 본문 가로형 적용 후 동일 패턴으로 확장(이번 스펙은 가로형 기준, 쇼츠는 회귀만 보장).

## 현재 구조 (변경 전)

`video.py`의 `render_video`는 장면마다 내레이션을 `_split_sentences`로 **문장 단위로 쪼개**, 문장별로 ① TTS 합성 ② 텍스트카드 PNG ③ 정지 이미지(`-loop 1`)+오디오 클립을 만들고, 마지막에 `concat -c copy`로 이어붙인다. 결과적으로 (a) 문장마다 억양이 리셋돼 "읽는" 느낌, (b) 완전 정지 화면, (c) 하드컷, (d) 무음(내레이션 외), (e) 음량 비정규화.

## 설계

### 1. 음성 — `tts.py`

검증 완료(2026-06-13, ko-KR voices API + synthesize 호출):
- ko-KR Chirp3-HD 보이스 30종 제공.
- `audioConfig.speakingRate` 동작(200).
- 네이티브 `[pause short]` 마크업을 `input.markup`으로 전달 시 동작(audioContent 반환).

변경:
- 보이스 매핑(`options.py`의 `VOICE`)을 Chirp3-HD로 교체.
  - `female-calm → ko-KR-Chirp3-HD-Aoede`
  - `female-bright → ko-KR-Chirp3-HD-Leda`
  - `male → ko-KR-Chirp3-HD-Charon`
- `synthesize(text, voice)`가 `input.markup`(문장 사이 `[pause short]` 주입) + `audioConfig.speakingRate=0.96`로 호출.
- 키 없음/실패 시 기존 `say` 폴백 유지(시그니처·폴백 흐름 불변).

### 2. 렌더 단위 — `video.py`

- 합성·렌더 단위를 **문장 → 장면**으로 변경. `_split_sentences` 루프 제거.
- 장면당 클립 1개 = (배경이미지 1장 + 헤드라인 캡션 `caption` + 장면 내레이션 **통째 1회 TTS**).
- 자막: 장면당 헤드라인 1장(`caption`). 문장별 자막 교체 폐기.

### 3. 모션 + 전환 — `video.py`

검증 완료: 현 ffmpeg가 `zoompan`·`xfade`·`loudnorm`·`amix`·`afade`·`acrossfade`·`dynaudnorm` 지원.

- 켄번스: 장면 클립을 `-loop 1` 정지 → `zoompan`(느린 줌인/팬). 1080p·30fps 유지.
- 크로스페이드: `concat -c copy` → `xfade`(0.4s) + `acrossfade`(0.4s) 체인으로 장면 연결. 재인코딩 비용(생성 지연) 수용.
- 클립 수가 1개면 xfade 체인 생략(단일 장면 graceful).

### 4. 오디오 마스터링 — `video.py`

- BGM: `services/content/assets/bgm/` 디렉토리에서 음원 1개를 고름(여러 개면 job_id 기반 결정적 선택). 파일 없으면 BGM 생략(graceful, say-폴백과 동일 철학). `amix`로 내레이션과 합성, BGM 볼륨 ≈ 0.15, BGM이 내레이션보다 짧으면 루프.
  - 음원은 **사용자가 무료 CC0 음원**(YouTube 오디오 보관함·Pixabay Music)을 직접 배치. 저장소엔 `assets/bgm/.gitkeep` + `README.md`(출처·라이선스 안내)만 커밋. 에이전트는 음원을 받거나 커밋하지 않는다.
- 음량 정규화: 최종 믹스에 `loudnorm`(I=-14 LUFS, YouTube 기준). 내레이션 앞뒤 짧은 무음 패딩으로 호흡 여유.

### 5. 이미지 톤 일관성 — `video_prompt.py`

- 영상 단위 공통 **스타일 접미사**(예: 색감·조명·필름룩 키워드)를 모든 장면 `image_prompt` 끝에 부착해 톤 통일. `image_style_kw`와 결합.
- 고정 시드는 비목표(위).

## 데이터 흐름 (변경 후)

```
generate_scenes (claude CLI) → scenes[{caption, narration, image_prompt}]
  └ 각 장면:
       image_fetcher(image_prompt + 스타일 접미사) → 배경 bytes (실패 시 단색)
       synthesize(narration 통째, voice, markup, rate) → mp3 (실패 시 say)
       _render_card(caption, 배경) → PNG
       ffmpeg zoompan(PNG)+audio → 장면 클립
  → xfade/acrossfade 체인 → 믹스(amix BGM)+loudnorm → out.mp4
```

## 인터페이스 영향

- `tts.synthesize(text, voice)` — 시그니처 유지, 내부만 변경.
- `video.render_video(scenes, ...)` — 시그니처 유지(장면 배열 입력 동일), 내부 루프 구조 변경.
- `options.VOICE` 매핑 값만 교체(키 `female-calm/female-bright/male` 유지 → 포털 UI 무변경).
- Worker API·포털·D1·params_json 스키마 무변경.

## 테스트 (TDD)

- `test_tts.py`: HTTP mock으로 (a) 페이로드가 `input.markup`·Chirp3-HD 보이스명·`speakingRate` 포함, (b) 키 없으면 None 반환(폴백 신호).
- `test_options.py`: `VOICE` 3키가 Chirp3-HD 보이스명으로 매핑.
- `test_video.py`: (a) 장면당 클립 1개(문장 분할 안 함), (b) ffmpeg 호출에 zoompan 포함, (c) 2장면 이상 시 xfade 체인, (d) BGM 디렉토리 비면 amix 생략·정상 산출, (e) loudnorm 적용.
- `test_video_prompt.py`: 스타일 접미사가 시스템 프롬프트에 반영.
- 기존 회귀 전부 통과(10/10 → 신규 포함 증가).

## 리스크 / 트레이드오프

- 재인코딩(xfade) + 장면 통째 합성으로 생성 시간 변동. 단일 스레드 워커 20분 타임아웃 내 유지 확인 필요(장면 16개 상한 기준).
- 무음 시청 시 본문 자막 부재(헤드라인만). 사용자 합의된 선택. 추후 libass 재설치로 보강 가능.
- Chirp3-HD가 SSML 풀 셋은 미보장 → `markup`(`[pause]`)·`speakingRate`만 사용해 안전 확보.
