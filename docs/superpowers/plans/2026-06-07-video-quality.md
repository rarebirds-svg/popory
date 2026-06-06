# 영상 품질 개선 (Google TTS·이미지·텍스트) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 영상 내레이션을 Google Cloud TTS 자연 음성으로, 배경 이미지 합성을 경량화(하단 스크림), 화면 텍스트를 짧은 캡션만으로 바꾼다.

**Architecture:** 전부 로컬 워커 파이프라인 변경. 신규 `tts.py`(Google TTS, say 폴백), `video.py`(음성 소스·카드 렌더 수정), `video_prompt.py`(image_prompt 강화). API·포털·DB 불변.

**Tech Stack:** Python(requests, Pillow, pytest, responses), Google Cloud TTS REST, ffmpeg, macOS say(폴백).

**전제:** YouTube 영상 생성 + AI 이미지가 prod 가동. 스펙 `docs/superpowers/specs/2026-06-07-video-quality-design.md`.

---

## File Structure

| 파일 | 변경 | 책임 |
|------|------|------|
| `services/content/popory_content/tts.py` | 신규 | Google TTS 합성(키 없으면 None) |
| `services/content/tests/test_tts.py` | 신규 | REST 모킹 테스트 |
| `services/content/popory_content/video.py` | 수정 | TTS 소스 + 스크림·캡션 렌더 |
| `services/content/tests/test_video.py` | 수정 | 캡션-only·폴백 테스트 |
| `services/content/popory_content/video_prompt.py` | 수정 | image_prompt 스타일 강화 |
| `services/content/tests/test_video_prompt.py` | 수정 | 스타일 단언 |

---

## Task 1: tts.py — Google Cloud TTS

**Files:**
- Create: `services/content/popory_content/tts.py`
- Create: `services/content/tests/test_tts.py`

- [ ] **Step 1: 실패 테스트**

`services/content/tests/test_tts.py`:
```python
# Google TTS 합성 — 키 유무·응답별 동작 검증(REST 모킹).
import base64
import responses
from popory_content import tts


@responses.activate
def test_synthesize_returns_bytes(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    audio = base64.b64encode(b"\xff\xfbMP3").decode()
    responses.add(responses.POST, tts.TTS_URL, json={"audioContent": audio}, status=200)
    out = tts.synthesize("안녕하세요")
    assert out == b"\xff\xfbMP3"


def test_synthesize_none_without_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_TTS_API_KEY", raising=False)
    assert tts.synthesize("안녕") is None


@responses.activate
def test_synthesize_none_on_error(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    responses.add(responses.POST, tts.TTS_URL, json={"error": "x"}, status=500)
    assert tts.synthesize("안녕") is None
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_tts.py -q`
Expected: FAIL(모듈 없음).

- [ ] **Step 3: 구현**

`services/content/popory_content/tts.py`:
```python
# Google Cloud Text-to-Speech 로 한국어 자연 음성 합성. 키 없거나 실패하면 None(호출측 say 폴백).
import base64
import os

import requests

TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
LANGUAGE = "ko-KR"
VOICE_NAME = "ko-KR-Neural2-C"


def synthesize(text: str) -> bytes | None:
    key = os.environ.get("GOOGLE_TTS_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            f"{TTS_URL}?key={key}",
            json={
                "input": {"text": text},
                "voice": {"languageCode": LANGUAGE, "name": VOICE_NAME},
                "audioConfig": {"audioEncoding": "MP3"},
            },
            timeout=30,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    audio = resp.json().get("audioContent")
    if not audio:
        return None
    return base64.b64decode(audio)
```

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_tts.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/tts.py services/content/tests/test_tts.py
git commit -m "feat(content-worker): Google Cloud TTS 합성(say 폴백)"
```

---

## Task 2: video.py — TTS 소스 + 스크림·캡션 렌더

**Files:**
- Modify: `services/content/popory_content/video.py`
- Modify: `services/content/tests/test_video.py`

- [ ] **Step 1: 테스트 갱신 (실패 유도)**

`services/content/tests/test_video.py` 의 `test_render_card_with_and_without_bg` 를 캡션-only 시그니처로 교체:
```python
def test_render_card_with_and_without_bg(tmp_path):
    buf = io.BytesIO()
    _Image.new("RGB", (320, 180), (200, 100, 50)).save(buf, format="PNG")
    bg = buf.getvalue()
    p1 = tmp_path / "with_bg.png"
    p2 = tmp_path / "no_bg.png"
    _render_card("짧은 캡션", p1, bg_image_bytes=bg)
    _render_card("짧은 캡션", p2, bg_image_bytes=None)
    assert p1.exists() and p1.stat().st_size > 1000
    assert p2.exists() and p2.stat().st_size > 1000
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video.py::test_render_card_with_and_without_bg -q`
Expected: FAIL(`_render_card` 가 아직 narration 인자 받음).

- [ ] **Step 3: video.py 수정**

import 추가(상단 import 블록):
```python
from popory_content.tts import synthesize
```

`_render_card` 를 아래로 교체(narration 인자 제거, 스크림+캡션만):
```python
def _scrim_bottom(img: Image.Image) -> None:
    """하단 그라데이션 스크림(아래로 갈수록 어두움)으로 캡션 가독성 확보."""
    grad_h = int(HEIGHT * 0.4)
    grad = Image.new("L", (1, grad_h))
    for y in range(grad_h):
        grad.putpixel((0, y), int(190 * y / grad_h))
    grad = grad.resize((WIDTH, grad_h))
    black = Image.new("RGB", (WIDTH, grad_h), (0, 0, 0))
    img.paste(black, (0, HEIGHT - grad_h), grad)


