# 멀티플랫폼 Slice B — Shorts 파이프라인 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 9:16 세로형 60초 이내 shorts 영상을 생성하는 파이프라인을 추가한다. 유튜브 쇼츠·인스타 쇼츠 공용 영상 파일을 만들고, 기존 YouTube 업로드 API에서 `shorts` 플랫폼을 허용한다.

**Architecture:** 기존 `make_video` 파이프라인에 `portrait=True` 파라미터를 추가해 1080×1920 해상도로 전환한다. `options.py`에 shorts 전용 길이 매핑(15/30/60초)을 추가하고, `worker.py`에 `shorts` 분기를 추가한다. YouTube 업로드 API의 플랫폼 체크를 `shorts`도 허용하도록 완화한다.

**Tech Stack:** Python 3.11, Pillow, ffmpeg, TTS(Google Cloud), Hono

**선행 조건:** Slice A 완료(content_topics 테이블, idle 상태 존재).

---

## 파일 맵

| 경로 | 변경 |
|---|---|
| `services/content/popory_content/options.py` | 수정 — SHORT_SCENE_COUNT 추가 |
| `services/content/popory_content/video.py` | 수정 — portrait 파라미터, 상수 분리 |
| `services/content/popory_content/video_prompt.py` | 수정 — shorts 전용 프롬프트 규칙 |
| `services/content/popory_content/worker.py` | 수정 — shorts 분기 추가 |
| `workers/api/src/routes/content_youtube_upload.ts` | 수정 — shorts 플랫폼 허용 |
| `services/content/tests/test_options.py` | 수정 — shorts 옵션 테스트 추가 |
| `services/content/tests/test_video.py` | 수정 — portrait 모드 테스트 추가 |
| `services/content/tests/test_worker.py` | 수정 — shorts 분기 테스트 추가 |

---

### Task 1: options.py에 Shorts 옵션 추가

**Files:**
- Modify: `services/content/popory_content/options.py`

- [ ] **Step 1: 테스트 추가**

`services/content/tests/test_options.py`에 추가:

```python
from popory_content.options import parse_shorts_options, SHORT_SCENE_COUNT

def test_parse_shorts_options_defaults():
    opts = parse_shorts_options(None)
    assert opts["length"] == "30"
    assert opts["voice"] == "female-calm"
    assert opts["image_style"] == "photo"
    assert opts["upload_targets"] == []

def test_parse_shorts_options_all_fields():
    import json
    params = json.dumps({"length": "60", "voice": "male", "image_style": "illust", "upload_targets": ["youtube", "instagram"]})
    opts = parse_shorts_options(params)
    assert opts["length"] == "60"
    assert opts["upload_targets"] == ["youtube", "instagram"]

def test_short_scene_count_keys():
    assert set(SHORT_SCENE_COUNT.keys()) == {"15", "30", "60"}
    assert SHORT_SCENE_COUNT["15"] == 3
    assert SHORT_SCENE_COUNT["30"] == 5
    assert SHORT_SCENE_COUNT["60"] == 8
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd services/content
.venv/bin/pytest tests/test_options.py -v 2>&1 | tail -15
```

Expected: FAIL (parse_shorts_options 미정의)

- [ ] **Step 3: options.py 수정**

```python
# youtube 작업의 params_json(길이·목소리·배경스타일) 파싱·매핑.
import json

SCENE_COUNT = {"3": 5, "5": 8, "7": 12, "10": 16}
SHORT_SCENE_COUNT = {"15": 3, "30": 5, "60": 8}
VOICE = {"female-calm": "ko-KR-Neural2-A", "female-bright": "ko-KR-Neural2-B", "male": "ko-KR-Neural2-C"}
STYLE = {
    "photo": "photorealistic, cinematic",
    "illust": "digital illustration, clean",
    "watercolor": "watercolor painting",
    "minimal": "minimalist flat design",
}
DEFAULTS = {"length": "5", "voice": "female-calm", "image_style": "photo"}
SHORTS_DEFAULTS = {"length": "30", "voice": "female-calm", "image_style": "photo", "upload_targets": []}


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


def parse_shorts_options(params_json: str | None) -> dict:
    opts = dict(SHORTS_DEFAULTS)
    opts["upload_targets"] = []
    if not params_json:
        return opts
    try:
        data = json.loads(params_json)
    except (json.JSONDecodeError, TypeError):
        return opts
    if isinstance(data, dict):
        if data.get("length") in SHORT_SCENE_COUNT:
            opts["length"] = data["length"]
        if data.get("voice") in VOICE:
            opts["voice"] = data["voice"]
        if data.get("image_style") in STYLE:
            opts["image_style"] = data["image_style"]
        targets = data.get("upload_targets", [])
        if isinstance(targets, list):
            opts["upload_targets"] = [t for t in targets if t in ("youtube", "instagram")]
    return opts
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd services/content
.venv/bin/pytest tests/test_options.py -v 2>&1 | tail -15
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/options.py services/content/tests/test_options.py
git commit -m "feat(worker): Shorts 옵션 파싱 추가 (parse_shorts_options, SHORT_SCENE_COUNT)"
```

