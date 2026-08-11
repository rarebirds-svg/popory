# 카테고리별 TTS·이미지 모델 설정 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 콘텐츠 카테고리마다 다른 TTS 보이스(Google/Fish Audio)와 이미지 모델을 기본값으로 지정하고, 작업 생성 시 그 기본값을 덮어쓸 수 있게 한다.

**Architecture:** 카테고리에 `defaults_json` 컬럼 하나를 더하고, 작업 생성 시 `{...카테고리기본값, ...요청옵션}`으로 병합해 `content_jobs.params_json`에 스냅샷으로 굳힌다. 워커는 지금처럼 `params_json`만 읽으므로 조회 로직이 늘지 않는다. TTS는 공급자별 모듈로 나누고 보이스 키가 공급자를 감춘다. 이미지는 `ModelManager`가 요청 모델과 로드된 모델이 다를 때 파이프라인을 교체한다.

**Tech Stack:** Python 3.11(`services/content`, `services/imagegen`), Hono on Cloudflare Workers(`workers/api`), D1(SQLite), Next.js(`apps/portal`), zod(`packages/types`), pytest, vitest.

**설계 문서:** `docs/superpowers/specs/2026-08-02-content-category-model-settings-design.md`

## Global Constraints

- 신규 소스 파일 첫 줄에 그 파일의 역할을 설명하는 한 줄짜리 한국어 주석을 넣는다 (`AGENTS.md` 규칙 6). Python·Shell은 `#`, TS·TSX는 `//`, SQL은 `--`.
- 한국어 문장은 마침표로 끝낸다. 콜론 종결 금지 (`AGENTS.md` 규칙 5).
- 기존 코드 스타일을 따른다. 인접 코드를 "개선"하지 않는다 (`AGENTS.md` 규칙 3).
- 백엔드 파이썬은 `from __future__ import annotations`와 현대 제네릭(`list[…]`, `X | None`)을 쓴다.
- 이미 저장된 `params_json`의 보이스 키(`female-calm`·`female-bright`·`male`)는 계속 유효해야 한다.
- `synthesize`의 키워드 인자 이름 `voice`를 유지한다. `test_video.py`가 `lambda text, voice=None`으로 몽키패치하고 있다.
- 테스트 실행 위치. `services/content`와 `services/imagegen`은 각 디렉토리에서 `pytest`, `workers/api`는 `pnpm test`, 전체는 루트에서 `pnpm test`.
- 커밋은 태스크마다 하나씩, 시맨틱 메시지로 남긴다.

---

## File Structure

**생성**

| 파일 | 책임 |
|---|---|
| `services/content/popory_content/tts/__init__.py` | 보이스 스펙을 받아 공급자 모듈로 디스패치. 정규화를 한 번만 수행 |
| `services/content/popory_content/tts/normalize.py` | 한국어 TTS 전처리. 공급자 무관 |
| `services/content/popory_content/tts/google.py` | Google Cloud TTS 호출 |
| `services/content/popory_content/tts/fish.py` | Fish Audio 호출 |
| `services/content/tests/test_tts_fish.py` | Fish 공급자 테스트 |
| `infra/migrations/00NN_category_defaults.sql` | `defaults_json` 컬럼 추가 |
| `apps/portal/src/app/(authed)/content/c/[id]/CategoryDefaults.tsx` | 카테고리 생성 기본값 편집 UI |

**삭제**

| 파일 | 사유 |
|---|---|
| `services/content/popory_content/tts.py` | 같은 이름의 패키지로 대체 |

**수정**

| 파일 | 변경 |
|---|---|
| `services/content/popory_content/options.py` | `VoiceSpec`, `IMAGE_MODEL`, `image_model` 옵션 키 |
| `services/content/popory_content/video.py` | `voice` 인자 타입을 `VoiceSpec`로 |
| `services/content/popory_content/worker.py` | 보이스 스펙 전달, imagegen 요청에 `model` 포함 |
| `services/imagegen/popory_imagegen/model.py` | `ModelManager` 모델 교체 |
| `services/imagegen/popory_imagegen/server.py` | `/generate`의 `model`, `/health`의 로드된 모델 |
| `packages/types/src/content_category.ts` | `CategoryDefaultsSchema`, `CategoryPatchSchema` 확장 |
| `workers/api/src/routes/content_categories.ts` | `defaults_json` 조회·저장 |
| `workers/api/src/routes/content_jobs.ts` | 카테고리 기본값 병합 |
| `apps/portal/src/app/(authed)/content/c/[id]/page.tsx` | `CategoryDefaults` 배치 |
| `apps/portal/src/app/(authed)/content/new/NewJobForm.tsx` | 카테고리 선택 시 옵션 프리필 |
| `services/content/tests/test_options.py` | `VoiceSpec` 반영 |

---

## Task 1: options.py — VoiceSpec과 image_model

**Files:**
- Modify: `services/content/popory_content/options.py`
- Test: `services/content/tests/test_options.py`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces:
  - `VoiceSpec(provider: str, id: str)` — frozen dataclass
  - `VOICE: dict[str, VoiceSpec]` — 키는 기존 3종 유지
  - `IMAGE_MODEL: set[str]` = `{"realvisxl", "sd15"}`
  - `parse_options(params_json: str | None) -> dict` — 반환 dict에 `image_model` 키 추가
  - `parse_shorts_options(params_json: str | None) -> dict` — 동일

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`services/content/tests/test_options.py` 끝에 추가한다.

```python
from popory_content.options import IMAGE_MODEL, VoiceSpec


def test_voice_map_is_specs():
    assert isinstance(VOICE["male"], VoiceSpec)
    assert VOICE["male"].provider == "google"
    assert VOICE["male"].id.startswith("ko-KR")


def test_image_model_default_and_validation():
    assert parse_options(None)["image_model"] == "realvisxl"
    assert parse_options('{"image_model":"sd15"}')["image_model"] == "sd15"
    assert parse_options('{"image_model":"nope"}')["image_model"] == "realvisxl"
    assert IMAGE_MODEL == {"realvisxl", "sd15"}


def test_shorts_image_model():
    assert parse_shorts_options(None)["image_model"] == "realvisxl"
    assert parse_shorts_options('{"image_model":"sd15"}')["image_model"] == "sd15"
```

기존 `test_maps_cover_keys`의 `assert VOICE["male"].startswith("ko-KR")`는 `VoiceSpec`에서 깨진다. 다음으로 바꾼다.

```python
def test_maps_cover_keys():
    assert set(SCENE_COUNT) == {"3", "5", "7", "10"}
    assert VOICE["male"].id.startswith("ko-KR")
    assert "watercolor" in STYLE["watercolor"]
```

기존 `test_defaults_when_none`도 `image_model`이 늘어 깨진다. 다음으로 바꾼다.

```python
def test_defaults_when_none():
    o = parse_options(None)
    assert o == {"length": "10", "voice": "male", "image_style": "photo",
                 "image_model": "realvisxl"}
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `cd services/content && pytest tests/test_options.py -v`
Expected: FAIL — `ImportError: cannot import name 'IMAGE_MODEL'`

- [ ] **Step 3: 최소 구현**

`services/content/popory_content/options.py`의 상단을 다음으로 바꾼다.

```python
# youtube 작업의 params_json(길이·목소리·배경스타일·이미지모델) 파싱·매핑.
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceSpec:
    """보이스 하나의 공급자와 식별자. 공급자는 저장 형식에 노출되지 않는다."""

    provider: str  # "google" | "fish"
    id: str        # google: voice name / fish: reference_id


SCENE_COUNT = {"3": 5, "5": 8, "7": 12, "10": 16}
SHORT_SCENE_COUNT = {"15": 3, "30": 5, "60": 8}
VOICE = {
    "female-calm": VoiceSpec("google", "ko-KR-Chirp3-HD-Aoede"),
    "female-bright": VoiceSpec("google", "ko-KR-Chirp3-HD-Leda"),
    "male": VoiceSpec("google", "ko-KR-Neural2-C"),
}
STYLE = {
    "photo": "photorealistic, cinematic",
    "illust": "digital illustration, clean",
    "watercolor": "watercolor painting",
    "minimal": "minimalist flat design",
}
IMAGE_MODEL = {"realvisxl", "sd15"}
DEFAULTS = {"length": "10", "voice": "male", "image_style": "photo",
            "image_model": "realvisxl"}
