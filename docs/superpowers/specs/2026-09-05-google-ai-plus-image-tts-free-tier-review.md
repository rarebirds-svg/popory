<!-- 구글 AI Plus 멤버십 기준으로 이미지 생성·TTS 무료 범위를 재검토한 기록. 결론: 현행(Cloudflare flux + Cloud TTS 무료 버킷) 유지. -->

# Google AI Plus vs. 현 파이프라인(Cloudflare 이미지 + Cloud TTS) 검토 — 2026-09-05

> 검증 방법 주의: 이 환경의 egress 프록시가 `ai.google.dev`, `one.google.com`, `gemini.google`, `support.google.com`, `blog.google`, `docs.cloud.google.com`을 차단했다.
> **직접 열람·인용한 1차 소스는 `cloud.google.com/text-to-speech/pricing`, `cloud.google.com/vertex-ai/generative-ai/pricing`, `google-gemini/cookbook`(GitHub) 뿐**이다.
> 나머지 Google 페이지는 검색 결과 스니펫(페이지 URL은 Google 공식)으로만 확인했으며, 아래에 `[스니펫]`으로 표시한다. 3rd-party 블로그 수치는 `[비공식]`.

## 1. Google AI Plus 구성 · 한국 가격 · API 크레딧 여부

| 항목 | 내용 | 근거 |
|---|---|---|
| 가격(한국) | **월 11,000원** (신규 첫 2개월 5,500원 프로모) | [스니펫] https://blog.google/intl/ko-kr/products/google-ai-plus-plans-kr/ , https://support.google.com/googleone/answer/16548195?hl=ko |
| 가격(미국) | $7.99/월, 160+개국 제공(한국 포함) | [스니펫] https://blog.google/products-and-platforms/products/google-one/google-ai-plus-availability/ |
| Gemini 앱 | Gemini 3 Pro(현재 3.1 Pro) "more access", Free 대비 **2x 사용량**, 사용량은 5시간/주간 단위 컴퓨트 기반 | [스니펫] https://support.google.com/googleone/answer/16882689 , https://support.google.com/gemini/answer/16275805 |
| 이미지(Nano Banana Pro) | 앱 내 "more access" — **일일 장수 등 구체 한도는 공개 문서에 없음(확인 못 함)** | [스니펫] 위 support 페이지, https://one.google.com/about/google-ai-plans/ |
| Veo / Flow / Whisk | Veo 3.1 "more access"(월 단위 갱신), **월 200 AI 크레딧**(Flow·Whisk 영상), Whisk는 일부 국가만 | [스니펫] support 16882689, one.google.com |
| NotebookLM | Free 대비 상향 한도 | [스니펫] support 16882689 |
| 저장공간 | 200GB, 가족 5명 공유 | [스니펫] 동상 |
| **Gemini API / AI Studio / Cloud 크레딧** | **없음(확인됨 범위 내)**. `ai.google.dev/gemini-api/docs/google-ai-plans`는 **AI Pro·Ultra만** AI Studio Playground/Build 한도 상향 대상으로 기술하고, "혜택은 AI Studio 웹 UI 안에서만 적용, API 키 직접 사용은 별도 과금"이라고 명시. $10/월 Cloud 크레딧도 **AI Pro/Ultra(GDP Premium 통합, 2026-01-27)** 혜택이며 Plus 언급 없음 | [스니펫] https://ai.google.dev/gemini-api/docs/google-ai-plans , https://blog.google/innovation-and-ai/technology/developers-tools/gdp-premium-ai-pro-ultra/ , https://support.google.com/googleone/answer/14534406 |

결론: **AI Plus는 앱(소비자) 혜택 묶음이며 파이프라인이 쓰는 API 비용에는 영향이 없다.**

## 2. Gemini API(ai.google.dev) 이미지 생성 — 무료 티어·가격·해상도

| 모델(ID) | 무료 티어 | 유료 단가(이미지당) | 비고 |
|---|---|---|---|
| Nano Banana = `gemini-2.5-flash-image` | 포럼상 "rate-limits 페이지에 free tier 없음" [스니펫, 2025] | 이미지 출력 $30/1M tok ≈ **$0.039/장** | **2026-10-02 종료(shutdown)**, 대체 `gemini-3.1-flash-image` [비공식 요약 + Vertex 가격표] |
| Nano Banana 2 = `gemini-3.1-flash-image(-preview)` | **Free Tier "not available"** [비공식 요약, 공식 표 직접 확인 못 함] | $60/1M tok: **512px $0.045 / 1K $0.067 / 2K $0.101 / 4K $0.15** | 직접 확인: https://cloud.google.com/vertex-ai/generative-ai/pricing 각주 ***; ai.google.dev pricing 스니펫 동일 |
| Nano Banana 2 Lite = `gemini-3.1-flash-lite-image` | 확인 못 함 | $30/1M tok: **1K $0.034** (2K/4K 미지원) | Vertex 가격표 각주 ****, https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite-image [스니펫] |
| Nano Banana Pro = `gemini-3-pro-image` | 확인 못 함(3.x Pro 계열은 free tier 없음이 통례) | $120/1M tok: **1K·2K $0.134 / 4K $0.24** | Vertex 가격표 각주 ** |
| Imagen 4 (`imagen-4.0-generate-001` 등) | 원래 free tier 없음 | Vertex: Fast $0.02 / 표준 $0.04 / Ultra $0.06 | **Gemini API 쪽 Imagen 4 엔드포인트는 2026-08-17 종료**, 대체 `gemini-3.1-flash-image` [스니펫] https://ai.google.dev/gemini-api/docs/deprecations.md.txt |