---

### Task 2: video.py에 portrait 모드 추가

**Files:**
- Modify: `services/content/popory_content/video.py`

- [ ] **Step 1: 테스트 추가**

`services/content/tests/test_video.py`에 추가 (기존 테스트 파일 끝에):

```python
def test_render_card_portrait_creates_correct_size(tmp_path):
    """portrait=True 시 1080×1920 PNG가 생성된다."""
    from popory_content.video import _render_card
    from PIL import Image
    out = tmp_path / "card.png"
    _render_card("제목", "자막 테스트 문장입니다.", out, portrait=True)
    img = Image.open(out)
    assert img.size == (1080, 1920)

def test_render_card_landscape_creates_correct_size(tmp_path):
    """기본(portrait=False)은 1920×1080을 유지한다."""
    from popory_content.video import _render_card
    from PIL import Image
    out = tmp_path / "card.png"
    _render_card("제목", "자막", out)
    img = Image.open(out)
    assert img.size == (1920, 1080)
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd services/content
.venv/bin/pytest tests/test_video.py::test_render_card_portrait_creates_correct_size -v
```

Expected: FAIL (portrait 파라미터 미존재)

- [ ] **Step 3: video.py 수정 — 상수 분리 + portrait 파라미터**

`video.py`에서 `WIDTH, HEIGHT = 1920, 1080` 상수를 제거하고, 함수들이 `w`/`h` 인자를 받도록 수정한다.

`_render_card`에 `portrait: bool = False` 파라미터 추가:

```python
LANDSCAPE_W, LANDSCAPE_H = 1920, 1080
PORTRAIT_W, PORTRAIT_H = 1080, 1920
```

`_render_card` 시그니처 변경:
```python
def _render_card(title: str, subtitle: str, out_png: Path,
                 bg_image_bytes: bytes | None = None, portrait: bool = False) -> None:
    w = PORTRAIT_W if portrait else LANDSCAPE_W
    h = PORTRAIT_H if portrait else LANDSCAPE_H
    if bg_image_bytes:
        bg = Image.open(BytesIO(bg_image_bytes)).convert("RGB")
        img = _cover(bg, w, h)
        _scrim_bottom(img, w, h)
    else:
        img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    title_font = ImageFont.truetype(FONT_PATH, 56)
    sub_font = ImageFont.truetype(FONT_PATH, 64)
    t = "\n".join(textwrap.wrap(title, width=22)) or " "
    d.multiline_text((80, 70), t, font=title_font, fill=HEAD_COLOR, anchor="la", align="left", spacing=10)
    s = "\n".join(textwrap.wrap(subtitle, width=30)) or " "
    d.multiline_text((w / 2, h - 240), s, font=sub_font, fill=(255, 255, 255), anchor="ma", align="center", spacing=14)
    img.save(out_png)
```

`_scrim_bottom` 시그니처 변경:
```python
def _scrim_bottom(img: Image.Image, w: int = LANDSCAPE_W, h: int = LANDSCAPE_H) -> None:
    grad_h = int(h * 0.4)
    grad = Image.new("L", (1, grad_h))
    for y in range(grad_h):
        grad.putpixel((0, y), int(190 * y / grad_h))
    grad = grad.resize((w, grad_h))
    black = Image.new("RGB", (w, grad_h), (0, 0, 0))
    img.paste(black, (0, h - grad_h), grad)
```

`_cover` 함수는 w, h를 인자로 이미 받으므로 변경 불필요.

`render_video` 시그니처에 `portrait: bool = False` 추가. 내부에서 `_render_card(..., portrait=portrait)` 전달.

`make_video` 시그니처에 `portrait: bool = False` 추가. `render_video(..., portrait=portrait)` 전달.

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd services/content
.venv/bin/pytest tests/test_video.py -v 2>&1 | tail -20
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/video.py services/content/tests/test_video.py
git commit -m "feat(worker): video.py에 portrait 모드 추가 (1080×1920 세로형)"
```

---

### Task 3: video_prompt.py에 Shorts 프롬프트 추가

**Files:**
- Modify: `services/content/popory_content/video_prompt.py`

- [ ] **Step 1: 테스트 추가**

`services/content/tests/test_video_prompt.py`에 추가:

```python
from popory_content.video_prompt import build_shorts_system_prompt, build_shorts_user_message

