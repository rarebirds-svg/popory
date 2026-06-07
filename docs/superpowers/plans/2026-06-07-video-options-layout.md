# 영상 자막 레이아웃 + 생성 옵션 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** YouTube 영상을 자막형(제목 좌상단 고정 + 하단 문장 교체)으로 바꾸고, 생성 시 길이·목소리·배경 스타일을 선택할 수 있게 한다.

**Architecture:** 옵션은 기존 `content_jobs.params_json` 에 저장(스키마 컬럼 불변). 워커가 파싱해 대본 장면 수·이미지 스타일·TTS 보이스에 반영. `video.py` 가 장면을 문장 단위로 쪼개 문장별 클립(같은 배경·제목, 자막 교체)을 만든다.

**Tech Stack:** Python(Pillow, pytest, responses), TypeScript(zod, Hono, Next.js), Google TTS, flux.

**전제:** 영상 품질 개선(Google TTS·스크림·캡션)이 적용된 상태. 길이는 3·5·7·10분만(검토 결과). 스펙 `docs/superpowers/specs/2026-06-07-video-options-layout-design.md`.

---

## File Structure

| 파일 | 변경 | 책임 |
|------|------|------|
| `packages/types/src/content_job.ts` | 수정 | options 스키마 |
| `packages/types/src/content_job.test.ts` | 수정 | options 단언 |
| `workers/api/src/routes/content_jobs.ts` | 수정 | options→params_json |
| `workers/api/src/routes/content_jobs.test.ts` | 수정 | params_json 저장 테스트 |
| `services/content/popory_content/options.py` | 신규 | params 파싱·매핑 |
| `services/content/tests/test_options.py` | 신규 | 파싱 테스트 |
| `services/content/popory_content/video_prompt.py` | 수정 | scene_count·스타일 파라미터 |
| `services/content/popory_content/tts.py` | 수정 | voice 파라미터 |
| `services/content/popory_content/video.py` | 수정 | 문장 분할·제목/자막 렌더·voice |
| `services/content/tests/test_video*.py`, `test_tts.py` | 수정 | 테스트 갱신 |
| `services/content/popory_content/worker.py` | 수정 | 옵션→make_video |
| `services/content/tests/test_worker.py` | 수정 | 옵션 전달 단언 |
| `apps/portal/src/app/(authed)/content/new/NewJobForm.tsx` | 수정 | youtube 옵션 UI |

---

## Task 1: types — options 스키마

**Files:**
- Modify: `packages/types/src/content_job.ts`
- Modify: `packages/types/src/content_job.test.ts`

- [ ] **Step 1: 테스트 추가**

`packages/types/src/content_job.test.ts` 의 `ContentJobCreateSchema` describe 에 추가:
```ts
  it("options(길이·목소리·스타일) 허용", () => {
    const v = ContentJobCreateSchema.parse({ topic: "t", platform: "youtube", options: { length: "7", voice: "male", image_style: "illust" } });
    expect(v.options?.length).toBe("7");
  });
  it("잘못된 length 거부", () => {
    expect(ContentJobCreateSchema.safeParse({ topic: "t", options: { length: "99" } }).success).toBe(false);
  });
```

- [ ] **Step 2: 실패 확인**

Run: `pnpm --filter @popory/types test -- --run content_job`
Expected: FAIL.

- [ ] **Step 3: 스키마 수정**

`packages/types/src/content_job.ts` 의 `ContentJobCreateSchema` 에 `sources` 아래 필드 추가(객체 닫기 전):
```ts
  options: z.object({
    length: z.enum(["3", "5", "7", "10"]).optional(),
    voice: z.enum(["female-calm", "female-bright", "male"]).optional(),
    image_style: z.enum(["photo", "illust", "watercolor", "minimal"]).optional(),
  }).optional(),
```

- [ ] **Step 4: 통과 확인**