SHORTS_DEFAULTS = {"length": "60", "voice": "male", "image_style": "photo",
                   "image_model": "realvisxl", "upload_targets": []}
```

`parse_options` 안에서 `image_style` 검사 바로 아래에 추가한다.

```python
        if data.get("image_model") in IMAGE_MODEL:
            opts["image_model"] = data["image_model"]
```

`parse_shorts_options`에도 같은 세 줄을 `image_style` 검사 아래에 넣는다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/content && pytest tests/test_options.py -v`
Expected: PASS (전부)

- [ ] **Step 5: 전체 스위트로 회귀를 확인한다**

Run: `cd services/content && pytest -q`
Expected: `VOICE`를 문자열로 쓰던 곳이 있으면 여기서 드러난다. 실패하면 Task 3에서 고칠 대상이므로 어떤 테스트가 깨졌는지 기록만 하고 넘어간다. 단 `test_options.py`는 반드시 통과해야 한다.

- [ ] **Step 6: 커밋**

```bash
git add services/content/popory_content/options.py services/content/tests/test_options.py
git commit -m "feat(options): VoiceSpec 도입 + image_model 옵션 키 추가"
```

---

## Task 2: tts 패키지 분리 (순수 이동)

동작을 바꾸지 않는 리팩터링이다. `test_tts.py`가 안전망이다.

**Files:**
- Create: `services/content/popory_content/tts/__init__.py`
- Create: `services/content/popory_content/tts/normalize.py`
- Create: `services/content/popory_content/tts/google.py`
- Delete: `services/content/popory_content/tts.py`
- Test: `services/content/tests/test_tts.py` (수정 없이 통과해야 한다)

**Interfaces:**
- Consumes: 없음
- Produces:
  - `popory_content.tts.normalize._prep_text(text: str) -> str`
  - `popory_content.tts.google.synthesize(text: str, voice_id: str) -> bytes | None`
  - `popory_content.tts.synthesize(text: str, voice: str = "ko-KR-Chirp3-HD-Aoede") -> bytes | None` — 이 태스크에서는 시그니처 유지

- [ ] **Step 1: 이동 전 기준선을 잡는다**

Run: `cd services/content && pytest tests/test_tts.py -v`
Expected: PASS. 통과하는 테스트 수를 적어둔다 — 이동 후 같아야 한다.

- [ ] **Step 2: 파일을 나눈다**

`popory_content/tts.py`의 내용을 다음과 같이 옮긴다. **로직은 한 줄도 바꾸지 않는다.**

`popory_content/tts/normalize.py` — 첫 줄에 헤더 주석을 넣고, 기존 파일의 `import base64`를 제외한 임포트와 `LANGUAGE` 아래 모든 정규식 상수, 그리고 `_normalize_for_tts`·`_sino_4`·`_sino_korean`·`_read_decimal`·`_read_number`·`_prep_text`·`_to_ssml`·`_comma_break` 함수를 그대로 옮긴다.

```python
# TTS 직전 한국어 텍스트 정규화 — 숫자 읽기·문장부호 운율 보정. 공급자 무관.
```

`popory_content/tts/google.py` — 헤더 주석, `TTS_URL`·`LANGUAGE` 상수, 기존 `synthesize` 본문을 옮기되 인자 이름만 `voice_id`로 바꾼다.

```python
# Google Cloud Text-to-Speech 호출. 키 없거나 실패하면 None.
```

`popory_content/tts/__init__.py` — 디스패치 자리이지만 이 태스크에서는 기존 공개 표면을 그대로 재노출한다.

```python
# TTS 진입점 — 텍스트 정규화 후 공급자 모듈로 디스패치.
from __future__ import annotations

from popory_content.tts import google
from popory_content.tts.normalize import _prep_text  # test_tts.py 하위호환 재노출

__all__ = ["synthesize", "_prep_text"]


def synthesize(text: str, voice: str = "ko-KR-Chirp3-HD-Aoede") -> bytes | None:
    return google.synthesize(text, voice)
```

`popory_content/tts.py`를 삭제한다.

- [ ] **Step 3: 테스트가 그대로 통과하는지 확인한다**

Run: `cd services/content && pytest tests/test_tts.py -v`
Expected: PASS, Step 1과 같은 개수.

`from popory_content import tts` 후 `tts.TTS_URL`을 참조하는 테스트가 있으면 `__init__.py`에 `from popory_content.tts.google import TTS_URL`을 추가하고 `__all__`에도 넣는다.

- [ ] **Step 4: 전체 스위트**

Run: `cd services/content && pytest -q`
Expected: Task 1 Step 5에서 기록한 실패 외에 새로운 실패가 없어야 한다.

- [ ] **Step 5: 커밋**

```bash
git add -A services/content/popory_content/tts services/content/popory_content/tts.py
git commit -m "refactor(tts): 공급자 분리를 위해 tts 를 패키지로 나눔 (동작 변경 없음)"
```

---

## Task 3: VoiceSpec 디스패치 배선

**Files:**
- Modify: `services/content/popory_content/tts/__init__.py`
- Modify: `services/content/popory_content/video.py:352,462` (`voice` 인자 기본값·타입)
- Modify: `services/content/popory_content/worker.py:96,110`
- Test: `services/content/tests/test_tts.py` (신규 케이스 추가)

**Interfaces:**
- Consumes: `options.VoiceSpec`, `options.VOICE`, `tts.google.synthesize`
- Produces: `tts.synthesize(text: str, voice: VoiceSpec | None = None) -> bytes | None`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`services/content/tests/test_tts.py` 끝에 추가한다.

```python
def test_dispatch_routes_by_provider(monkeypatch):
    from popory_content import tts
    from popory_content.options import VoiceSpec

    called = {}

    def fake_google(text, voice_id):
        called["google"] = (text, voice_id)
        return b"G"

    monkeypatch.setattr(tts.google, "synthesize", fake_google)
    out = tts.synthesize("안녕하세요.", voice=VoiceSpec("google", "ko-KR-Neural2-C"))
    assert out == b"G"
    assert called["google"][1] == "ko-KR-Neural2-C"


def test_dispatch_defaults_to_male_when_voice_is_none(monkeypatch):
    from popory_content import tts

    seen = {}
    monkeypatch.setattr(tts.google, "synthesize",
                        lambda text, voice_id: seen.setdefault("id", voice_id) or b"G")
    tts.synthesize("안녕하세요.")
    assert seen["id"] == "ko-KR-Neural2-C"


def test_dispatch_normalizes_once(monkeypatch):
    from popory_content import tts
    from popory_content.options import VoiceSpec

    seen = {}
    monkeypatch.setattr(tts.google, "synthesize",
                        lambda text, voice_id: seen.setdefault("text", text) or b"G")
    tts.synthesize("1,700원…", voice=VoiceSpec("google", "x"))
    assert "…" not in seen["text"]
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `cd services/content && pytest tests/test_tts.py -k dispatch -v`
Expected: FAIL — `synthesize()` 가 `VoiceSpec`을 문자열로 취급해 `google.synthesize`에 스펙 객체가 그대로 넘어간다.

- [ ] **Step 3: 디스패처를 구현한다**

`popory_content/tts/__init__.py`를 다음으로 바꾼다.

```python
# TTS 진입점 — 텍스트 정규화 후 공급자 모듈로 디스패치.
from __future__ import annotations

from popory_content import options
from popory_content.tts import google
from popory_content.tts.normalize import _prep_text  # test_tts.py 하위호환 재노출

__all__ = ["synthesize", "_prep_text"]

_PROVIDERS = {"google": google.synthesize}