def test_build_shorts_system_prompt_includes_shorts_rules():
    sp = build_shorts_system_prompt([], scene_count=5, image_style_kw="photorealistic")
    assert "쇼츠" in sp or "Shorts" in sp
    assert "5" in sp  # scene_count
    assert "60초" in sp or "세로형" in sp

def test_build_shorts_user_message_includes_topic():
    msg = build_shorts_user_message("전세사기 예방", [])
    assert "전세사기 예방" in msg
    assert "shorts_scenes_json" in msg or "scenes_json" in msg
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd services/content
.venv/bin/pytest tests/test_video_prompt.py::test_build_shorts_system_prompt_includes_shorts_rules -v
```

Expected: FAIL

- [ ] **Step 3: video_prompt.py에 Shorts 함수 추가**

기존 파일 끝에 추가:

```python
def _shorts_rules(scene_count: int, image_style_kw: str) -> str:
    return f"""당신은 한국어 세로형 쇼츠(Shorts/Reels) 영상 대본 작가입니다. 주제로 60초 이내 짧은 슬라이드쇼형 영상 대본을 만듭니다.

## 1. 리서치
- WebSearch·WebFetch 로 주제 관련 신뢰할 자료를 수집합니다.
- 사용자가 제공한 참고 링크가 있으면 반영합니다.
- 확인된 사실만 씁니다.

## 2. 구성
- 영상은 장면(scene) 약 {scene_count}개로 구성합니다.
- 세로형(9:16) 화면에 최적화합니다.
- 각 장면: caption(화면 헤드라인, 10자 이내), narration(1~2문장, 짧고 강렬하게).
- 각 장면에 image_prompt(영어, {image_style_kw} 스타일, 글자 없음)도 포함합니다.
- 첫 장면에서 강렬하게 후킹. 마지막 장면에서 팔로우 유도.
- 자연스러운 한국어 구어체.

## 3. 출력 (반드시 마지막 응답에 두 태그를 정확히 포함)
- 태그 안에는 코드 블록 표시(```)를 쓰지 않습니다.
<scenes_json>
[{{"caption": "...", "narration": "...", "image_prompt": "english description"}}, ...]
</scenes_json>
<video_meta>
{{"title": "...", "description": "...", "tags": ["..."]}}
</video_meta>
"""


def build_shorts_system_prompt(style_samples: list[str], scene_count: int = 5,
                                image_style_kw: str = "photorealistic, cinematic") -> str:
    sp = _shorts_rules(scene_count, image_style_kw)
    if style_samples:
        sp += _STYLE_HEADER
        for i, s in enumerate(style_samples, 1):
            sp += f"\n--- 샘플 {i} ---\n{s.strip()}\n"
    return sp


def build_shorts_user_message(topic: str, sources: list[dict[str, Any]]) -> str:
    lines = [f"주제: {topic}", "", "세로형 쇼츠 대본을 장면 배열로 작성하세요."]
    refs = [s for s in sources if s.get("url")]
    if refs:
        lines.append("\n참고 링크:")
        for s in refs:
            note = f" — {s['note']}" if s.get("note") else ""
            lines.append(f"- {s['url']}{note}")
    lines.append("")
    lines.append("마지막 응답에 <scenes_json>...</scenes_json> 과 <video_meta>...</video_meta> 두 태그를 정확히 포함하세요.")
    return "\n".join(lines)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd services/content
.venv/bin/pytest tests/test_video_prompt.py -v 2>&1 | tail -15
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/video_prompt.py services/content/tests/test_video_prompt.py
git commit -m "feat(worker): Shorts 전용 프롬프트 함수 추가"
```

---

### Task 4: worker.py에 Shorts 분기 추가

**Files:**
- Modify: `services/content/popory_content/worker.py`

- [ ] **Step 1: 테스트 추가**

`services/content/tests/test_worker.py`에 추가 (기존 mock 패턴 따라):

```python
def test_run_once_shorts_calls_make_video_portrait(tmp_path, mocker):
    """shorts 플랫폼은 make_video를 portrait=True로 호출한다."""
    mocker.patch("popory_content.worker.LOGS_DIR", tmp_path)
    fake_mp4 = tmp_path / "out.mp4"
    fake_mp4.write_bytes(b"fake")
    mocker.patch("popory_content.worker.make_video", return_value=(fake_mp4, [], {"title": "t"}))
    put_binary = mocker.patch.object(type(mocker.MagicMock()), "put_binary")
    patch_mock = mocker.MagicMock()
    client = mocker.MagicMock()
    client.post.return_value = {
        "job": {"id": "j1", "topic": "전세", "platform": "shorts", "params_json": '{"length":"30","upload_targets":["youtube"]}'},
        "sources": [],
        "style_samples": [],
    }
    client.put_binary = mocker.MagicMock()
    client.patch = mocker.MagicMock()

    from popory_content.worker import run_once
    result = run_once(client)

    assert result is True
    from popory_content.worker import make_video as mv
    call_kwargs = popory_content.worker.make_video.call_args
    assert call_kwargs.kwargs.get("portrait") is True