Run: `pnpm --filter @popory/types test -- --run content_job`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add packages/types/src/content_job.ts packages/types/src/content_job.test.ts
git commit -m "feat(types): content 작업 options(길이·목소리·스타일) 스키마"
```

---

## Task 2: 작업 생성 라우트 — options→params_json

**Files:**
- Modify: `workers/api/src/routes/content_jobs.ts`
- Modify: `workers/api/src/routes/content_jobs.test.ts`

- [ ] **Step 1: 테스트 추가**

`content_jobs.test.ts` 의 `describe("POST /api/content/jobs"` 안에 추가:
```ts
  it("options 를 params_json 에 저장", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", platform: "youtube", options: { length: "10", voice: "male", image_style: "watercolor" } }),
    });
    const { id } = await res.json<{ id: string }>();
    const row = await env.DB.prepare("SELECT params_json FROM content_jobs WHERE id=?").bind(id).first<{ params_json: string }>();
    expect(JSON.parse(row!.params_json)).toEqual({ length: "10", voice: "male", image_style: "watercolor" });
  });
```

- [ ] **Step 2: 실패 확인**

Run: `pnpm --filter @popory/api test -- --run content_jobs`
Expected: FAIL(params_json null).

- [ ] **Step 3: 라우트 수정**

`workers/api/src/routes/content_jobs.ts` 의 `POST /api/content/jobs` INSERT 에서 params_json 을 저장하도록. 현재 INSERT:
```ts
    await c.env.DB.prepare(
      `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, created_at, updated_at)
       VALUES (?, ?, ?, ?, 'queued', ?, NULL, ?, ?)`,
    ).bind(id, u.sub, parsed.data.topic, parsed.data.platform, parsed.data.style_profile_id ?? null, now, now).run();
```
변경 — params 자리 NULL → 바인딩:
```ts
    const paramsJson = parsed.data.options ? JSON.stringify(parsed.data.options) : null;
    await c.env.DB.prepare(
      `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, created_at, updated_at)
       VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)`,
    ).bind(id, u.sub, parsed.data.topic, parsed.data.platform, parsed.data.style_profile_id ?? null, paramsJson, now, now).run();
```

- [ ] **Step 4: 통과 + 타입체크**

Run: `pnpm --filter @popory/api test -- --run content_jobs 2>&1 | tail -3` → PASS.
Run: `pnpm --filter @popory/api typecheck 2>&1 | tail -2` → clean.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add workers/api/src/routes/content_jobs.ts workers/api/src/routes/content_jobs.test.ts
git commit -m "feat(content): 작업 options 를 params_json 에 저장"
```

---

## Task 3: options.py — 파싱·매핑

**Files:**
- Create: `services/content/popory_content/options.py`
- Create: `services/content/tests/test_options.py`

- [ ] **Step 1: 실패 테스트**

`services/content/tests/test_options.py`:
```python
# 작업 옵션 파싱·매핑 검증.
from popory_content.options import parse_options, SCENE_COUNT, VOICE, STYLE


def test_defaults_when_none():
    o = parse_options(None)
    assert o == {"length": "5", "voice": "female-calm", "image_style": "photo"}


def test_valid_merge():
    o = parse_options('{"length":"10","voice":"male","image_style":"watercolor"}')
    assert o["length"] == "10" and o["voice"] == "male" and o["image_style"] == "watercolor"


def test_invalid_falls_back():
    o = parse_options('{"length":"99","voice":"bad"}')
    assert o["length"] == "5" and o["voice"] == "female-calm"


def test_bad_json():
    assert parse_options("not json")["length"] == "5"


def test_maps_cover_keys():
    assert set(SCENE_COUNT) == {"3", "5", "7", "10"}
    assert VOICE["male"].startswith("ko-KR")
    assert "watercolor" in STYLE["watercolor"]
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_options.py -q`
Expected: FAIL(모듈 없음).

- [ ] **Step 3: 구현**

