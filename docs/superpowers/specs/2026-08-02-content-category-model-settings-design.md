# 카테고리별 TTS·이미지 모델 설정 설계

작성일 2026-08-02.

## 목적

콘텐츠 스튜디오에서 **카테고리마다 다른 목소리와 이미지 모델**을 쓸 수 있게 한다. 첫 적용 대상은 신규 카테고리 **영화후기**이며, 전용 유튜브 채널·Fish Audio 보이스·이미지 모델을 붙인다.

## 현재 구조와 격차

| 설정 | 현재 위치 | 범위 |
|---|---|---|
| TTS 보이스 | `options.py`의 `VOICE` 3종 | 작업별 (`content_jobs.params_json`) |
| 이미지 스타일 | `options.py`의 `STYLE` 4종 → 프롬프트 조각 | 작업별 |
| 이미지 모델 | imagegen 서버의 `POPORY_IMAGEGEN_MODEL` 환경변수 | **서버 전역** |
| 유튜브 채널 | `content_categories.youtube_channel_id` | 카테고리별 |

격차는 두 가지다.

1. 보이스·스타일에 **카테고리 기본값이 없다.** 영화후기 작업을 만들 때마다 사람이 매번 같은 값을 고르게 된다.
2. 이미지 모델은 **서버 전역**이라 카테고리마다 다르게 쓸 수단이 아예 없다.

TTS는 Google Cloud TTS 단일 공급자다. 로컬 TTS(Qwen3) PoC는 "맥에서 비실용적, Chirp3-HD 유지 권고"로 종결됐고 `services/ttsgen/`은 존재하지 않는다.

## 결정 사항

- **카테고리 기본값은 `defaults_json` 단일 컬럼**에 둔다. 작업의 `params_json`과 같은 형식이라 병합이 `{**기본값, **작업옵션}` 한 줄로 끝나고, 값 검증 로직을 양쪽이 공유한다.
- **작업에서 덮어쓸 수 있다.** 카테고리 값은 기본값이지 강제가 아니다.
- **신규 TTS 공급자는 Fish Audio.** 모델 `s2.1-pro-free`.
- **보이스는 사전 등록 목록**에서 고른다. 포털 보이스 검색·미리듣기 UI는 만들지 않는다.

## 데이터 모델

### 보이스 키가 공급자를 감춘다

사용자는 "목소리"를 고르지 목소리와 공급자를 따로 고르지 않는다. 저장 형식에 `provider` 필드를 만들지 않고 평평한 키 하나를 유지한다.

```python
# options.py
@dataclass(frozen=True)
class VoiceSpec:
    provider: str   # "google" | "fish"
    id: str         # google: voice name / fish: reference_id

VOICE = {
    "female-calm":    VoiceSpec("google", "ko-KR-Chirp3-HD-Aoede"),
    "female-bright":  VoiceSpec("google", "ko-KR-Chirp3-HD-Leda"),
    "male":           VoiceSpec("google", "ko-KR-Neural2-C"),
    "movie-narrator": VoiceSpec("fish", "<reference_id>"),  # 신규
}

IMAGE_MODEL = {"realvisxl", "sd15"}   # 신규 옵션 키
```

`params_json`·`defaults_json`은 여전히 `{"voice": "movie-narrator"}` 형태다. 공급자를 추가하거나 교체해도 저장 포맷이 바뀌지 않는다.

`movie-narrator`의 `reference_id`는 구현 착수 시 확정한다. fish.audio에서 한국어 보이스를 들어보고 고르거나 `GET /v1/voices?language=ko`로 후보를 추린 뒤, 확정된 32자리 ID를 `VOICE` 맵에 상수로 적는다. 보이스를 늘리려면 이 맵에 항목을 추가한다 — 포털 검색 UI는 만들지 않기로 했으므로 코드 수정이 정상 경로다.

`_deepen_voice()` 후처리는 건드리지 않는다. `video.py:390`이 모든 세그먼트에 호출하지만 `VOICE_DEEPEN_SEMITONES` 기본값이 `0`이고 `secrets/env.sh`·plist 어디에도 설정돼 있지 않아 **프로덕션에서 no-op**이다. 보이스별 on/off 필드를 미리 만들 근거가 없다. 나중에 이 후처리를 켜게 되면 그때 `VoiceSpec`에 필드를 더한다.