def synthesize(text: str, voice: options.VoiceSpec | None = None) -> bytes | None:
    """정규화된 텍스트를 스펙의 공급자로 보낸다. 미지원 공급자면 None."""
    spec = voice or options.VOICE[options.DEFAULTS["voice"]]
    fn = _PROVIDERS.get(spec.provider)
    if fn is None:
        return None
    return fn(text, spec.id)
```

정규화는 각 공급자 모듈이 아니라 여기서 한 번만 돌아야 한다. `google.synthesize` 안에 이미 `_prep_text` 호출이 있으면 그대로 둔다 — 공급자 모듈이 자기 입력을 정규화하는 구조가 유지되면 `test_dispatch_normalizes_once`가 통과한다. 없으면 `google.synthesize` 첫 줄에서 `_prep_text(text)`를 호출하도록 옮긴다.

- [ ] **Step 4: video.py 배선**

`video.py`의 두 시그니처에서 `voice` 기본값을 바꾼다.

352행 근처.
```python
                 image_fetcher: Any = None, voice: "VoiceSpec | None" = None,
```

462행 근처.
```python
               voice: "VoiceSpec | None" = None,
```

파일 상단 임포트에 추가한다.
```python
from popory_content.options import VoiceSpec
```

`synthesize(sent, voice=voice)` 호출부(383행 근처)는 **바꾸지 않는다.** 키워드 이름이 그대로라 `test_video.py`의 몽키패치가 계속 동작한다.

- [ ] **Step 5: worker.py 배선**

96행과 110행의 `voice=VOICE[opts["voice"]]`는 이제 `VoiceSpec`을 넘긴다. **코드 변경이 필요 없다** — `VOICE` 값의 타입만 바뀌었기 때문이다. 해당 두 줄을 눈으로 확인하고 수정 없이 넘어간다.

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd services/content && pytest tests/test_tts.py tests/test_video.py tests/test_worker.py -v`
Expected: PASS

- [ ] **Step 7: 전체 스위트**

Run: `cd services/content && pytest -q`
Expected: PASS. Task 1 Step 5에서 기록한 실패가 여기서 모두 해소돼야 한다. 남으면 원인을 찾아 고친다.

- [ ] **Step 8: 커밋**

```bash
git add services/content/popory_content services/content/tests/test_tts.py
git commit -m "feat(tts): VoiceSpec 기반 공급자 디스패치"
```

---

## Task 4: Fish Audio 공급자

**Files:**
- Create: `services/content/popory_content/tts/fish.py`
- Create: `services/content/tests/test_tts_fish.py`
- Modify: `services/content/popory_content/tts/__init__.py` (`_PROVIDERS`에 등록)
- Modify: `services/content/popory_content/options.py` (`VOICE`에 `movie-narrator` 추가)

**Interfaces:**
- Consumes: `tts.normalize`, `options.VoiceSpec`
- Produces:
  - `tts.fish.synthesize(text: str, voice_id: str) -> bytes | None`
  - `tts.fish.FishError` — 재시도 소진 후 던지는 예외
  - `options.VOICE["movie-narrator"]`

- [ ] **Step 1: 보이스 ID를 확정한다**

Fish Audio 콘솔에서 API 키를 발급받아 셸에 넣는다.

```bash
export FISH_API_KEY=...
curl -s -H "Authorization: Bearer $FISH_API_KEY" \
  "https://api.fish.audio/model?language=ko&page_size=20" | python3 -m json.tool | head -60
```

응답에서 영화후기 내레이션에 맞는 보이스의 `_id`(32자리 hex)를 고른다. 후보를 fish.audio 웹에서 들어보고 정한다. 확정한 값을 이 태스크의 나머지 단계에서 `<VOICE_ID>` 자리에 넣는다.

키는 `services/content/secrets/env.sh`에 추가한다.

```bash
export FISH_API_KEY=...
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`services/content/tests/test_tts_fish.py`를 만든다.

```python
# Fish Audio TTS 공급자 검증 — 성공·재시도·최종 실패.
import pytest
import responses

from popory_content.tts import fish

URL = "https://api.fish.audio/v1/tts"


@responses.activate
def test_success_returns_audio_bytes(monkeypatch):
    monkeypatch.setenv("FISH_API_KEY", "k")
    responses.add(responses.POST, URL, body=b"MP3", status=200)
    assert fish.synthesize("안녕하세요.", "abc123") == b"MP3"
    req = responses.calls[0].request
    assert req.headers["Authorization"] == "Bearer k"
    assert req.headers["model"] == "s2.1-pro-free"


@responses.activate
def test_no_key_returns_none(monkeypatch):
    monkeypatch.delenv("FISH_API_KEY", raising=False)
    assert fish.synthesize("안녕하세요.", "abc123") is None
    assert len(responses.calls) == 0


@responses.activate
def test_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setenv("FISH_API_KEY", "k")
    monkeypatch.setattr(fish.time, "sleep", lambda s: None)
    responses.add(responses.POST, URL, status=429)
    responses.add(responses.POST, URL, body=b"MP3", status=200)
    assert fish.synthesize("안녕하세요.", "abc123") == b"MP3"
    assert len(responses.calls) == 2


@responses.activate
def test_raises_after_retries_exhausted(monkeypatch):
    monkeypatch.setenv("FISH_API_KEY", "k")
    monkeypatch.setattr(fish.time, "sleep", lambda s: None)
    for _ in range(fish.MAX_ATTEMPTS):
        responses.add(responses.POST, URL, status=429)
    with pytest.raises(fish.FishError):
        fish.synthesize("안녕하세요.", "abc123")


@responses.activate
def test_raises_on_4xx_without_retry(monkeypatch):
    monkeypatch.setenv("FISH_API_KEY", "k")
    responses.add(responses.POST, URL, status=400, body="bad reference_id")
    with pytest.raises(fish.FishError):
        fish.synthesize("안녕하세요.", "abc123")
    assert len(responses.calls) == 1
```

- [ ] **Step 3: 테스트가 실패하는지 확인한다**

Run: `cd services/content && pytest tests/test_tts_fish.py -v`
Expected: FAIL — `ModuleNotFoundError: popory_content.tts.fish`

- [ ] **Step 4: 구현**

`services/content/popory_content/tts/fish.py`를 만든다.

```python
# Fish Audio TTS 호출 — 무료 등급 s2.1-pro-free. 429 는 지수 백오프, 소진 시 FishError.
from __future__ import annotations

import os
import time

import requests

TTS_URL = "https://api.fish.audio/v1/tts"
MODEL = "s2.1-pro-free"
MAX_ATTEMPTS = 4
TIMEOUT_SECONDS = 120  # 무료 등급은 지연 보장이 없다


class FishError(RuntimeError):
    """Fish Audio 합성 실패. 호출측이 작업을 실패시키게 한다."""


def synthesize(text: str, voice_id: str) -> bytes | None:
    """정규화된 텍스트를 합성해 mp3 바이트로 반환. 키가 없으면 None."""
    key = os.environ.get("FISH_API_KEY")
    if not key:
        return None
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "model": MODEL,
    }
    body = {"text": text, "reference_id": voice_id, "format": "mp3"}
    last = ""
    for attempt in range(MAX_ATTEMPTS):
        resp = requests.post(TTS_URL, json=body, headers=headers,
                             timeout=TIMEOUT_SECONDS)
        if resp.status_code == 200:
            return resp.content
        last = f"{resp.status_code}: {resp.text[:200]}"
        retryable = resp.status_code == 429 or resp.status_code >= 500
        if not retryable:
            raise FishError(last)
        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(2 ** attempt)
    raise FishError(f"retries exhausted — {last}")