`services/content/popory_content/options.py`:
```python
# youtube 작업의 params_json(길이·목소리·배경스타일) 파싱·매핑.
import json

SCENE_COUNT = {"3": 5, "5": 8, "7": 12, "10": 16}
VOICE = {"female-calm": "ko-KR-Neural2-A", "female-bright": "ko-KR-Neural2-B", "male": "ko-KR-Neural2-C"}
STYLE = {
    "photo": "photorealistic, cinematic",
    "illust": "digital illustration, clean",
    "watercolor": "watercolor painting",
    "minimal": "minimalist flat design",
}
DEFAULTS = {"length": "5", "voice": "female-calm", "image_style": "photo"}


def parse_options(params_json: str | None) -> dict:
    opts = dict(DEFAULTS)
    if not params_json:
        return opts
    try:
        data = json.loads(params_json)
    except (json.JSONDecodeError, TypeError):
        return opts
    if isinstance(data, dict):
        if data.get("length") in SCENE_COUNT:
            opts["length"] = data["length"]
        if data.get("voice") in VOICE:
            opts["voice"] = data["voice"]
        if data.get("image_style") in STYLE:
            opts["image_style"] = data["image_style"]
    return opts
```

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_options.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/options.py services/content/tests/test_options.py
git commit -m "feat(content-worker): 작업 옵션 파싱·매핑"
```

---

## Task 4: video_prompt.py — scene_count·스타일 파라미터

**Files:**
- Modify: `services/content/popory_content/video_prompt.py`
- Modify: `services/content/tests/test_video_prompt.py`

- [ ] **Step 1: 테스트 갱신**

`services/content/tests/test_video_prompt.py` 의 `test_system_prompt_has_contract` 를 파라미터 반영하도록 교체:
```python
def test_system_prompt_has_contract():
    sp = build_video_system_prompt([], scene_count=12, image_style_kw="watercolor painting")
    assert "scenes_json" in sp
    assert "video_meta" in sp
    assert "narration" in sp
    assert "caption" in sp
    assert "image_prompt" in sp
    assert "12" in sp                  # 장면 수 반영
    assert "watercolor" in sp          # 스타일 키워드 반영
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video_prompt.py -q`
Expected: FAIL(시그니처/문구).

- [ ] **Step 3: video_prompt.py 수정**

`services/content/popory_content/video_prompt.py` 전체를 아래로 교체(규칙을 함수로 빌드):
```python
# claude CLI 에 줄 YouTube 영상 대본 system/user 프롬프트. 장면 배열 + 메타를 출력시킨다.
from typing import Any


def _rules(scene_count: int, image_style_kw: str) -> str:
    return f"""당신은 한국어 YouTube 영상 대본 작가입니다. 주제로 슬라이드쇼형 영상의 대본을 만듭니다.

## 1. 리서치
- WebSearch·WebFetch 로 주제 관련 신뢰할 자료를 수집합니다.
- 사용자가 제공한 참고 링크가 있으면 반영합니다.
- 확인된 사실만 씁니다.

## 2. 구성
- 영상은 장면(scene) 약 {scene_count}개로 구성합니다.
- 각 장면은 caption(화면에 크게 띄울 짧은 헤드라인, 16자 이내 핵심 단어 위주)과 narration(그 장면에서 읽어줄 내레이션, 2~4문장)으로 이뤄집니다.
- 각 장면에 image_prompt(그 장면을 묘사하는 영어 이미지 생성 프롬프트, 한 문장. {image_style_kw} 스타일이며 이미지 안에 글자/텍스트는 넣지 않습니다)도 포함합니다.
- 도입(후킹) → 본문 → 마무리(구독 유도) 흐름.
- 자연스러운 한국어 구어체. 문장은 마침표로 끝냅니다.

## 3. 출력 (반드시 마지막 응답에 두 태그를 정확히 포함)
- 태그 안에는 코드 블록 표시(```)를 쓰지 말고 내용만 넣습니다.
<scenes_json>
[{{"caption": "...", "narration": "...", "image_prompt": "english description"}}, ...]
</scenes_json>
<video_meta>
{{"title": "...", "description": "...", "tags": ["..."]}}
</video_meta>
"""


_STYLE_HEADER = "\n## 4. 말투 스타일 (아래 샘플의 어조를 따르세요)\n"


def build_video_system_prompt(style_samples: list[str], scene_count: int = 8,
                              image_style_kw: str = "photorealistic, cinematic") -> str:
    sp = _rules(scene_count, image_style_kw)
    if style_samples:
        sp += _STYLE_HEADER
        for i, s in enumerate(style_samples, 1):
            sp += f"\n--- 샘플 {i} ---\n{s.strip()}\n"
    return sp