### 마이그레이션

```sql
ALTER TABLE content_categories ADD COLUMN defaults_json TEXT;
```

nullable 단일 컬럼 추가다. 기존 카테고리는 `NULL`이라 전역 기본값으로 동작한다.

### 병합은 작업 생성 시 스냅샷

API가 카테고리 `defaults_json`과 요청 옵션을 합쳐 최종값을 `content_jobs.params_json`에 굳혀 저장한다.

```
params_json = { ...category.defaults_json, ...request.options }
```

런타임 조회가 아니라 생성 시 스냅샷을 택한 이유는 세 가지다. 카테고리 설정을 나중에 바꿔도 **큐에 이미 들어간 작업이 소급 변경되지 않고**, 워커가 카테고리를 조회할 필요가 없어 **파이썬 쪽 변경이 0**이며, 작업 레코드만 봐도 무엇으로 생성됐는지 알 수 있어 사후 추적이 된다.

`defaults_json`도 `params_json`과 똑같이 `options.py`의 허용값 검사를 통과해야 한다. 카테고리 설정 저장 시 API가 같은 규칙으로 거부한다.

## TTS 공급자 계층

### 패키지 분리

`tts.py`는 200여 줄 중 대부분이 한국어 텍스트 정규화이고 실제 합성은 20줄 남짓이다. 공급자를 붙이면 비대칭이 심해지므로 패키지로 나눈다.

```
popory_content/tts/
├── __init__.py    # synthesize() 디스패치
├── normalize.py   # 한국어 정규화 (공급자 무관, 기존 코드 이동)
├── google.py      # Google Cloud TTS (기존 로직 이동)
└── fish.py        # Fish Audio (신규)
```

각 공급자 모듈은 같은 계약을 지킨다.

```python
def synthesize(text: str, voice_id: str) -> bytes | None
```

정규화는 디스패처가 한 번만 수행하고 공급자 모듈에는 정규화된 텍스트가 전달된다.

### Fish Audio 호출

SDK(`fishaudio` 패키지)를 쓰지 않는다. SDK의 `Model` 타입 리터럴은 `speech-1.5 | speech-1.6 | s1 | s2-pro`뿐이라 `s2.1-pro-free`가 빠져 있고, HTTP 직접 호출이 더 단순하다. `tts.py`가 이미 `requests`를 쓰므로 **새 의존성이 없다.**

```
POST https://api.fish.audio/v1/tts
Authorization: Bearer <FISH_API_KEY>
model: s2.1-pro-free                    ← 헤더
Content-Type: application/json

{"text": "...", "reference_id": "<voice id>", "format": "mp3"}
```

모델을 헤더로 넘기므로 SDK 타입 문제를 우회한다.

인증 키는 기존 패턴을 따라 `GOOGLE_TTS_API_KEY`와 나란히 `FISH_API_KEY`를 `services/content/secrets/env.sh`에 둔다.

### 실패 처리

Google 경로의 기존 동작은 유지한다 — 합성 실패 시 문장 단위로 macOS `say` 폴백. 검증된 동작을 건드릴 이유가 없다.

Fish 경로는 다르게 간다. 429 레이트리밋에 지수 백오프로 재시도하되, **끝내 실패하면 `say`로 떨어지지 않고 작업을 실패시킨다.** `video.py`가 문장마다 합성을 호출하므로 문장 단위 폴백이 걸리면 한 영상 안에서 Fish 음색과 `say` 기계음이 섞인다. 이건 실패보다 나쁜 결과물이다.

`FISH_API_KEY`가 없으면 Fish 보이스를 **검증 단계에서 거부**한다. 런타임에 터지지 않게 한다.

## 카테고리별 이미지 모델

### ModelManager가 로드된 모델을 기억한다

