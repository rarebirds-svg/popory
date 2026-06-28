<!-- Qwen3-TTS 맥미니 M4 로컬 실행 PoC(설치·샘플·실측) 설계 문서. -->

# Qwen3-TTS 로컬 PoC (맥미니 M4)

작성일 2026-06-28.

## 목표

맥미니 M4에서 Qwen3-TTS가 실제로 돌아가는지, 한국어 음성 품질·생성 속도·메모리를 확인해 **로컬 통합(서비스화) 진행 여부를 결정**한다. 탐색적 spike이며 서비스·워커 통합은 범위 밖(다음 슬라이스).

## 배경 / 제약

- Qwen3-TTS 공식 추론은 **CUDA 전용**(`device_map="cuda:0"`, `flash_attention_2`). Apple Silicon(MPS)·CPU는 미문서화 → 맥 실행은 비공식·미검증. 라이선스 Apache 2.0(self-host 가능).
- 설치: `pip install -U qwen-tts` + `soundfile`. **flash-attn은 맥(CUDA 없음)에서 제외**, `attn_implementation="eager"` 사용.
- 모델: `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`(경량 우선), `…-1.7B-CustomVoice`(품질). 1.7B ≈ 2GB.
- 한국어 화자: `Sohee`. API: `Qwen3TTSModel.from_pretrained(...)` → `generate_custom_voice(text, language="Korean", speaker="Sohee")` → `(wavs, sr)`.

## 방법

1. 격리 venv(`/tmp .../scratchpad/.qwenvenv` 또는 `services/` 밖 임시)에서 `qwen-tts`·`soundfile` 설치(flash-attn 제외).
2. 모델 로드 시도 순서: **MPS**(`device_map="mps"`, `torch_dtype=bfloat16`, `attn_implementation="eager"`) → 실패/오류면 **CPU** 폴백. 0.6B 먼저, 되면 1.7B.
3. 한국어 샘플 생성(포포리 책 리뷰 톤 문장, Sohee + 가능하면 음성 디자인) → `~/Downloads/qwen3tts_local_{model}_{speaker}.wav` 저장.
4. **실측**: 모델 로드 시간, 문장당 생성 시간, 피크 메모리(이미지gen과 공존 가능성). 콘솔/로그로 보고.

## 성공 기준 / 판단

- MPS에서 합리적 속도(짧은 문장 수 초 수준)·정상 한국어 → **로컬 통합 진행 가치 있음**.
- MPS 연산 깨짐 + CPU만 가능(문장당 수십 초~분) → **비실용적, 현행 Google Chirp3-HD 유지 권고**.
- 설치/실행 자체 불가 → 원인 기록 + "맥 비실용" 결론.

## 비목표

- `services/ttsgen/` 서비스화·HTTP 엔드포인트·plist·워커 tts.py 통합(품질·속도 OK일 때 다음 슬라이스).
- 다중 화자 전수 생성(판단엔 Sohee + 음성 디자인이면 충분; 되면 추가).

## 산출물

- 로컬 생성 한국어 WAV 샘플(`~/Downloads/`).
- 실측 결과(로드/생성 시간·메모리·MPS 가용 여부)와 통합 권고(진행/보류).
- 코드는 임시 spike 스크립트(scratchpad). 통합 결정 시 정식 `services/ttsgen/`로 재작성.

## 롤백

PoC는 임시 venv·스크립트뿐 — 저장소·prod 무영향. venv 삭제로 정리.
