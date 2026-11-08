# Gemini 설계 음성(Voice design) 도입 — 설계

## 배경

- 롱폼(2026-11-02 사용자 판정)과 쇼츠(2026-11-08 보고) 모두 챕터마다 목소리가 바뀐다. 기본 남성 음성인 Gemini 3.8 Flash TTS 프리셋 화자 Iapetus 는 화자 이름만 고정하고, 합성할 때마다(테이크마다·문단마다) 목소리를 새로 만든다. 장면 보정(`video._match_scenes`, rubberband)이 흔들림을 메우지만 갈라지는 소리를 남긴다.
- 2026-11-08 실험(같은 쇼츠 원고 『모리와 함께한 화요일』 8장면, `tools/voice_ab.py`).
  - 문단 나눔 제거·짧은 연출 지시는 효과가 없었다(2×2, 16테이크). 테이크 사이 차이가 변형 사이 차이보다 컸다.
  - Voice design 으로 만든 고정 음성 `voice_s8vzho2m0lq6` 은 장면 사이 음높이 폭 2.66 → 1.36반음(짧은 지시), 테이크 사이 기본 음높이 차 2.1 → 1.1반음, 필요 보정량 0.58 → 0.38반음이었다. 테이크 8:8 짝 비교 64쌍 중 60쌍에서 설계 음성이 더 고르다. 밝기 폭(약 5dB)은 줄지 않았다. 문장 정렬 거부 0건.
  - 사용자는 귀로 구분하지 못해 판단을 맡겼고, 수치 개선·보정량 감소·되돌리기 쉬움을 근거로 채택했다.
- 설계 음성 `voice_s8vzho2m0lq6` — display `popory-narrator-v1`, ko-KR, male, 페르소나 "A calm, warm Korean man in his forties who narrates book reviews to a single listener. Natural conversational pace, gentle and trustworthy, never like a news announcer.", **만료 2027-11-08**(저장 음성 TTL 1년, 프로젝트당 200개). API 키의 Google 프로젝트에 묶여 있다.

## 목표

1. 롱폼·쇼츠 남성 기본 음성(`options.VOICE["male"]`)을 `gemini-3.8-flash-tts/voice_s8vzho2m0lq6` 으로 바꾼다.
2. Gemini 요청 본문이 설계 음성 ID(`voice_…`)를 `speechConfig.voiceConfig.voice` 로 보낸다. 프리셋 화자는 지금처럼 `prebuiltVoiceConfig.voiceName`.
3. 연출 지시(`gemini_tts.STYLE` 기본값)를 짧은 고정 문구 `Calm, warm and conversational.` 로 바꾼다. 공식 문서 권고 — 긴 Director's Notes·"같은 목소리를 유지하라" 같은 메타 지시·나이·성별은 오히려 흔들림을 늘린다. env `POPORY_GEMINI_TTS_STYLE` 덮어쓰기는 유지한다.
4. 만료 30일 전부터 영상 작업마다 `gemini_voice_expiry_failed` 로그를 남긴다(→ `/admin/errors`, 헬스체크 '자원한도' 경고 → 텔레그램).
5. 같은 페르소나로 음성을 다시 만드는 도구 `tools/design_voice.py` 를 남긴다.

## 비목표

- 장면 보정 제거·변경 — 밝기 차이가 그대로라 유지한다.
- 여성 음성(Chirp3-HD Aoede·Leda) 변경.
- 폴백 정책 변경 — 설계 음성 요청이 실패하면 지금처럼 영상 전체가 `FALLBACK_VOICE`(Neural2-C)로 가고 `gemini_tts_failed` 가 남는다.
- Chirp3-HD 전환(PR #103) — 보류하고 대안으로 남긴다.
- 만료일을 API 로 조회하는 장치 — 만료일은 생성 응답의 `expire_time` 을 상수로 둔다.

## 실패로 보는 것

- 한 영상 안에서 음성이 섞이는 것.
- 설계 음성이 사라져 무료 음성 폴백이 조용히 계속되는 것.
- 테스트가 실제 Gemini·텔레그램에 닿는 것.

## 결정

- 404 응답 안내 문구가 "모델 이름을 찾을 수 없음" 만 말하면 설계 음성 만료를 놓친다 — 모델 또는 설계 음성을 함께 안내한다.
- 만료 경고는 워커의 영상 작업(롱폼·쇼츠) 직후 기록 지점(`_log_scene_match` 옆)에서 남긴다(Claude 결정).
- 만료일 표는 `options.py` 에 둔다(`DESIGNED_VOICE_EXPIRES`). 음성 ID 와 함께 바뀌기 때문이다.
- 재생성 도구는 기본이 드라이런(요청 없음)이고 `--yes` 일 때만 만든다. 다시 만든 음성은 같은 프롬프트라도 목소리가 다를 수 있으므로, 교체 전 `voice_ab.py` 로 다시 비교한다.

## 검증

- 단위 테스트 — 요청 본문 분기, 404 안내, 기본 음성이 설계 음성인지, 짧은 지시, 만료 경고 경계(31일 전 무음·30일 전 기록·만료 후 기록·프리셋은 무시), 헬스체크 마커, 재생성 도구의 요청 본문.
- content·healthcheck 전체 pytest.
- 실제 경로(맥미니, 3요청 약 $0.08) — 롱폼 샘플 원고(16장면, 2묶음)와 쇼츠 원고(1묶음)를 `video._gemini_scene_audio` 로 합성해 요청 수·문장 정렬·장면 사이 폭·발화 길이를 잰다. 기준은 요청 수 롱폼 2·쇼츠 1, 정렬로 통째 폴백한 장면 0, 쇼츠 장면 사이 폭이 현행 평균(2.66반음)보다 작을 것이다. 롱폼 발화 길이는 기록만 한다(말이 약 10% 빠르다).
- 반영 후 다음 18시 롱폼·쇼츠 작업 폴더로 같은 측정을 한다.

## 되돌리기

`options.VOICE["male"]` 를 `gemini-3.8-flash-tts/Iapetus` 로 되돌리고 워커를 재시작한다. 연출 지시는 env `POPORY_GEMINI_TTS_STYLE` 로 즉시 바꿀 수 있다.