```python
def __init__(self, loader: Callable[[str], Any], idle_seconds=600,
             default_model="realvisxl", clock=time.monotonic):
    self._model: str | None = None
    self._default = default_model

def generate(self, prompt: str, model: str | None = None, **kw):
    want = model or self._default
    with self._lock:
        if self._pipe is not None and self._model != want:
            self._pipe.close(); self._pipe = None; self._model = None; gc.collect()
        if self._pipe is None:
            self._pipe = self._loader(want); self._model = want
        self._last_used = self._clock()
        return self._pipe.generate(prompt, **kw)
```

기존 락이 생성을 직렬화하므로 교체도 같은 락 안에서 안전하다. 로더 시그니처가 `Callable[[], Any]` → `Callable[[str], Any]`로 바뀌는데 `build_pipe(model_name)`은 이미 그 인자를 받는다. 배선만 연결한다.

교체는 언로드 후 로드라 항상 파이프 하나만 상주한다. 맥미니 M4 16GB 공유 메모리 제약이 그대로 지켜진다.

### API 표면

- `POST /generate` — 요청 본문에 `model` 선택 필드 추가. 없으면 환경변수 기본값
- `GET /health` — 현재 환경변수 값을 보고한다. **실제 로드된 모델**을 보고하도록 바꾼다

워커 변경은 한 줄이다. `{"prompt": prompt}` → `{"prompt": prompt, "model": opts["image_model"]}`.

### 교체 비용

워커는 단일 폴 루프로 작업을 하나씩 claim하고(`worker.py:80`), 한 작업의 모든 장면이 같은 모델을 쓴다. imagegen 호출자도 워커 하나뿐이다(`worker.py:285`). 따라서 **모델 교체는 작업당 최대 1회**다.

10분 영상이 16장면 × 약 18초 ≈ 290초이므로 재로드 비용이 그 위에 얹혀도 비율이 크지 않다. 다만 **SDXL 로드 + LoRA fuse 실측 시간은 측정되지 않았다.** 구현 단계에서 재고, 예상보다 크면 카테고리를 묶어 처리하는 순서 조정을 검토한다.

`image_style`(프롬프트 조각)과 `image_model`(파이프라인)은 직교하는 축이다. 스타일은 지금처럼 작업별로 남는다.

## API와 포털 UI

| 엔드포인트 | 변경 |
|---|---|
| `GET /api/content/categories` | SELECT에 `defaults_json` 추가 — 작업 생성 폼 프리필에 필요 |
| `PATCH /api/content/categories/:id` | `defaults` 필드 수용, 허용값 검증 후 저장 |
| 작업 생성 | 카테고리 `defaults_json`과 요청 옵션을 병합해 `params_json`에 스냅샷 |

검증 규칙은 `@popory/types`의 zod 스키마에 두고 파이썬 `options.py`의 허용값과 같은 목록을 공유해야 한다. **두 언어에 값 목록이 이중으로 존재하는 것이 이 설계의 유일한 구조적 약점이다.** 목록이 어긋나면 API는 통과시키는데 워커가 기본값으로 되돌리는 조용한 버그가 난다. 계약 테스트로 잠근다.

UI는 두 곳이다.

- `content/c/[id]` 카테고리 상세에 **"생성 기본값"** 섹션 추가. 기존 `CategoryYoutube` 컴포넌트 옆에 목소리·이미지 모델·이미지 스타일·길이 네 개의 select를 둔다.
- `content/new/NewJobForm`은 카테고리 선택이 바뀌면 옵션 select를 그 카테고리 기본값으로 다시 채운다. 이미 `categories` 배열을 props로 받으므로 `defaults_json`만 실려 오면 클라이언트에서 처리된다. 사용자가 손대면 그 값이 이긴다.

영화후기 카테고리 자체는 새로 만들 것이 없다. `CreateCategory`로 만들고 `CategoryYoutube`로 새 채널을 연결한 뒤 "생성 기본값"에서 보이스·모델을 지정하면 된다. 기존 기능의 조합이다.

## 테스트

