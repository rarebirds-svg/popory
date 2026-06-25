<!-- 유튜브 동영상·쇼츠 다국어 소프트자막(KO/EN/ZH/JA) 설계 스펙. -->

# 유튜브 다국어 소프트자막 (KO/EN/ZH/JA)

작성일 2026-06-26.

## 목표

유튜브 동영상·쇼츠를 생성할 때, 한국어 음성·한국어 번인 자막은 그대로 두고
**KO/EN/ZH/JA 자막을 `.srt`로 만들어 유튜브 caption 트랙으로 업로드**한다.
시청자가 CC 버튼에서 언어를 골라 끄고 켤 수 있다.

## 핵심 결정 (확정)

- **음성·내레이션 언어**: 한국어 유지. 이미 `tts.py` `ko-KR` + 프롬프트 한국어 강제라 **변경 없음**.
- **화면 번인 자막**: 한국어 그대로 유지(`video.py` PNG overlay).
- **소프트자막 트랙**: KO·EN·ZH·JA **4개 전부** 업로드. (KO는 번인과 중복되지만 SEO·자동번역 소스로 유용.)
- **적용**: 유튜브 동영상 + 쇼츠의 유튜브 업로드 경로. **항상 ON**(폼 옵션 추가 없음). IG/FB 릴스는 `.srt` 미지원이라 해외 자막 미표시.
- **OAuth 스코프**: `youtube.force-ssl` 추가(`captions.insert` 필수). 기존 연결 계정은 `/content/youtube`에서 한 번 재연결해야 자막 권한 부여. 재연결 안내 배너는 만들지 않는다.
- **내성**: 번역 실패·자막 업로드 실패는 **영상 생성/업로드를 실패시키지 않는다**. 경고 로그 후 진행.

## 데이터 흐름

```
make_video (생성)
  └ 장면별 narration → 문장 분할 → TTS 실측 길이 → 장면-로컬 span (기존)
  └ 장면 오프셋(크로스페이드 반영)으로 전역 KO cue 목록 누적   ← 신규 훅
worker.run_once
  └ ko_lines = [cue.text]
  └ translate_lines(ko_lines) → {en,zh,ja}  (claude CLI, 1:1 정렬 검증, 실패 시 None)
  └ subtitles.to_srt(cues, 언어별 텍스트) → ko/en/zh/ja .srt
  └ R2 저장: content/subs/{job_id}/{lang}.srt
worker.run_upload_once (유튜브 업로드, 별도 패스)
  └ videos.insert (기존) → video_id
  └ 각 lang .srt를 R2에서 받아 captions.insert(video_id, lang)   ← 신규
       실패는 lang별 try/except + 경고. 영상은 정상.
```

## 전역 타임라인 산출 (정확도 핵심)

장면은 `_xfade_graph`로 전이 `td=0.4s`만큼 겹쳐 이어붙인다. 따라서 최종 영상 시간축은
장면 길이 합보다 짧다. 장면 i의 절대 시작:

```
scene_start[0] = 0
scene_start[i] = scene_start[i-1] + scene_duration[i-1] - td   (i ≥ 1)
```

전역 cue = (scene_start[i] + local_st, scene_start[i] + local_en, sentence).
`scene_duration`은 `render_video`가 `_xfade_graph`에 넘기는 `durations` 배열,
`local_st/en`은 기존 `_spans_from_durations` 결과다. 번인 자막이 장면-로컬 시간으로
이미 그렇게 표시되므로 `.srt`도 동일 기준이라 화면과 일치한다.

## 컴포넌트 (단위 분리)

### 1. `services/content/popory_content/subtitles.py` (신규)
순수 함수 모듈. 외부 의존 없음 → 단위 테스트 용이.
- `scene_offsets(scene_durations: list[float], td: float) -> list[float]` — 위 공식.
- `Cue = tuple[float, float, str]` (start, end, text).
- `to_srt(cues: list[Cue]) -> str` — `HH:MM:SS,mmm` 타임코드로 SRT 직렬화. 빈 텍스트 cue는 건너뜀.