```

`popory_content/tts/__init__.py`를 고친다.

```python
from popory_content.tts import fish, google
...
_PROVIDERS = {"google": google.synthesize, "fish": fish.synthesize}
```

`popory_content/options.py`의 `VOICE`에 항목을 더한다. `<VOICE_ID>`는 Step 1에서 확정한 값이다.

```python
    "movie-narrator": VoiceSpec("fish", "<VOICE_ID>"),
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd services/content && pytest tests/test_tts_fish.py tests/test_tts.py -v`
Expected: PASS

- [ ] **Step 6: 키 없이 Fish 보이스를 쓰면 렌더 전에 실패시킨다**

`fish.synthesize`가 키 없을 때 `None`을 돌려주면 `video.py`가 문장마다 `say`로 폴백해 기계음 영상이 나온다. 렌더를 시작하기 전에 막는다.

`services/content/tests/test_worker.py`에 테스트를 더한다.

```python
def test_preflight_rejects_fish_voice_without_key(monkeypatch):
    from popory_content import worker
    from popory_content.options import VoiceSpec

    monkeypatch.delenv("FISH_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FISH_API_KEY"):
        worker._require_voice_ready(VoiceSpec("fish", "abc"))


def test_preflight_allows_google_without_fish_key(monkeypatch):
    from popory_content import worker
    from popory_content.options import VoiceSpec

    monkeypatch.delenv("FISH_API_KEY", raising=False)
    worker._require_voice_ready(VoiceSpec("google", "ko-KR-Neural2-C"))  # 예외 없음
```

Run: `cd services/content && pytest tests/test_worker.py -k preflight -v`
Expected: FAIL — `_require_voice_ready` 미존재

`worker.py`에 함수를 더한다.

```python
def _require_voice_ready(spec) -> None:
    """공급자 자격증명이 없으면 렌더 전에 실패시킨다 — 문장별 say 폴백으로
    음색이 섞인 영상이 나오는 것을 막는다."""
    if spec.provider == "fish" and not os.environ.get("FISH_API_KEY"):
        raise RuntimeError("FISH_API_KEY 가 없어 fish 보이스를 쓸 수 없다")
```

96행·110행에서 `render_video`/`render_shorts`를 호출하기 직전에 넣는다.

```python
                _require_voice_ready(VOICE[opts["voice"]])
```

Run: `cd services/content && pytest tests/test_worker.py -v`
Expected: PASS

- [ ] **Step 7: 실제 API로 한 번 합성해 본다**

```bash
cd services/content && source secrets/env.sh && python3 -c "
from popory_content.tts import synthesize
from popory_content.options import VOICE
b = synthesize('영화 후기 내레이션 테스트입니다. 오늘 소개할 작품은 이렇습니다.', voice=VOICE['movie-narrator'])
open('/tmp/fish-test.mp3','wb').write(b); print(len(b), 'bytes')
"
afplay /tmp/fish-test.mp3
```

들어보고 판단한다. 정규화가 Chirp3-HD 기준이라 문장부호가 어색하게 읽히면 설계 문서의 "미해결 질문 3"에 해당하니 **여기서 고치지 말고** 관찰 내용을 기록한 뒤 다음 태스크로 넘어간다.

- [ ] **Step 8: 커밋**

```bash
git add services/content/popory_content services/content/tests/test_tts_fish.py services/content/tests/test_worker.py
git commit -m "feat(tts): Fish Audio 공급자 추가 (s2.1-pro-free)"
```

---

## Task 5: ModelManager 모델 교체

**Files:**
- Modify: `services/imagegen/popory_imagegen/model.py:10-42`
- Test: `services/imagegen/tests/test_model.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `ModelManager(loader: Callable[[str], Any], idle_seconds: int = 600, default_model: str = "realvisxl", clock=time.monotonic)`
  - `ModelManager.generate(prompt: str, model: str | None = None, **kw) -> bytes`
  - `ModelManager.current_model -> str | None`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`services/imagegen/tests/test_model.py` 끝에 추가한다.

```python
class _FakePipe:
    def __init__(self, name):
        self.name = name
        self.closed = False

    def generate(self, prompt, **kw):
        return f"{self.name}:{prompt}".encode()

    def close(self):
        self.closed = True


def test_swaps_pipe_when_model_differs():
    built = []

    def loader(name):
        built.append(name)
        return _FakePipe(name)

    m = ModelManager(loader=loader, default_model="realvisxl")
    assert m.generate("a") == b"realvisxl:a"
    assert m.current_model == "realvisxl"
    assert m.generate("b", model="sd15") == b"sd15:b"
    assert built == ["realvisxl", "sd15"]
    assert m.current_model == "sd15"


def test_reuses_pipe_when_model_matches():
    built = []

    def loader(name):
        built.append(name)
        return _FakePipe(name)

    m = ModelManager(loader=loader, default_model="realvisxl")
    m.generate("a", model="sd15")
    m.generate("b", model="sd15")
    assert built == ["sd15"]


def test_closes_old_pipe_on_swap():
    pipes = []

    def loader(name):
        p = _FakePipe(name)
        pipes.append(p)
        return p

    m = ModelManager(loader=loader, default_model="realvisxl")
    m.generate("a")
    m.generate("b", model="sd15")
    assert pipes[0].closed is True
    assert pipes[1].closed is False
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `cd services/imagegen && pytest tests/test_model.py -v`
Expected: FAIL — `TypeError: loader() takes 0 positional arguments but 1 was given` 또는 `AttributeError: current_model`

- [ ] **Step 3: 구현**

`services/imagegen/popory_imagegen/model.py`의 `ModelManager`를 다음으로 바꾼다.

```python
class ModelManager:
    """파이프라인을 lazy-load 하고, 직렬화 생성하며, 유휴 시 언로드한다.
    요청 모델이 로드된 것과 다르면 언로드 후 재로드한다 — 16GB 공유 메모리라
    두 파이프를 동시에 올릴 수 없다.
    loader(model_name)는 generate(prompt, **kw)->bytes 와 close() 를 가진 객체를 반환한다."""

    def __init__(self, loader: Callable[[str], Any], idle_seconds: int = 600,
                 default_model: str = "realvisxl",
                 clock: Callable[[], float] = time.monotonic):
        self._loader = loader
        self._idle = idle_seconds
        self._default = default_model
        self._clock = clock
        self._pipe: Any = None
        self._model: str | None = None
        self._last_used: float | None = None
        self._lock = threading.Lock()

    def generate(self, prompt: str, model: str | None = None, **kw: Any) -> bytes:
        want = model or self._default
        with self._lock:
            if self._pipe is not None and self._model != want:
                self._pipe.close()
                self._pipe = None
                self._model = None
                gc.collect()
            if self._pipe is None:
                self._pipe = self._loader(want)
                self._model = want
            self._last_used = self._clock()
            return self._pipe.generate(prompt, **kw)

    def maybe_unload(self) -> None:
        with self._lock:
            if self._pipe is None or self._last_used is None:
                return
            if self._clock() - self._last_used >= self._idle:
                self._pipe.close()
                self._pipe = None
                self._model = None
                self._last_used = None
                gc.collect()

    @property
    def loaded(self) -> bool:
        return self._pipe is not None

    @property
    def current_model(self) -> str | None:
        return self._model
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/imagegen && pytest tests/test_model.py -v`
Expected: PASS. 기존 테스트가 `loader=lambda: ...` 형태로 인자 없는 로더를 쓰고 있으면 `lambda name: ...`으로 고친다.

- [ ] **Step 5: 커밋**

```bash
git add services/imagegen/popory_imagegen/model.py services/imagegen/tests/test_model.py
git commit -m "feat(imagegen): ModelManager 가 요청 모델에 따라 파이프를 교체"
```

---

## Task 6: imagegen 서버의 model 파라미터

**Files:**
- Modify: `services/imagegen/popory_imagegen/server.py:24-26,45-51,71`
- Test: `services/imagegen/tests/test_server.py`

**Interfaces:**
- Consumes: `ModelManager.generate(prompt, model=...)`, `ModelManager.current_model`
- Produces:
  - `POST /generate` 본문에 `model` 선택 필드
  - `GET /health` 응답의 `model`이 실제 로드된 모델(`null` 가능)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`services/imagegen/tests/test_server.py` 끝에 추가한다. 기존 파일의 서버 기동 헬퍼와 같은 방식을 쓴다.

```python
def test_generate_passes_model_to_manager():
    seen = {}

    class M:
        loaded = True
        current_model = "sd15"

        def generate(self, prompt, model=None, **kw):
            seen["model"] = model
            return b"PNG"

    srv = make_server(M(), port=0)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        r = requests.post(f"http://127.0.0.1:{port}/generate",
                          json={"prompt": "x", "model": "sd15"}, timeout=5)
        assert r.status_code == 200
        assert seen["model"] == "sd15"
    finally:
        srv.shutdown()