- 종횡비: Gemini 3.1 Flash Image **1:1, 3:2, 2:3, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9, 4:1, 8:1**; `image_size` 512/1K/2K/4K. Flash-Lite는 1K만. → 16:9, 9:16, **3:2 모두 지원** [스니펫] https://ai.google.dev/gemini-api/docs/image-generation , https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite-image
- SynthID 워터마크 항상 삽입(+C2PA) [스니펫].
- RPM/RPD: 공식 rate-limits 페이지는 이미지·TTS 모델의 티어별 수치를 더 이상 표로 공개하지 않고 "AI Studio 콘솔에서 확인"으로 안내 [스니펫] https://ai.google.dev/gemini-api/docs/rate-limits → **수치 확인 못 함**.
- 한국어 프롬프트/텍스트 없는 장면 이미지: 정책상 금지 조항 없음(일반 사용 정책만 적용). 프롬프트 언어별 성능 표는 확인 못 함. Nano Banana 2는 "reliable text rendering" 명시라 텍스트 없는 배경 생성엔 무관.
- 파이프라인 월 비용(24장/일≈720장/월, 무료 없음 가정): Flash-Lite 1K ≈ **$24**, Flash Image 512px ≈ $32 / 1K ≈ **$48**, Pro 1K ≈ $96.

## 3. Gemini API TTS

| 항목 | 내용 | 근거 |
|---|---|---|
| 모델 | `gemini-3.1-flash-tts-preview`(현행 권장), `gemini-2.5-flash-preview-tts`, `gemini-2.5-pro-preview-tts` | 직접 확인: cookbook `quickstarts/Get_started_TTS.ipynb`; [스니펫] https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-tts-preview |
| 무료 티어 | pricing 페이지에 2.5 Flash TTS·3.1 Flash TTS 모두 Free Tier "Free of charge"(데이터는 제품 개선에 사용) [스니펫/비공식]. **RPM/RPD/TPM 공식 수치는 미공개** — 3rd-party가 말하는 "2.5 Flash TTS 3 RPM / 10k TPM / 15 RPD"는 [비공식], 포럼 제목에도 "free-tier quota (limit 3)" 언급. **확인 못 함** | https://ai.google.dev/gemini-api/docs/pricing , https://ai.google.dev/gemini-api/docs/rate-limits |
| 유료 단가 | 2.5 Flash TTS **입력 $0.50 / 출력(오디오) $10.00 per 1M tok**; 3.1 Flash TTS·2.5 Pro TTS **$1.00 / $20.00**; 배치 50% 할인. **오디오 25 tok/초** | 직접 확인: https://cloud.google.com/text-to-speech/pricing (Gemini-TTS 표, Cloud TTS API 경유 시 무료 한도 "Not available"); ai.google.dev pricing 스니펫 동일 |
| 한국어 | 지원 언어표에 **Korean (ko)** 포함 | [스니펫] https://ai.google.dev/gemini-api/docs/speech-generation |
| 보이스 | 30개 프리빌트(언어 독립): Kore(Firm), Leda(Youthful), Aoede(Breezy), Charon, Puck, Zephyr 등 — Cloud Chirp3-HD의 Aoede/Leda와 이름 동일 계열 | [스니펫] 동상 |
| 제어 | 자연어 "연출 지시"(스타일·억양·속도·톤) + **audio tags** `[short pause]`, `[whisper]`, `[sighs]` 등. 한국어 대본이라도 태그는 영어 권장. SSML 아님 | 직접 확인: cookbook 노트북; [스니펫] speech-generation |
| 출력 | **raw PCM 16-bit mono 24kHz** (WAV 컨테이너는 클라이언트가 씌움), MP3 직접 출력 없음 | 직접 확인: cookbook; [스니펫] |
| 비용 추정 | 170k자/월 ≈ 한국어 낭독 ~330자/분 → ~515분 ≈ 31k초 → **~770k 오디오 tok** → 2.5 Flash TTS ≈ **$8/월**, 3.1 Flash TTS ≈ **$15/월**(무료 티어 미적용 시). 무료 티어 RPD가 15 수준이면 일일 에피소드 분할 청크 수에 따라 초과 가능 | 추정 |

## 4. Google Cloud Text-to-Speech 무료 한도·단가 (직접 확인: https://cloud.google.com/text-to-speech/pricing)