### 2. `services/content/popory_content/translate.py` (신규)
- `translate_lines(ko_lines: list[str], langs=("en","zh","ja")) -> dict[str, list[str]] | None`
- claude CLI 1회 호출. 입력은 번호 매긴 한국어 문장, 출력은 각 언어 배열(동일 길이).
- **1:1 정렬 강제**: 문장 병합·분할·증감 금지. 반환 배열 길이가 입력과 다르면 1회 재시도, 그래도 불일치면 `None`(해외 자막 생략).
- 번역 톤: 자연스러운 구어체, 고유명사·인용 보존. 광고/CTA 추가 금지(브랜딩 규칙).

### 3. `video.py` (기존 — 최소 훅)
- `render_video`가 전역 KO cue 목록을 함께 반환(또는 out-param). 기존 번인 로직·반환 구조는 유지하고 누적만 추가.
- `make_video`(worker가 부르는 진입점)가 cue 목록을 worker로 전달.

### 4. `services/content/popory_content/worker.py` (기존)
- `make_video` 반환에 cue 추가 수용.
- `translate_lines` 호출 → 언어별 `.srt` 생성 → R2 `content/subs/{job_id}/{lang}.srt` 저장(`put_binary` 유사 경로).
- 유튜브 업로드 패스(`run_upload_once`)에서 video_id 확보 후, 존재하는 lang `.srt`를 R2에서 받아 `upload_caption` 호출. lang별 try/except, 실패는 `append_log` 경고.

### 5. `services/content/popory_content/youtube_upload.py` (기존)
- `upload_caption(access_token, video_id, language, name, srt_bytes) -> None`
- `POST https://www.googleapis.com/upload/youtube/v3/captions?part=snippet&uploadType=multipart`
- multipart: `snippet={videoId, language, name, isDraft:false}` + 자막 본문(SRT). 403/기타 오류는 호출측에서 처리.

### 6. `workers/api/src/routes/content_youtube.ts` (기존)
- `SCOPE`에 `https://www.googleapis.com/auth/youtube.force-ssl` 추가. 기존 `youtube.upload`(업로드 필수)는 유지.

## R2 키 규약

- 영상: `content/video/{job_id}.mp4` (기존)
- 자막: `content/subs/{job_id}/{lang}.srt` (신규, lang ∈ ko|en|zh|ja)

## 에러 처리

- 번역 실패(`translate_lines` None 또는 예외): EN/ZH/JA 자막 생략, KO `.srt`만 저장, 영상 정상. 경고 로그.
- 자막 업로드 403(스코프 미보유): 해당 lang 건너뜀, 경고. 영상 업로드는 성공 그대로.
- `.srt` 누락(생성 실패): 해당 lang 업로드만 건너뜀.

## 테스트

- `subtitles.py`: `scene_offsets`(전이 오프셋 누적), `to_srt`(타임코드 포맷·정렬·빈 텍스트 스킵) 단위 테스트.
- `translate.py`: claude CLI 러너를 스텁으로 주입해 **길이 불일치 시 재시도→None** 경로 검증.
- 유튜브 caption 업로드: 모킹 스모크(요청 형태 확인).

## YAGNI / 비범위

- 음성 다국어(더빙) 없음 — 음성은 한국어 고정.
- 자막 언어 선택 UI 없음 — 항상 4개.
- IG/FB 해외 자막 없음(.srt 미지원).
- 번인 자막 다국어화 없음 — 한국어 번인 유지.

## 마이그레이션

- 스코프 변경 후 기존 유튜브 연결 계정은 재연결 필요. 재연결 전엔 자막만 403→경고, 영상은 정상.
- DB 스키마 변경 없음(자막은 R2 + 유튜브에만 존재).

## 신규 파일 헤더 (CLAUDE.md 규칙 6)

`subtitles.py`·`translate.py`는 첫 줄에 한국어 한 줄 역할 주석을 넣는다.