def test_health_reports_loaded_model():
    class M:
        loaded = True
        current_model = "sd15"

        def generate(self, prompt, model=None, **kw):
            return b"PNG"

    srv = make_server(M(), port=0)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        r = requests.get(f"http://127.0.0.1:{port}/health", timeout=5)
        assert r.json()["model"] == "sd15"
    finally:
        srv.shutdown()


def test_generate_rejects_unknown_model():
    class M:
        loaded = True
        current_model = None

        def generate(self, prompt, model=None, **kw):
            return b"PNG"

    srv = make_server(M(), port=0)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        r = requests.post(f"http://127.0.0.1:{port}/generate",
                          json={"prompt": "x", "model": "nope"}, timeout=5)
        assert r.status_code == 400
    finally:
        srv.shutdown()
```

파일 상단에 `import threading`과 `import requests`, `from popory_imagegen.server import make_server`가 없으면 추가한다.

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `cd services/imagegen && pytest tests/test_server.py -v`
Expected: FAIL — `model`이 매니저로 전달되지 않고, `/health`가 환경변수 값을 돌려준다.

- [ ] **Step 3: 구현**

`server.py`의 `do_GET`을 고친다.

```python
        def do_GET(self) -> None:
            if self.path == "/health":
                self._json(200, {"loaded": getattr(manager, "loaded", False),
                                 "model": getattr(manager, "current_model", None)})
            else:
                self._json(404, {"error": "not found"})
```

`do_POST`의 prompt 검증 아래에 모델 검증을 넣고 `generate` 호출에 전달한다.

```python
            model = body.get("model")
            if model is not None and model not in ALLOWED_MODELS:
                self._json(400, {"error": "bad model"})
                return
            try:
                png = manager.generate(
                    prompt,
                    model=model,
                    negative_prompt=body.get("negative_prompt"),
                    steps=body.get("steps"),
                    width=body.get("width"),
                    height=body.get("height"),
                )