| 음성군 | 월 무료 한도 | 초과 단가 | SKU |
|---|---|---|---|
| Standard | 0–4M자 | $4/1M자 | 9D01-5995-B545 |
| WaveNet | 0–4M자 | $4/1M자 | **9D01-5995-B545 (Standard와 동일 SKU → 한 버킷 공유로 해석)** |
| Neural2 | 0–1M자 | $16/1M자 | FEBD-04B6-769B |
| Polyglot(Preview) | 0–1M자 | $16/1M자 | FEBD-04B6-769B (Neural2와 동일 SKU) |
| Studio | 0–1M자 | $160/1M자 | 84AB-48C0-F9C3 |
| Chirp 3: HD | 0–1M자 | $30/1M자 | F977-2280-6F1B |
| Instant custom voice | 없음 | $60/1M자 | A247-37D7-C094 |
| Gemini-TTS(2.5 Flash / 3.1 Flash / 2.5 Pro) | 없음 | 위 3절 단가 | — |

- **Neural2(FEBD…)와 Chirp 3 HD(F977…)는 SKU가 다르므로 각각 1M자 무료 버킷을 별도로 가진다** — 페이지는 "per voice family" 문구 대신 SKU별 행으로 표시(해석). 현재 사용량 170k자/월은 어느 한쪽만 써도 무료 범위 안(둘 합쳐 2M자).
- 과금은 공백·개행 포함 문자 수, SSML 태그(`<mark>` 제외) 포함 — 현 코드의 `<break>` 삽입도 문자 수에 산입됨.

## 5. 구독이 API 비용을 줄이는 경로가 있는가

- **AI Plus: 없음.** 개발자 혜택(AI Studio 한도, $10/월 Cloud 크레딧, Antigravity/Jules 한도)은 문서상 **AI Pro·Ultra** 전용 [스니펫: ai.google.dev google-ai-plans, blog gdp-premium-ai-pro-ultra, support 14534406]. 2026-06-18부로 Gemini CLI/Code Assist 소비자 티어는 Antigravity로 통합 [스니펫].
- **AI Pro라면** $10/월 Google Cloud 크레딧(Gemini API·Vertex 사용 가능)이 있음 → Flash-Lite Image 기준 ~290장/월, Nano Banana 2 1K 기준 ~150장/월분. 파이프라인 720장/월을 다 덮진 못함. AI Pro 한국 가격은 **확인 못 함**.
- AI Studio 웹 UI 무료 사용은 API 키 호출과 별개이며 자동화 대상이 아님(구독 혜택도 UI 안에서만) [스니펫].

## 권고 (24장/일, 170k자/월 기준)

1. **현행 유지(Cloudflare flux + Cloud TTS 무료 버킷) — 1순위.** 검증된 비용 $0. Neural2 1M자 + Chirp3-HD 1M자 별도 버킷이라 여유 5배 이상. 리스크는 Cloudflare 일일 뉴런 소진(이미 로컬 RealVisXL 폴백 있음)뿐. 변경 불필요.
2. **이미지를 Gemini API로 전환 — 비권장(비용 발생).** 무료 티어가 없거나(3.1 Flash Image) 미확인이고, 2.5 Flash Image는 10/2 종료. 품질(한국적 장면·일관성·4K)은 flux보다 우위일 가능성이 크나 월 $24~48. 도입한다면 `worker.py`의 `_try_cloudflare` 앞/뒤에 `gemini-3.1-flash-lite-image`(1K, `aspect_ratio` 16:9/9:16) 호출 단계를 추가하고 SynthID 워터마크·과금 상한(예산 알림)을 두는 형태. AI Pro $10 크레딧으로 일부 상쇄 가능하나 Plus로는 불가.
3. **TTS를 Gemini TTS로 전환 — 보류.** 한국어·감정/쉼 제어(audio tags)는 매력적이지만 (a) 무료 RPD가 공식 미공개·매우 낮다는 보고(3 RPM/15 RPD [비공식])라 일일 자동 생성이 한도에 걸릴 위험, (b) 초과 시 $8~15/월로 현재 $0보다 비쌈, (c) 출력이 24kHz PCM이라 `tts.py`의 MP3/`<break>` SSML 로직 전면 교체 필요, (d) preview 모델이라 음질 편차·무음 버그 포럼 보고 다수. 여성 보이스 실험 정도만 권장.
4. **AI Plus로 Gemini 앱/Nano Banana Pro 수동 생성 — 자동화 불가.** 앱 전용(API 아님), 한도는 컴퓨트 기반 5시간/주간 단위로 장수 미공개. 썸네일·특수 컷 몇 장을 손으로 뽑는 보조 용도에만 유효. 구독 유지 여부는 파이프라인과 무관하게 앱·저장공간 가치로 판단.

**미확인 항목 요약**: Gemini API 이미지/TTS 모델의 무료 RPM·RPD 정확 수치, AI Plus 앱 내 이미지 일일 장수, AI Pro 한국 가격, Gemini 이미지 모델의 프롬프트 언어(한국어) 공식 지원표.