def build_video_user_message(topic: str, sources: list[dict[str, Any]]) -> str:
    lines = [f"주제: {topic}", "", "시스템 규칙에 따라 YouTube 영상 대본을 장면 배열로 작성하세요."]
    refs = [s for s in sources if s.get("url")]
    if refs:
        lines.append("")
        lines.append("참고 링크:")
        for s in refs:
            note = f" — {s['note']}" if s.get("note") else ""
            lines.append(f"- {s['url']}{note}")
    lines.append("")
    lines.append("마지막 응답에 <scenes_json>...</scenes_json> 과 <video_meta>...</video_meta> 두 태그를 정확히 포함하세요.")
    return "\n".join(lines)
```

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video_prompt.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/video_prompt.py services/content/tests/test_video_prompt.py
git commit -m "feat(content-worker): 대본 프롬프트 장면수·스타일 파라미터화"
```

---

## Task 5: tts.py — voice 파라미터

**Files:**
- Modify: `services/content/popory_content/tts.py`
- Modify: `services/content/tests/test_tts.py`

- [ ] **Step 1: 테스트 추가**

`services/content/tests/test_tts.py` 에 추가:
```python
@responses.activate
def test_synthesize_uses_voice(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    import base64 as _b
    responses.add(responses.POST, tts.TTS_URL, json={"audioContent": _b.b64encode(b"x").decode()}, status=200)
    tts.synthesize("안녕", voice="ko-KR-Neural2-C")
    body = responses.calls[0].request.body
    assert "ko-KR-Neural2-C" in (body if isinstance(body, str) else body.decode())
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_tts.py -q`
Expected: FAIL(voice 인자 없음).

- [ ] **Step 3: tts.py 수정**

`services/content/popory_content/tts.py` 의 `synthesize` 시그니처·바디를 변경:
```python
def synthesize(text: str, voice: str = "ko-KR-Neural2-A") -> bytes | None:
    key = os.environ.get("GOOGLE_TTS_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            f"{TTS_URL}?key={key}",
            json={
                "input": {"text": text},
                "voice": {"languageCode": LANGUAGE, "name": voice},
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
(기존 `VOICE_NAME` 상수는 더 이상 안 쓰면 제거. `LANGUAGE` 유지.)

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_tts.py -q`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/tts.py services/content/tests/test_tts.py
git commit -m "feat(content-worker): TTS voice 파라미터"
```

---

## Task 6: video.py — 문장 분할·제목/자막·voice

**Files:**
- Modify: `services/content/popory_content/video.py`
- Modify: `services/content/tests/test_video.py`

- [ ] **Step 1: 테스트 갱신**

`services/content/tests/test_video.py` 의 `test_render_card_with_and_without_bg` 를 (title, subtitle) 시그니처로 교체하고 `_split_sentences` 테스트 추가:
```python
def test_render_card_with_and_without_bg(tmp_path):
    buf = io.BytesIO()
    _Image.new("RGB", (320, 180), (200, 100, 50)).save(buf, format="PNG")
    bg = buf.getvalue()
    p1 = tmp_path / "with_bg.png"
    p2 = tmp_path / "no_bg.png"
    _render_card("챕터 제목", "지금 읽는 문장입니다.", p1, bg_image_bytes=bg)
    _render_card("챕터 제목", "지금 읽는 문장입니다.", p2, bg_image_bytes=None)
    assert p1.exists() and p1.stat().st_size > 1000
    assert p2.exists() and p2.stat().st_size > 1000


def test_split_sentences():
    from popory_content.video import _split_sentences
    out = _split_sentences("첫째 문장입니다. 둘째 문장이에요! 셋째는요?")
    assert out == ["첫째 문장입니다.", "둘째 문장이에요!", "셋째는요?"]
```
import 줄(`from popory_content.video import render_video, _render_card, FONT_PATH`)에 `_render_card` 가 이미 있으면 그대로.

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video.py -q`
Expected: FAIL.

- [ ] **Step 3: video.py 수정**