```

파일 상단에 상수를 더한다. `options.py`의 `IMAGE_MODEL`과 같은 값이어야 하지만 서비스가 달라 임포트할 수 없으므로 여기 따로 둔다.

```python
# popory_content.options.IMAGE_MODEL 과 같은 목록을 유지해야 한다.
ALLOWED_MODELS = {"realvisxl", "sd15"}
```

`main()`의 매니저 생성에 기본 모델을 넘긴다.

```python
    manager = ModelManager(
        loader=build_pipe,
        idle_seconds=idle,
        default_model=os.environ.get("POPORY_IMAGEGEN_MODEL", "realvisxl"),
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/imagegen && pytest -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add services/imagegen
git commit -m "feat(imagegen): /generate 의 model 파라미터와 /health 의 로드된 모델 보고"
```

---

## Task 7: 워커가 이미지 모델을 전달

**Files:**
- Modify: `services/content/popory_content/worker.py:285`
- Test: `services/content/tests/test_worker.py`

**Interfaces:**
- Consumes: `options.parse_options` 반환 dict의 `image_model`
- Produces: imagegen 요청 본문에 `model` 포함

- [ ] **Step 1: `_safe_image` 경로를 읽는다**

Run: `cd services/content && sed -n '275,300p' popory_content/worker.py`

`_safe_image(client, prompt, job_id)`가 `requests.post(IMAGEGEN_URL, json={"prompt": prompt}, ...)`를 호출하는 것을 확인한다. 이 함수는 `worker.py:93,107,135`에서 람다로 감싸 `image_fetcher`로 넘겨진다.

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`services/content/tests/test_worker.py` 끝에 추가한다.

```python
@responses.activate
def test_safe_image_sends_model(monkeypatch):
    from popory_content import worker

    responses.add(responses.POST, worker.IMAGEGEN_URL, body=b"PNG", status=200)
    worker._safe_image(None, "a prompt", "job1", model="sd15")
    body = json.loads(responses.calls[0].request.body)
    assert body["model"] == "sd15"
    assert body["prompt"] == "a prompt"
```

`json`과 `responses` 임포트가 파일에 없으면 추가한다.

- [ ] **Step 3: 테스트가 실패하는지 확인한다**

Run: `cd services/content && pytest tests/test_worker.py -k safe_image_sends_model -v`
Expected: FAIL — `_safe_image() got an unexpected keyword argument 'model'`

- [ ] **Step 4: 구현**

`_safe_image` 시그니처에 `model` 키워드를 더하고 요청 본문에 넣는다.

```python
def _safe_image(client, prompt, job_id=None, model=None):
    ...
        payload = {"prompt": prompt}
        if model:
            payload["model"] = model
        resp = requests.post(IMAGEGEN_URL, json=payload, timeout=IMAGE_TIMEOUT_SECONDS)
```

기존 시그니처의 인자 순서와 이름은 그대로 두고 `model`만 마지막에 더한다. 호출부 세 곳(93·107·135행)의 람다에 `model`을 실어 준다.

```python
                image_fetcher=lambda p: _safe_image(client, p, job_id,
                                                    model=opts["image_model"]),
```

135행은 `_safe_image(client, p)` 형태이고 인스타그램 이미지 경로다. 이 경로에도 옵션이 있으면 같은 방식으로 넘기고, 없으면 `model` 없이 둔다 — 서버 기본값으로 동작한다.

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd services/content && pytest tests/test_worker.py -v`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add services/content/popory_content/worker.py services/content/tests/test_worker.py
git commit -m "feat(worker): imagegen 요청에 카테고리 이미지 모델 전달"
```

---

## Task 8: D1 마이그레이션과 zod 스키마

**Files:**
- Create: `infra/migrations/00NN_category_defaults.sql`
- Modify: `packages/types/src/content_category.ts`
- Test: `packages/types/src/content_category.test.ts`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `content_categories.defaults_json TEXT` 컬럼
  - `CategoryDefaultsSchema` — `{length?, voice?, image_style?, image_model?}` 전부 optional
  - `CategoryPatchSchema.defaults` — `CategoryDefaultsSchema | null` optional
  - `VOICE_KEYS`, `IMAGE_MODELS`, `IMAGE_STYLES`, `LENGTHS` — 계약 테스트가 참조할 상수

- [ ] **Step 1: 마이그레이션 번호를 확인한다**

Run: `ls infra/migrations | tail -5`

가장 큰 번호 다음 번호를 쓴다. 아래 `00NN`을 그 번호로 바꾼다.

- [ ] **Step 2: 마이그레이션을 만든다**

`infra/migrations/00NN_category_defaults.sql`

```sql
-- 카테고리별 작업 생성 기본값(보이스·이미지 모델·스타일·길이) 저장 컬럼.
ALTER TABLE content_categories ADD COLUMN defaults_json TEXT;
```

- [ ] **Step 3: 실패하는 테스트를 쓴다**

`packages/types/src/content_category.test.ts`가 없으면 만들고, 있으면 끝에 추가한다.

```typescript
// 카테고리 스키마 검증 — 기본값 허용치와 부분 갱신.
import { describe, it, expect } from "vitest";
import { CategoryDefaultsSchema, CategoryPatchSchema, VOICE_KEYS, IMAGE_MODELS } from "./content_category";

describe("CategoryDefaultsSchema", () => {
  it("모든 필드가 선택적이다", () => {
    expect(CategoryDefaultsSchema.safeParse({}).success).toBe(true);
  });

  it("허용된 보이스·모델만 받는다", () => {
    expect(CategoryDefaultsSchema.safeParse({ voice: "movie-narrator", image_model: "sd15" }).success).toBe(true);
    expect(CategoryDefaultsSchema.safeParse({ voice: "nope" }).success).toBe(false);
    expect(CategoryDefaultsSchema.safeParse({ image_model: "nope" }).success).toBe(false);
  });

  it("목록 상수를 노출한다", () => {
    expect(VOICE_KEYS).toContain("movie-narrator");
    expect(IMAGE_MODELS).toEqual(["realvisxl", "sd15"]);
  });
});

describe("CategoryPatchSchema", () => {
  it("defaults 를 받는다", () => {
    expect(CategoryPatchSchema.safeParse({ defaults: { voice: "male" } }).success).toBe(true);
  });

  it("defaults: null 로 초기화할 수 있다", () => {
    expect(CategoryPatchSchema.safeParse({ defaults: null }).success).toBe(true);
  });
});
```

- [ ] **Step 4: 테스트가 실패하는지 확인한다**

Run: `cd packages/types && pnpm test`
Expected: FAIL — `CategoryDefaultsSchema` 미존재

- [ ] **Step 5: 구현**

`packages/types/src/content_category.ts`에 추가한다.

```typescript
// 작업 옵션 허용값 — services/content/popory_content/options.py 와 같은 목록을 유지해야 한다.
export const LENGTHS = ["3", "5", "7", "10"] as const;
export const VOICE_KEYS = ["female-calm", "female-bright", "male", "movie-narrator"] as const;
export const IMAGE_STYLES = ["photo", "illust", "watercolor", "minimal"] as const;
export const IMAGE_MODELS = ["realvisxl", "sd15"] as const;

export const CategoryDefaultsSchema = z.object({
  length: z.enum(LENGTHS).optional(),
  voice: z.enum(VOICE_KEYS).optional(),
  image_style: z.enum(IMAGE_STYLES).optional(),
  image_model: z.enum(IMAGE_MODELS).optional(),
});
export type CategoryDefaults = z.infer<typeof CategoryDefaultsSchema>;
```

`CategoryPatchSchema`에 필드를 더한다.

```typescript
export const CategoryPatchSchema = z.object({
  name: z.string().min(1).max(60).optional(),
  icon: z.string().max(8).nullable().optional(),
  sort_order: z.number().int().min(0).max(9999).optional(),
  defaults: CategoryDefaultsSchema.nullable().optional(),
});
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd packages/types && pnpm test`
Expected: PASS

- [ ] **Step 7: 로컬 D1에 마이그레이션을 적용한다**

Run: `cd infra/wrangler && npx wrangler d1 migrations apply <DB_NAME> --local`

`<DB_NAME>`은 `infra/wrangler/wrangler.toml`의 `[[d1_databases]] database_name` 값이다.

- [ ] **Step 8: 커밋**

```bash
git add infra/migrations packages/types/src/content_category.ts packages/types/src/content_category.test.ts
git commit -m "feat(types): 카테고리 defaults 스키마 + defaults_json 마이그레이션"
```

---

## Task 9: 카테고리 API의 defaults 조회·저장

**Files:**
- Modify: `workers/api/src/routes/content_categories.ts:24-33,63-73`
- Test: `workers/api/src/routes/content_categories.test.ts`

**Interfaces:**
- Consumes: `CategoryPatchSchema.defaults`
- Produces:
  - `GET /api/content/categories` 응답 행에 `defaults_json: string | null`
  - `PATCH /api/content/categories/:id`가 `defaults`를 받아 `defaults_json`에 저장

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`workers/api/src/routes/content_categories.test.ts`의 기존 패턴을 따라 추가한다.

```typescript
it("GET 이 defaults_json 을 포함한다", async () => {
  // 기존 테스트의 카테고리 시드 헬퍼를 재사용한다
  const res = await app.request("/api/content/categories", {}, env);
  const body = await res.json();
  expect(body.categories[0]).toHaveProperty("defaults_json");
});

it("PATCH 가 defaults 를 저장한다", async () => {
  const res = await app.request(`/api/content/categories/${catId}`, {
    method: "PATCH",
    body: JSON.stringify({ defaults: { voice: "movie-narrator", image_model: "sd15" } }),
    headers: { "Content-Type": "application/json" },
  }, env);
  expect(res.status).toBe(204);
  const row = await env.DB.prepare("SELECT defaults_json FROM content_categories WHERE id=?").bind(catId).first();
  expect(JSON.parse(row.defaults_json)).toEqual({ voice: "movie-narrator", image_model: "sd15" });
});

it("PATCH 가 허용값 밖 defaults 를 거부한다", async () => {
  const res = await app.request(`/api/content/categories/${catId}`, {
    method: "PATCH",
    body: JSON.stringify({ defaults: { voice: "nope" } }),
    headers: { "Content-Type": "application/json" },
  }, env);
  expect(res.status).toBe(400);
});
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `cd workers/api && pnpm test content_categories`
Expected: FAIL — `defaults_json` 미포함, PATCH가 `nothing to update` 400을 반환

- [ ] **Step 3: 구현**

`GET` 핸들러의 SELECT에 컬럼을 더한다.

```typescript
      `SELECT c.id, c.name, c.slug, c.icon, c.sort_order, c.defaults_json,
              c.youtube_channel_id, c.youtube_channel_title, c.instagram_account_id, c.instagram_username, c.created_at,
```

`PATCH` 핸들러의 `sets` 조립에 분기를 더한다. `sort_order` 분기 바로 아래다.

```typescript
    if (parsed.data.defaults !== undefined) {
      sets.push("defaults_json=?");
      vals.push(parsed.data.defaults === null ? null : JSON.stringify(parsed.data.defaults));
    }
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd workers/api && pnpm test content_categories`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add workers/api/src/routes/content_categories.ts workers/api/src/routes/content_categories.test.ts
git commit -m "feat(api): 카테고리 defaults 조회·저장"
```

---

## Task 10: 작업 생성 시 기본값 병합

두 생성 경로 모두에 적용해야 한다. `service-create`는 매일 자동 생성(`auto_create.py`)이 쓰는 경로라 영화후기의 주 경로다.

**Files:**
- Modify: `workers/api/src/routes/content_jobs.ts:30-55,57-80`
- Test: `workers/api/src/routes/content_jobs.test.ts`

**Interfaces:**
- Consumes: `content_categories.defaults_json`
- Produces: `mergeCategoryDefaults(db, categoryId, options) -> Promise<string | null>` — `content_jobs.ts` 내부 헬퍼

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`workers/api/src/routes/content_jobs.test.ts`에 추가한다. 기존 테스트의 시드·요청 헬퍼를 재사용한다.

```typescript
it("카테고리 기본값이 params_json 에 스냅샷된다", async () => {
  await env.DB.prepare("UPDATE content_categories SET defaults_json=? WHERE id=?")
    .bind(JSON.stringify({ voice: "movie-narrator", image_model: "sd15" }), catId).run();
  const res = await app.request("/api/content/jobs", {
    method: "POST",
    body: JSON.stringify({ topic: "t", platform: "youtube", category_id: catId }),
    headers: { "Content-Type": "application/json" },
  }, env);
  const { id } = await res.json();
  const row = await env.DB.prepare("SELECT params_json FROM content_jobs WHERE id=?").bind(id).first();
  expect(JSON.parse(row.params_json)).toEqual({ voice: "movie-narrator", image_model: "sd15" });
});

it("작업 옵션이 카테고리 기본값을 이긴다", async () => {
  await env.DB.prepare("UPDATE content_categories SET defaults_json=? WHERE id=?")
    .bind(JSON.stringify({ voice: "movie-narrator", image_model: "sd15" }), catId).run();
  const res = await app.request("/api/content/jobs", {
    method: "POST",
    body: JSON.stringify({ topic: "t", platform: "youtube", category_id: catId, options: { voice: "male" } }),
    headers: { "Content-Type": "application/json" },
  }, env);
  const { id } = await res.json();
  const row = await env.DB.prepare("SELECT params_json FROM content_jobs WHERE id=?").bind(id).first();
  expect(JSON.parse(row.params_json)).toEqual({ voice: "male", image_model: "sd15" });
});

it("카테고리가 없으면 요청 옵션만 저장한다", async () => {
  const res = await app.request("/api/content/jobs", {
    method: "POST",
    body: JSON.stringify({ topic: "t", platform: "youtube", options: { voice: "male" } }),
    headers: { "Content-Type": "application/json" },
  }, env);
  const { id } = await res.json();
  const row = await env.DB.prepare("SELECT params_json FROM content_jobs WHERE id=?").bind(id).first();
  expect(JSON.parse(row.params_json)).toEqual({ voice: "male" });
});
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `cd workers/api && pnpm test content_jobs`
Expected: FAIL — 첫 테스트에서 `params_json`이 `null`

- [ ] **Step 3: 구현**

`content_jobs.ts` 상단(`ulid` 헬퍼 근처)에 병합 헬퍼를 더한다.

```typescript
// 카테고리 기본값과 요청 옵션을 병합해 작업 생성 시점의 스냅샷을 만든다.
// 요청 옵션이 항상 이긴다. 둘 다 없으면 null.
async function mergeCategoryDefaults(
  db: D1Database,
  categoryId: string | null | undefined,
  options: Record<string, unknown> | undefined,
): Promise<string | null> {
  let defaults: Record<string, unknown> = {};
  if (categoryId) {
    const row = await db.prepare("SELECT defaults_json FROM content_categories WHERE id=?")
      .bind(categoryId).first<{ defaults_json: string | null }>();
    if (row?.defaults_json) {
      try {
        const parsed = JSON.parse(row.defaults_json);
        if (parsed && typeof parsed === "object") defaults = parsed;
      } catch {
        // 손상된 기본값은 무시하고 요청 옵션만 쓴다
      }
    }
  }
  const merged = { ...defaults, ...(options ?? {}) };
  return Object.keys(merged).length > 0 ? JSON.stringify(merged) : null;
}
```

`POST /api/content/jobs`의 `paramsJson` 계산을 바꾼다.

```typescript
    const paramsJson = await mergeCategoryDefaults(
      c.env.DB, parsed.data.category_id, parsed.data.options as Record<string, unknown> | undefined);
```

`POST /api/content/jobs/service-create`에서는 `categoryId`를 구한 **뒤에** 계산해야 한다. 기존 `const paramsJson = options ? ... : null;` 줄을 지우고, `categoryId` 확정 이후에 넣는다.

```typescript
    const paramsJson = await mergeCategoryDefaults(
      c.env.DB, categoryId, options as Record<string, unknown> | undefined);
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd workers/api && pnpm test content_jobs`
Expected: PASS

- [ ] **Step 5: 전체 워커 테스트**

Run: `cd workers/api && pnpm test`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add workers/api/src/routes/content_jobs.ts workers/api/src/routes/content_jobs.test.ts
git commit -m "feat(api): 작업 생성 시 카테고리 기본값을 params_json 에 스냅샷"
```

---

## Task 11: 계약 테스트 — TS와 파이썬 허용값 일치

설계 문서가 지목한 유일한 구조적 약점을 잠근다.

**Files:**
- Modify: `services/content/tests/test_contract.py`

**Interfaces:**
- Consumes: `packages/types/src/content_category.ts`의 상수, `options.py`의 맵
- Produces: 없음 (검증만)

- [ ] **Step 1: 기존 계약 테스트 방식을 확인한다**

Run: `cd services/content && head -20 tests/test_contract.py`

파일이 TS 소스를 읽어 비교하는 방식인지 확인한다. 아니면 아래 방식을 새로 쓴다.

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`services/content/tests/test_contract.py` 끝에 추가한다.

```python
import re
from pathlib import Path

from popory_content.options import IMAGE_MODEL, SCENE_COUNT, STYLE, VOICE

_TYPES = Path(__file__).resolve().parents[3] / "packages/types/src/content_category.ts"


def _ts_list(name: str) -> set[str]:
    """content_category.ts 의 `export const NAME = [...] as const;` 를 파싱."""
    src = _TYPES.read_text(encoding="utf-8")
    m = re.search(rf"export const {name} = \[(.*?)\] as const;", src, re.S)
    assert m, f"{name} 을 찾지 못했다"
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def test_voice_keys_match():
    assert _ts_list("VOICE_KEYS") == set(VOICE)


def test_image_models_match():
    assert _ts_list("IMAGE_MODELS") == IMAGE_MODEL


def test_image_styles_match():
    assert _ts_list("IMAGE_STYLES") == set(STYLE)


def test_lengths_match():
    assert _ts_list("LENGTHS") == set(SCENE_COUNT)
```

- [ ] **Step 3: 테스트가 실패하는지 확인한다**

Run: `cd services/content && pytest tests/test_contract.py -k match -v`
Expected: 경로가 맞으면 PASS. 실패하면 `_TYPES` 경로의 `parents[N]`을 조정한다 — `services/content/tests/` 기준으로 리포 루트까지 올라가야 한다. `python3 -c "from pathlib import Path; print(Path('services/content/tests/x').resolve().parents[3])"`로 확인한다.

`ALLOWED_MODELS`(imagegen)도 같은 목록이어야 하므로 다음도 추가한다.

```python
def test_imagegen_allowed_models_match():
    src = (Path(__file__).resolve().parents[3]
           / "services/imagegen/popory_imagegen/server.py").read_text(encoding="utf-8")
    m = re.search(r"ALLOWED_MODELS = \{(.*?)\}", src, re.S)
    assert m
    assert set(re.findall(r'"([^"]+)"', m.group(1))) == IMAGE_MODEL
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/content && pytest tests/test_contract.py -v`
Expected: PASS

- [ ] **Step 5: 일부러 깨뜨려 자물쇠가 동작하는지 본다**

`packages/types/src/content_category.ts`의 `IMAGE_MODELS`에 `"fake"`를 잠시 추가하고 위 테스트를 다시 돌린다. FAIL이 나야 한다. 확인 후 되돌린다.

- [ ] **Step 6: 커밋**

```bash
git add services/content/tests/test_contract.py
git commit -m "test(contract): TS·파이썬·imagegen 의 옵션 허용값 일치 검증"
```

---

## Task 12: 포털 — 카테고리 생성 기본값 UI

**Files:**
- Create: `apps/portal/src/app/(authed)/content/c/[id]/CategoryDefaults.tsx`
- Modify: `apps/portal/src/app/(authed)/content/c/[id]/page.tsx`

**Interfaces:**
- Consumes: `GET /api/content/categories`의 `defaults_json`, `PATCH /api/content/categories/:id`의 `defaults`
- Produces: `<CategoryDefaults categoryId={string} initial={CategoryDefaults | null} />`

- [ ] **Step 1: 기존 컴포넌트 관례를 읽는다**

Run: `cd apps/portal && cat "src/app/(authed)/content/c/[id]/CategoryYoutube.tsx"`

폼 제출·에러 표시·클래스 상수(`INPUT` 등)·`fetch` 래퍼 사용 방식을 그대로 따른다. 새 패턴을 만들지 않는다.

- [ ] **Step 2: 컴포넌트를 만든다**

`apps/portal/src/app/(authed)/content/c/[id]/CategoryDefaults.tsx`

```tsx
// 카테고리 작업 생성 기본값(길이·목소리·이미지 스타일·이미지 모델) 편집 폼.
"use client";

import { useState } from "react";
import { LENGTHS, VOICE_KEYS, IMAGE_STYLES, IMAGE_MODELS, type CategoryDefaults as Defaults } from "@popory/types";

const INPUT = "border border-neutral-300 rounded px-2 py-1 text-sm";

export function CategoryDefaults({ categoryId, initial }: { categoryId: string; initial: Defaults | null }) {
  const [d, setD] = useState<Defaults>(initial ?? {});
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  async function save() {
    setSaving(true);
    setMsg("");
    const res = await fetch(`/api/content/categories/${categoryId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ defaults: Object.keys(d).length ? d : null }),
    });
    setSaving(false);
    setMsg(res.ok ? "저장했습니다." : "저장에 실패했습니다.");
  }

  function field<K extends keyof Defaults>(key: K, label: string, opts: readonly string[]) {
    return (
      <label className="flex items-center gap-2 text-sm">
        <span className="w-24">{label}</span>
        <select
          className={INPUT}
          value={(d[key] as string) ?? ""}
          onChange={(e) => setD({ ...d, [key]: e.target.value || undefined })}
        >
          <option value="">지정 안 함</option>
          {opts.map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
      </label>
    );
  }

  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-semibold">생성 기본값</h2>
      <p className="text-xs text-neutral-500">
        이 카테고리로 작업을 만들 때 미리 채워집니다. 작업에서 바꿀 수 있습니다.
      </p>
      {field("length", "길이", LENGTHS)}
      {field("voice", "목소리", VOICE_KEYS)}
      {field("image_style", "이미지 스타일", IMAGE_STYLES)}
      {field("image_model", "이미지 모델", IMAGE_MODELS)}
      <div className="flex items-center gap-2">
        <button onClick={save} disabled={saving} className="border rounded px-3 py-1 text-sm">
          {saving ? "저장 중" : "저장"}
        </button>
        {msg && <span className="text-xs text-neutral-600">{msg}</span>}
      </div>
    </section>
  );
}
```

`INPUT` 상수와 클래스명은 Step 1에서 읽은 기존 컴포넌트의 값으로 맞춘다.

- [ ] **Step 3: 페이지에 배치한다**

`page.tsx`에서 카테고리 행을 가져오는 부분에 `defaults_json`이 포함되는지 확인하고, `CategoryYoutube` 옆에 렌더한다.

```tsx
<CategoryDefaults
  categoryId={category.id}
  initial={category.defaults_json ? JSON.parse(category.defaults_json) : null}