def _render_card(caption: str, out_png: Path, bg_image_bytes: bytes | None = None) -> None:
    if bg_image_bytes:
        bg = Image.open(BytesIO(bg_image_bytes)).convert("RGB")
        img = _cover(bg, WIDTH, HEIGHT)
        _scrim_bottom(img)
    else:
        img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)
    head = ImageFont.truetype(FONT_PATH, 76)
    cap = "\n".join(textwrap.wrap(caption, width=20)) or " "
    d.multiline_text((90, HEIGHT - 240), cap, font=head, fill=HEAD_COLOR, anchor="la", align="left", spacing=14)
    img.save(out_png)
```

`render_video` 의 장면 루프에서 음성 생성·렌더 호출을 교체. 변경 전:
```python
        aiff = work / f"{i}.aiff"
        _run([SAY_BIN, "-v", SAY_VOICE, "-o", str(aiff), narration])
        dur = _duration(aiff)
        bg_bytes = None
        prompt = scene.get("image_prompt")
        if image_fetcher and prompt:
            try:
                bg_bytes = image_fetcher(prompt)
            except Exception:  # noqa: BLE001 — 이미지 실패는 단색 폴백
                bg_bytes = None
        png = work / f"{i}.png"
        _render_card(caption, narration, png, bg_image_bytes=bg_bytes)
        clip = work / f"{i}.mp4"
        _run([
            FFMPEG_BIN, "-y", "-loop", "1", "-i", str(png), "-i", str(aiff),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-t", f"{dur:.3f}",
            "-c:a", "aac", "-shortest", str(clip),
        ])
```
변경 후:
```python
        audio_bytes = synthesize(narration)
        if audio_bytes:
            audio = work / f"{i}.mp3"
            audio.write_bytes(audio_bytes)
        else:
            audio = work / f"{i}.aiff"
            _run([SAY_BIN, "-v", SAY_VOICE, "-o", str(audio), narration])
        dur = _duration(audio)
        bg_bytes = None
        prompt = scene.get("image_prompt")
        if image_fetcher and prompt:
            try:
                bg_bytes = image_fetcher(prompt)
            except Exception:  # noqa: BLE001 — 이미지 실패는 단색 폴백
                bg_bytes = None
        png = work / f"{i}.png"
        _render_card(caption, png, bg_image_bytes=bg_bytes)
        clip = work / f"{i}.mp4"
        _run([
            FFMPEG_BIN, "-y", "-loop", "1", "-i", str(png), "-i", str(audio),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-t", f"{dur:.3f}",
            "-c:a", "aac", "-shortest", str(clip),
        ])