| 대상 | 확인 |
|---|---|
| `options.py` | 병합 우선순위(작업 > 카테고리 > 전역), 허용값 밖 입력은 기본값으로 복귀 |
| `tts` 디스패치 | 스펙의 provider대로 라우팅, 정규화는 한 번만 적용 |
| `fish.py` | HTTP 목킹 — 성공, 429 백오프 재시도, 최종 실패 시 작업 실패 |
| `video.py` | `synthesize`에 `VoiceSpec`이 전달되고 기존 렌더 경로가 회귀 없이 통과 |
| `ModelManager` | 모델 불일치 시 언로드→로드, 일치 시 재사용, 유휴 언로드 회귀 없음 |
| imagegen 서버 | `/generate`가 `model` 반영, `/health`가 로드된 모델 보고 |
| 계약 | TS zod 허용값 == 파이썬 `options.py` 허용값 |

마지막 계약 테스트가 위에서 말한 이중 목록 약점을 막는 자물쇠다.

## 롤아웃

이 변경은 영화후기 카테고리를 만들기 전까지 아무것도 바꾸지 않는다.

- 마이그레이션은 nullable 컬럼 추가뿐 — 기존 카테고리는 `NULL`이라 전역 기본값으로 동작
- `VOICE` 값이 문자열에서 `VoiceSpec`으로 바뀌지만 **키는 그대로**라 저장된 `params_json`이 전부 유효
- `synthesize`의 키워드 이름 `voice`를 유지하므로 `test_video.py`의 기존 몽키패치가 그대로 동작
- `FISH_API_KEY` 부재 시 Fish 보이스는 검증에서 거부

## 위험과 미해결 질문

### 1. Fish Audio 무료 등급의 상업적 라이선스 (착수 전 확인 필수)

무료 등급은 **"라이선스: 제한적"**이고 상업적 라이선스는 유료 플랜에만 포함된다. 영화후기는 유튜브 채널에 공개 발행하는 콘텐츠다. 이 배포가 무료 등급의 라이선스 범위에 드는지 블로그 글만으로는 판단할 수 없다.

**구현 착수 전에 이용약관 확인 또는 직접 문의가 필요하다.** 나중에 채널의 기존 영상 전체를 재생성해야 하는 상황이 되면 비용이 훨씬 크다.

부수적으로 요청 데이터가 모델 품질 개선에 사용될 수 있다고 명시돼 있다. 대본이 학습에 쓰일 수 있다는 뜻이며, 공개 콘텐츠라 실질 영향은 작아 보인다.

### 2. 무료 기간 종료 — 2026-08-31

최초 종료일 2026-07-24에서 두 차례 연장돼 8월 31일까지다. 폴백은 선택이 아니라 일정이다.

구조는 그대로 버틴다. `VOICE` 맵에서 해당 항목의 `provider`를 `google`로, `id`를 교체하면 카테고리·작업 데이터를 손대지 않고 전환된다. 유료로 가는 경우 `model` 헤더만 `s2.1-pro`로 바꾼다.

비용은 `s2.1-pro` 기준 $15/M UTF-8 bytes다. 한글은 글자당 3바이트이므로 10분 대본 3,500자 ≈ 10.5KB ≈ **영상당 약 16센트**, 하루 1편이면 월 5달러 수준이다.

### 3. 정규화 프로파일

현재 정규화는 Chirp3-HD의 운율 해석에 맞춰 튜닝돼 있다(말줄임표→쉼표, 대시→쉼표 등). Fish 모델이 문장부호를 어떻게 읽는지는 청취 테스트로 확인해야 한다. 일단 정규화를 공유하고, 어긋나면 공급자별 프로파일로 나눈다.

### 4. 모델 교체 실측 시간

위 "교체 비용" 절 참조. 미측정 값이다.

## 범위 밖

- TTS 사용량·비용 기록 (`usage.py` 확장)
- 포털 보이스 검색·미리듣기 UI
- 세 번째 TTS 공급자
- 이미지 모델 추가 (`realvisxl`·`sd15` 외)

필요해지면 이 구조 위에 붙는다.

## 참고

- [Fish Audio S2.1 Pro 무료 API 공지](https://fish.audio/ko/blog/s2-1-pro-free-api/)
- [Fish Audio 가격·레이트리밋](https://docs.fish.audio/developer-guide/models-pricing/pricing-and-rate-limits)