/>
```

- [ ] **Step 4: 타입 체크와 빌드**

Run: `cd apps/portal && pnpm typecheck && pnpm build`
Expected: 통과

- [ ] **Step 5: 손으로 확인한다**

Run: `pnpm dev`

카테고리 상세 페이지에서 목소리를 `movie-narrator`, 이미지 모델을 `sd15`로 저장한 뒤 새로고침해 값이 유지되는지 본다.

- [ ] **Step 6: 커밋**

```bash
git add "apps/portal/src/app/(authed)/content/c/[id]"
git commit -m "feat(portal): 카테고리 생성 기본값 편집 UI"
```

---

## Task 13: 포털 — 작업 생성 폼 프리필

**Files:**
- Modify: `apps/portal/src/app/(authed)/content/new/NewJobForm.tsx:21,72,78`

**Interfaces:**
- Consumes: `categories[].defaults_json`
- Produces: 없음

- [ ] **Step 1: 폼의 상태 변수를 확인한다**

Run: `cd apps/portal && grep -n "useState" "src/app/(authed)/content/new/NewJobForm.tsx"`

`ytLength`·`ytVoice`·`ytStyle`·`shLength`·`shVoice`·`shStyle`의 초기값과 setter 이름을 적어둔다.

- [ ] **Step 2: 카테고리 변경 시 프리필한다**

`categoryId` 상태 아래에 효과를 더한다.

```tsx
  useEffect(() => {
    const cat = categories.find((c) => c.id === categoryId);
    if (!cat?.defaults_json) return;
    let d: Record<string, string>;
    try {
      d = JSON.parse(cat.defaults_json);
    } catch {
      return;
    }
    if (d.length) { setYtLength(d.length); setShLength(d.length); }
    if (d.voice) { setYtVoice(d.voice); setShVoice(d.voice); }
    if (d.image_style) { setYtStyle(d.image_style); setShStyle(d.image_style); }
    setImageModel(d.image_model ?? "");
  }, [categoryId, categories]);