import 에 `re` 추가(상단). `synthesize` import 는 이미 있음.

`_render_card` 를 (title, subtitle) 형태로 교체:
```python
def _render_card(title: str, subtitle: str, out_png: Path, bg_image_bytes: bytes | None = None) -> None:
    if bg_image_bytes:
        bg = Image.open(BytesIO(bg_image_bytes)).convert("RGB")
        img = _cover(bg, WIDTH, HEIGHT)
        _scrim_bottom(img)
    else:
        img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)
    title_font = ImageFont.truetype(FONT_PATH, 56)
    sub_font = ImageFont.truetype(FONT_PATH, 64)
    t = "\n".join(textwrap.wrap(title, width=22)) or " "
    d.multiline_text((80, 70), t, font=title_font, fill=HEAD_COLOR, anchor="la", align="left", spacing=10)
    s = "\n".join(textwrap.wrap(subtitle, width=30)) or " "
    d.multiline_text((WIDTH / 2, HEIGHT - 240), s, font=sub_font, fill=(255, 255, 255), anchor="ma", align="center", spacing=14)
    img.save(out_png)


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.?!])\s*", text.strip())
    return [p.strip() for p in parts if p.strip()]
```

`render_video` 를 문장 분할·voice 형태로 교체:
```python
def render_video(scenes: list[dict[str, Any]], job_id: str = "adhoc",
                 image_fetcher: Any = None, voice: str = "ko-KR-Neural2-A") -> Path:
    """장면→문장별 클립(같은 배경·제목, 하단 자막 교체)→concat MP4."""
    if not Path(FONT_PATH).exists():
        raise VideoError(f"한국어 폰트 없음: {FONT_PATH}")
    work = TMP / f"video_{job_id}"
    work.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for i, scene in enumerate(scenes):
        caption = str(scene["caption"]).strip()
        bg_bytes = None
        prompt = scene.get("image_prompt")
        if image_fetcher and prompt:
            try:
                bg_bytes = image_fetcher(prompt)
            except Exception:  # noqa: BLE001 — 이미지 실패는 단색 폴백
                bg_bytes = None
        sentences = _split_sentences(str(scene["narration"])) or [str(scene["narration"]).strip() or " "]
        for j, sent in enumerate(sentences):
            audio_bytes = synthesize(sent, voice=voice)
            if audio_bytes:
                audio = work / f"{i}_{j}.mp3"
                audio.write_bytes(audio_bytes)
            else:
                audio = work / f"{i}_{j}.aiff"
                _run([SAY_BIN, "-v", SAY_VOICE, "-o", str(audio), sent])
            dur = _duration(audio)
            png = work / f"{i}_{j}.png"
            _render_card(caption, sent, png, bg_image_bytes=bg_bytes)
            clip = work / f"{i}_{j}.mp4"
            _run([
                FFMPEG_BIN, "-y", "-loop", "1", "-i", str(png), "-i", str(audio),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-t", f"{dur:.3f}",
                "-c:a", "aac", "-shortest", str(clip),
            ])
            clips.append(clip)

    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{p}'\n" for p in clips), encoding="utf-8")
    out = work / "out.mp4"
    _run([FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(out)])
    return out
```

`generate_scenes` 와 `make_video` 시그니처에 파라미터 추가:
```python
def generate_scenes(*, topic: str, sources: list[dict[str, Any]], style_samples: list[str],
                    job_id: str = "adhoc", scene_count: int = 8,
                    image_style_kw: str = "photorealistic, cinematic") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sp = build_video_system_prompt(style_samples, scene_count=scene_count, image_style_kw=image_style_kw)
    um = build_video_user_message(topic, sources)
    return run_claude_cli(system_prompt=sp, user_msg=um, parse=parse_video, job_id=job_id)


def make_video(*, topic: str, sources: list[dict[str, Any]], style_samples: list[str],
               job_id: str = "adhoc", image_fetcher: Any = None, scene_count: int = 8,
               image_style_kw: str = "photorealistic, cinematic",
               voice: str = "ko-KR-Neural2-A") -> tuple[Path, list[dict[str, Any]], dict[str, Any]]:
    scenes, meta = generate_scenes(topic=topic, sources=sources, style_samples=style_samples,
                                   job_id=job_id, scene_count=scene_count, image_style_kw=image_style_kw)
    mp4 = render_video(scenes, job_id=job_id, image_fetcher=image_fetcher, voice=voice)
    return mp4, scenes, meta
```

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video.py -q`
Expected: PASS(렌더 스모크는 say 폴백·문장 분할로 동작).

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/video.py services/content/tests/test_video.py
git commit -m "feat(content-worker): 문장별 자막 클립(제목 좌상단·하단 교체) + voice"
```