```

> **참고:** 기존 test_worker.py의 mocker 패턴을 확인해 `popory_content.worker.make_video`를 patch하는 방식을 따른다. 테스트가 기존 패턴과 다르면 기존 패턴을 우선한다.

- [ ] **Step 2: worker.py import 추가 및 shorts 분기 구현**

`worker.py` 상단 import 수정:

```python
from popory_content.options import parse_options, parse_shorts_options, SCENE_COUNT, SHORT_SCENE_COUNT, VOICE, STYLE
from popory_content.video_prompt import build_shorts_system_prompt, build_shorts_user_message
```

`run_once` 함수의 `if platform == "youtube":` 블록 다음에 `elif platform == "shorts":` 추가:

```python
    elif platform == "shorts":
        opts = parse_shorts_options(job.get("params_json"))
        mp4, scenes, meta = make_video(
            topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id,
            image_fetcher=lambda p: _safe_image(client, p),
            scene_count=SHORT_SCENE_COUNT[opts["length"]],
            image_style_kw=STYLE[opts["image_style"]],
            voice=VOICE[opts["voice"]],
            portrait=True,
            system_prompt_builder=build_shorts_system_prompt,
            user_msg_builder=build_shorts_user_message,
        )
        client.put_binary(f"/api/content/jobs/{job_id}/video", data=mp4.read_bytes(), content_type="video/mp4")
        script = "\n\n".join(f"[{s['caption']}]\n{s['narration']}" for s in scenes)
        _report(client, job_id, {"status": "review", "draft": script, "meta": meta}, "review")
```

`make_video`에 `system_prompt_builder`와 `user_msg_builder` 파라미터가 없으므로, `video.py`의 `generate_scenes`와 `make_video`도 프롬프트 빌더 주입을 받도록 수정하거나, shorts용 `generate_scenes` 오버라이드 함수를 추가한다.

간단한 방법: `generate_scenes`에 `system_prompt_builder` / `user_msg_builder` 파라미터 추가:

`video.py`의 `generate_scenes`:
```python
from popory_content.video_prompt import build_video_system_prompt, build_video_user_message