```

Step 1에서 확인한 실제 setter 이름으로 맞춘다. `useEffect`를 `react` 임포트에 추가한다.

- [ ] **Step 3: 이미지 모델을 옵션에 싣는다**

`imageModel` 상태를 더한다.

```tsx
  const [imageModel, setImageModel] = useState("");
```

72행과 78행의 옵션 조립에 넣는다. 빈 문자열이면 보내지 않아야 서버 기본값이 산다.

```tsx
      if (youtube) platforms.push({ platform: "youtube", options: {
        length: ytLength, voice: ytVoice, image_style: ytStyle,
        ...(imageModel ? { image_model: imageModel } : {}),
      } });
```

78행의 shorts 분기에도 같은 스프레드를 더한다.

- [ ] **Step 4: 타입 체크와 빌드**

Run: `cd apps/portal && pnpm typecheck && pnpm build`
Expected: 통과

- [ ] **Step 5: 손으로 확인한다**

Run: `pnpm dev`

작업 생성 화면에서 카테고리를 영화후기로 바꾸면 목소리·이미지 모델 select가 카테고리 기본값으로 바뀌는지, 다른 카테고리로 바꾸면 그쪽 값으로 바뀌는지 본다. 손으로 고른 값이 유지되는지도 확인한다.

- [ ] **Step 6: 커밋**

```bash
git add "apps/portal/src/app/(authed)/content/new/NewJobForm.tsx"
git commit -m "feat(portal): 카테고리 선택 시 작업 옵션 프리필"
```

---

## Task 14: 통합 검증

코드 변경 없이 실제로 도는지 확인한다.

**Files:** 없음

- [ ] **Step 1: 전체 테스트**

```bash
cd services/content && pytest -q
cd ../imagegen && pytest -q
cd ../.. && pnpm test && pnpm lint && pnpm typecheck
```
Expected: 전부 통과

- [ ] **Step 2: 원격 D1에 마이그레이션을 적용한다**

Run: `cd infra/wrangler && npx wrangler d1 migrations apply <DB_NAME> --remote`

- [ ] **Step 3: 영화후기 카테고리를 만든다**

포털에서 카테고리를 만들고, `CategoryYoutube`로 새 유튜브 채널을 연결하고, 생성 기본값에 `movie-narrator` + 이미지 모델을 지정한다.

- [ ] **Step 4: 짧은 영상을 한 편 생성한다**

길이 3분으로 작업을 만들어 워커가 끝까지 도는지 본다. 확인할 것 세 가지다.

1. `content_jobs.params_json`에 카테고리 기본값이 스냅샷돼 있는가
2. imagegen 로그에 모델 교체가 한 번만 찍히는가 — 교체에 걸린 실측 시간을 적어둔다 (설계 문서 "미해결 질문 4")
3. 완성 영상의 내레이션이 Fish 보이스인가

- [ ] **Step 5: 결과를 설계 문서에 반영한다**

`docs/superpowers/specs/2026-08-02-content-category-model-settings-design.md`의 "미해결 질문" 3·4번에 실측값과 청취 판단을 적는다.

```bash
git add docs/superpowers/specs/2026-08-02-content-category-model-settings-design.md
git commit -m "docs(spec): 모델 교체 실측 시간과 Fish 청취 결과 반영"
```

---

## 착수 전 확인 (비협상)

설계 문서 "위험과 미해결 질문 1"이다. **Task 4 착수 전에 결론이 나야 한다.**

Fish Audio 무료 등급(`s2.1-pro-free`)은 라이선스가 제한적이고 상업적 라이선스는 유료 플랜에만 포함된다. 영화후기는 유튜브에 공개 발행하는 콘텐츠다. 이 사용이 무료 등급 범위에 드는지 이용약관에서 확인하거나 Fish Audio에 직접 문의한다.

범위 밖으로 판명되면 `fish.py`의 `MODEL` 상수를 `s2.1-pro`로 바꾸고 유료 키를 쓴다. 코드 구조는 그대로다.

무료 기간은 2026-08-31 종료다. 그 전에 유료 전환 여부를 정한다 — 전환하지 않으면 `options.py`의 `VOICE["movie-narrator"]`를 Google 스펙으로 바꾸는 것으로 되돌린다.