---

## Task 7: worker.py — 옵션 배선

**Files:**
- Modify: `services/content/popory_content/worker.py`
- Modify: `services/content/tests/test_worker.py`

- [ ] **Step 1: 테스트 갱신**

`services/content/tests/test_worker.py` 의 `test_youtube_branch_uploads_video_and_reviews` 의 job 에 params_json 추가하고 captured 단언 추가:
```python
    client = VidClient({"job": {"id": "yt1", "topic": "t", "platform": "youtube", "params_json": '{"length":"7","voice":"male","image_style":"illust"}'}, "sources": [], "style_samples": []})
```
그리고 `assert callable(captured.get("image_fetcher"))` 아래에 추가:
```python
    assert captured.get("scene_count") == 12      # length "7" → 12 장면
    assert captured.get("voice") == "ko-KR-Neural2-C"
    assert "illustration" in captured.get("image_style_kw")
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_worker.py -q`
Expected: FAIL.

- [ ] **Step 3: worker.py 수정**

import 추가:
```python
from popory_content.options import parse_options, SCENE_COUNT, VOICE, STYLE
```

youtube 분기의 make_video 호출 교체:
```python
        if platform == "youtube":
            opts = parse_options(job.get("params_json"))
            mp4, scenes, meta = make_video(
                topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id,
                image_fetcher=lambda p: _safe_image(client, p),
                scene_count=SCENE_COUNT[opts["length"]],
                image_style_kw=STYLE[opts["image_style"]],
                voice=VOICE[opts["voice"]],
            )
```

- [ ] **Step 4: 통과 + 전체 회귀**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_worker.py -q` → PASS.
Run: `pytest -q` → 전체 PASS(영상 스모크 포함, 수십 초).

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/worker.py services/content/tests/test_worker.py
git commit -m "feat(content-worker): 옵션(길이·목소리·스타일)을 영상 생성에 배선"
```

---

## Task 8: 포털 — youtube 옵션 UI

**Files:**
- Modify: `apps/portal/src/app/(authed)/content/new/NewJobForm.tsx`

- [ ] **Step 1: 상태·바디·UI 추가**

`NewJobForm.tsx` 의 platform state 아래에 옵션 state 추가:
```tsx
  const [length, setLength] = useState<"3" | "5" | "7" | "10">("5");
  const [voice, setVoice] = useState<"female-calm" | "female-bright" | "male">("female-calm");
  const [imageStyle, setImageStyle] = useState<"photo" | "illust" | "watercolor" | "minimal">("photo");
```

POST 바디(`body: JSON.stringify({`)에 options 추가:
```tsx
        body: JSON.stringify({
          topic,
          platform,
          options: platform === "youtube" ? { length, voice, image_style: imageStyle } : undefined,
          style_profile_id: styleId || undefined,
          sources: cleanSources.length ? cleanSources : undefined,
        }),
```