def generate_scenes(*, topic: str, sources: list[dict[str, Any]], style_samples: list[str],
                    job_id: str = "adhoc", scene_count: int = 8,
                    image_style_kw: str = "photorealistic, cinematic",
                    system_prompt_builder=None, user_msg_builder=None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sp_builder = system_prompt_builder or build_video_system_prompt
    um_builder = user_msg_builder or build_video_user_message
    sp = sp_builder(style_samples, scene_count=scene_count, image_style_kw=image_style_kw)
    um = um_builder(topic, sources)
    return run_claude_cli(system_prompt=sp, user_msg=um, parse=parse_video, job_id=job_id)
```

`make_video`에도 같은 파라미터 추가 후 `generate_scenes`에 전달.

- [ ] **Step 3: 전체 Python 테스트 통과 확인**

```bash
cd services/content
.venv/bin/pytest -v 2>&1 | tail -20
```

Expected: 모든 테스트 PASS

- [ ] **Step 4: 커밋**

```bash
git add services/content/popory_content/worker.py \
        services/content/popory_content/video.py \
        services/content/tests/test_worker.py
git commit -m "feat(worker): shorts 플랫폼 분기 추가 — portrait 9:16 영상 생성"
```

---

### Task 5: YouTube 업로드 API — shorts 허용

**Files:**
- Modify: `workers/api/src/routes/content_youtube_upload.ts`

- [ ] **Step 1: 플랫폼 체크 완화**

`content_youtube_upload.ts`에서:

```typescript
// 기존:
if (job.platform !== "youtube") return c.text("not a video", 400);

// 변경:
if (job.platform !== "youtube" && job.platform !== "shorts") return c.text("not a video", 400);
```

- [ ] **Step 2: 상세 페이지 shorts 지원**

`apps/portal/src/app/(authed)/content/[id]/page.tsx`에서 youtube 관련 분기를 shorts도 포함하도록 수정:

```typescript
// 기존:
{(job.status === "review" || job.status === "done") && job.platform === "youtube" && (

// 변경: shorts도 video + upload UI 표시
{(job.status === "review" || job.status === "done") && (job.platform === "youtube" || job.platform === "shorts") && (
```

`YoutubeUpload` 컴포넌트에도 shorts platform을 전달할 때 upload_targets를 params_json에서 파싱해 YouTube 업로드 버튼 표시 여부를 결정한다. Slice D(Instagram 업로드) 전까지는 YouTube 버튼만 보여도 무방하다.

`page.tsx`에서 `ytConnected` 체크 조건도 수정:

```typescript
// 기존:
if (job.platform === "youtube") {

// 변경:
if (job.platform === "youtube" || job.platform === "shorts") {
```

`YoutubeUpload` 컴포넌트의 platform check (현재 없음) — shorts 플랫폼일 때도 YouTube 업로드 버튼이 보여야 함. `upload_targets`에 "youtube"가 포함된 경우에만 버튼 표시:

`page.tsx`에서 params_json 파싱 추가:

```typescript
let uploadTargets: string[] = [];
if (job.platform === "shorts" && job.meta_json) {
  try {
    const p = JSON.parse(job.params_json ?? "{}") as { upload_targets?: string[] };
    uploadTargets = p.upload_targets ?? [];
  } catch { uploadTargets = []; }
}
const showYtUpload = job.platform === "youtube" || (job.platform === "shorts" && (uploadTargets.includes("youtube") || uploadTargets.length === 0));
```

그리고 `YoutubeUpload` 렌더를 `showYtUpload`로 조건부 렌더.

> **참고:** `job` 인터페이스에 `params_json` 필드가 없으면 추가: `params_json: string | null;`

- [ ] **Step 3: API 테스트 추가**

`workers/api/src/routes/content_youtube_upload.test.ts`에 추가:

```typescript
it("shorts 플랫폼도 youtube-upload 허용", async () => {
  const ck = await userCookie();
  // youtube_connections에 연결 추가
  await env.DB.prepare("INSERT INTO youtube_connections (sub, channel_id, channel_title, refresh_token, connected_at) VALUES (?,?,?,?,?)")
    .bind("u1", "ch1", "채널", "enc_token", 1).run();
  // shorts job 생성
  const now = Math.floor(Date.now() / 1000);
  await env.DB.prepare(
    "INSERT INTO content_jobs (id, owner_sub, topic, platform, status, created_at, updated_at) VALUES (?,?,?,'shorts','review',?,?)"
  ).bind("j_shorts", "u1", "t", now, now).run();
  // R2에 video 파일 존재 시뮬레이션
  await env.R2.put("content/video/j_shorts.mp4", new Uint8Array([1, 2, 3]));
  const res = await SELF.fetch("https://example.com/api/content/jobs/j_shorts/youtube-upload", {
    method: "POST", headers: { cookie: ck, "content-type": "application/json" },
    body: JSON.stringify({ privacy: "private" }),
  });
  expect(res.status).toBe(200);
});
```

- [ ] **Step 4: 전체 테스트 통과 확인**

```bash
cd workers/api
npm test 2>&1 | tail -10
```

Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add workers/api/src/routes/content_youtube_upload.ts \
        workers/api/src/routes/content_youtube_upload.test.ts \
        apps/portal/src/app/\(authed\)/content/\[id\]/page.tsx
git commit -m "feat(api,portal): shorts 플랫폼 YouTube 업로드 허용 + 상세 페이지 shorts 지원"
```

---

### Task 6: 워커 재시작 + prod 배포

- [ ] **Step 1: 워커 코드 반영**

```bash
launchctl kickstart -k gui/$(id -u)/com.popory.content-worker
```

- [ ] **Step 2: API Worker 배포 (youtube_upload 변경)**

```bash
cd workers/api
wrangler deploy --env prod
```

- [ ] **Step 3: Portal 배포**

```bash
cd apps/portal
npm run build:cf
wrangler pages deploy .vercel/output/static --project-name popory-portal --branch main
```

- [ ] **Step 4: 동작 확인**

주제 그룹 페이지에서 "유튜브 쇼츠" idle 카드 → "생성 시작" → queued → (워커 처리) → review → "결과 보기" → video 태그에 세로형 영상 표시 확인.