```

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video.py -q`
Expected: PASS(캡션-only 단위테스트 + 렌더 스모크. 스모크는 키 없으면 say 폴백으로 동작).

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/video.py services/content/tests/test_video.py
git commit -m "feat(content-worker): TTS 음성 소스 교체 + 하단 스크림·캡션만 렌더"
```

---

## Task 3: video_prompt.py — image_prompt 스타일 강화

**Files:**
- Modify: `services/content/popory_content/video_prompt.py`
- Modify: `services/content/tests/test_video_prompt.py`

- [ ] **Step 1: 테스트 갱신 (실패 유도)**

`services/content/tests/test_video_prompt.py` 의 `test_system_prompt_has_contract` 에 단언 추가:
```python
    assert "cinematic" in sp
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video_prompt.py -q`
Expected: FAIL.

- [ ] **Step 3: video_prompt.py 수정**

`services/content/popory_content/video_prompt.py` 의 image_prompt 지시 줄을 교체. 변경 전:
```
- 각 장면에 image_prompt(그 장면 분위기를 묘사하는 영어 이미지 생성 프롬프트, 한 문장)도 포함합니다.
```
변경 후:
```
- 각 장면에 image_prompt(그 장면을 묘사하는 영어 이미지 생성 프롬프트, 한 문장. cinematic, photorealistic, high detail 스타일이며 이미지 안에 글자/텍스트는 넣지 않습니다)도 포함합니다.
```
그리고 caption 설명 줄의 "20자 이내" 를 "16자 이내, 핵심 단어 위주" 로:
```
- 각 장면은 caption(화면에 크게 띄울 짧은 헤드라인, 16자 이내 핵심 단어 위주)과 narration(그 장면에서 읽어줄 내레이션, 2~4문장)으로 이뤄집니다.
```

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video_prompt.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/video_prompt.py services/content/tests/test_video_prompt.py
git commit -m "feat(content-worker): image_prompt cinematic·무텍스트 강화 + 캡션 축약"
```

---

## Task 4: 검증 + 배포 + 외부 설정

**Files:** 없음

- [ ] **Step 1: 전체 워커 회귀**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest -q`
Expected: 전체 PASS(영상 스모크 포함, 수십 초).

- [ ] **Step 2: 외부 설정 (사용자, e2e 전)**

1. Google Cloud `popory-497615` → Cloud Text-to-Speech API 사용 설정.
2. API 키 발급(가능하면 TTS API 로 제한).
3. 워커 `services/content/secrets/env.sh` 에 추가: `export GOOGLE_TTS_API_KEY="..."`.

- [ ] **Step 3: 워커 재시작 (새 모듈·env 로드)**

```bash
launchctl kickstart -k "gui/$(id -u)/com.popory.content-worker"
```

- [ ] **Step 4: 로컬 TTS 스모크 (키 설정 후)**

```bash
cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && set -a && source secrets/env.sh && set +a && python -c "from popory_content.tts import synthesize; b=synthesize('안녕하세요. 테스트입니다.'); print('tts bytes:', len(b) if b else None, '| head:', b[:4] if b else None)"
```
Expected: 수천+ 바이트(MP3). None 이면 키·API 활성화 점검.

- [ ] **Step 5: e2e (휴먼)**

새 YouTube 작업 → 자연 음성 내레이션 + 선명한 배경 이미지 + 짧은 캡션만 있는 영상 확인.

---

## Self-Review (작성자 체크)

**Spec coverage:**
- §5.1 tts.py(Google TTS, 키없음 None) → Task 1. ✅
- §5.2 render_video TTS 소스 교체 + say 폴백 + MP3/aiff → Task 2. ✅
- §5.2 _render_card 스크림·캡션만(자막 제거) → Task 2. ✅
- §5.3 image_prompt 강화 + 캡션 축약 → Task 3. ✅
- §7 폴백(TTS 실패→say, 이미지 실패→단색) → Task 2. ✅
- §8 테스트(tts·video·prompt) → Task 1·2·3. ✅
- §9 외부 설정(Cloud TTS·키) → Task 4 Step 2. ✅

**Placeholder scan:** 모든 단계 실제 코드. 스크림 그라데이션 구현 구체. 보이스명 `ko-KR-Neural2-C` 고정(튜닝은 후속). ✅

**Type consistency:** `synthesize(text)->bytes|None` Task 1 정의·Task 2 사용 일치. `_render_card(caption, out_png, bg_image_bytes=None)`(narration 제거) Task 2 정의·호출·테스트 일치. `_scrim_bottom(img)` 신규. `TTS_URL`·`VOICE_NAME` 상수 Task 1·테스트 일관. ✅