콘텐츠 종류 select `<label>` 바로 뒤에 youtube 옵션 블록 추가:
```tsx
      {platform === "youtube" && (
        <div className="grid grid-cols-3 gap-3">
          <label className="block">
            <span className="block text-xs font-semibold text-popory-muted mb-1">길이</span>
            <select value={length} onChange={(e) => setLength(e.target.value as typeof length)} className={INPUT}>
              <option value="3">3분</option>
              <option value="5">5분</option>
              <option value="7">7분</option>
              <option value="10">10분</option>
            </select>
          </label>
          <label className="block">
            <span className="block text-xs font-semibold text-popory-muted mb-1">목소리</span>
            <select value={voice} onChange={(e) => setVoice(e.target.value as typeof voice)} className={INPUT}>
              <option value="female-calm">여성·차분</option>
              <option value="female-bright">여성·밝은</option>
              <option value="male">남성</option>
            </select>
          </label>
          <label className="block">
            <span className="block text-xs font-semibold text-popory-muted mb-1">배경 스타일</span>
            <select value={imageStyle} onChange={(e) => setImageStyle(e.target.value as typeof imageStyle)} className={INPUT}>
              <option value="photo">실사</option>
              <option value="illust">일러스트</option>
              <option value="watercolor">수채화</option>
              <option value="minimal">미니멀</option>
            </select>
          </label>
        </div>
      )}
```

- [ ] **Step 2: 타입체크 + 빌드**

Run: `pnpm --filter @popory/portal typecheck 2>&1 | tail -3` → clean.
Run: `NEXT_PUBLIC_API_BASE=https://api.poporyfamily.com pnpm --filter @popory/portal build:cf 2>&1 | grep -E "Build completed|error"` → 성공.

- [ ] **Step 3: Commit**

```bash
cd /Users/daegong/projects/popory
git add "apps/portal/src/app/(authed)/content/new/NewJobForm.tsx"
git commit -m "feat(portal): YouTube 생성 옵션(길이·목소리·배경 스타일) UI"
```

---

## Task 9: 검증 + 배포

**Files:** 없음

- [ ] **Step 1: 전체 회귀**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest -q` → PASS.
Run: `cd /Users/daegong/projects/popory && pnpm --filter @popory/api test -- --run 2>&1 | grep Tests` → PASS.
Run: `pnpm -r typecheck 2>&1 | grep -E "Done|error"` → 6 Done.

- [ ] **Step 2: prod 배포**

```bash
cd /Users/daegong/projects/popory/workers/api
pnpm exec wrangler deploy --env prod --config ../../infra/wrangler/api.toml
NEXT_PUBLIC_API_BASE=https://api.poporyfamily.com pnpm --filter @popory/portal build:cf
pnpm exec wrangler pages deploy /Users/daegong/projects/popory/apps/portal/.vercel/output/static --project-name popory-portal --branch main
```

- [ ] **Step 3: 워커 재시작**

```bash
launchctl kickstart -k "gui/$(id -u)/com.popory.content-worker"
```

- [ ] **Step 4: e2e (휴먼)**

새 YouTube 작업 → 길이·목소리·배경 스타일 선택 → 생성 → 좌상단 제목·하단 문장 교체 자막·선택한 보이스·스타일 확인.

---

## Self-Review (작성자 체크)

**Spec coverage:**
- §5.1 options 스키마 → Task 1. ✅
- §5.2 params_json 저장 → Task 2. ✅
- §5.3 options.py 파싱·매핑 → Task 3. ✅
- §5.4 video_prompt scene_count·스타일 → Task 4. ✅
- §5.5 tts voice → Task 5. ✅
- §5.6 문장 분할·제목/자막·render_video voice → Task 6. ✅
- §5.7 worker 옵션 배선 → Task 7. ✅
- §5.8 포털 옵션 UI → Task 8. ✅
- §7 폴백·기본값 → Task 3(기본값)·6(say/단색 폴백). ✅
- §8 테스트 → 각 Task. ✅

**Placeholder scan:** 모든 단계 실제 코드. ✅

**Type consistency:** `parse_options`·`SCENE_COUNT/VOICE/STYLE`(Task 3) → worker(Task 7) 사용 일치. `build_video_system_prompt(style_samples, scene_count, image_style_kw)`(Task 4) → generate_scenes(Task 6) 호출 일치. `synthesize(text, voice)`(Task 5) → render_video(Task 6) 일치. `_render_card(title, subtitle, out_png, bg_image_bytes)`(Task 6) → render_video 호출·테스트 일치. `make_video(..., scene_count, image_style_kw, voice)`(Task 6) → worker(Task 7) 일치. options 스키마(Task 1) ↔ params_json(Task 2) ↔ parse_options(Task 3) 키(length/voice/image_style) 일관. ✅
