# 영상 AI 장면 이미지 (Workers AI flux) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** YouTube 영상의 장면 배경을 단색 카드에서 Cloudflare Workers AI(flux) 생성 이미지로 바꾼다(실패 시 단색 폴백).

**Architecture:** Worker `[ai]` 바인딩으로 `POST /api/content/ai-image` 엔드포인트가 flux 이미지를 PNG로 반환. 로컬 워커가 장면별 `image_prompt`로 호출해 받은 이미지를 Pillow 배경으로 합성. video.py 는 포털을 모르고 `image_fetcher` 주입을 받는다.

**Tech Stack:** Cloudflare Workers AI(flux-1-schnell), Hono, Python(Pillow, pytest), claude CLI.

**전제:** YouTube 영상 생성(Slice)이 prod 가동. 이미지 접근 = Worker AI 바인딩(토큰 권한 불필요). 스펙 `docs/superpowers/specs/2026-06-06-video-ai-scene-images-design.md`.

---

## File Structure

| 파일 | 변경 | 책임 |
|------|------|------|
| `infra/wrangler/api.toml` | 수정 | `[ai]` + `[env.prod.ai]` 바인딩 |
| `workers/api/src/types.ts` | 수정 | `Env.AI` 타입 |
| `workers/api/src/routes/content_ai_image.ts` | 신규 | `POST /api/content/ai-image` → flux PNG |
| `workers/api/src/routes/content_ai_image.test.ts` | 신규 | 인증·검증 vitest |
| `workers/api/src/app.ts` | 수정 | mount |
| `services/content/popory_content/video_prompt.py` | 수정 | 장면 image_prompt 지시 |
| `services/content/tests/test_video_prompt.py` | 수정 | image_prompt 단언 |
| `services/content/tests/test_video_contract.py` | 수정 | image_prompt 통과 단언 |
| `services/content/popory_content/video.py` | 수정 | `_render_card(bg_image_bytes)` + `render_video(image_fetcher)` |
| `services/content/tests/test_video.py` | 수정 | 합성·폴백 테스트 |
| `services/content/popory_content/portal_client.py` | 수정 | `post_for_bytes` |
| `services/content/popory_content/worker.py` | 수정 | image_fetcher 주입 |
| `services/content/tests/test_worker.py` | 수정 | image_fetcher 전달 단언 |

---

## Task 1: Worker AI 바인딩 + 이미지 라우트

**Files:**
- Modify: `infra/wrangler/api.toml`
- Modify: `workers/api/src/types.ts`
- Create: `workers/api/src/routes/content_ai_image.ts`
- Create: `workers/api/src/routes/content_ai_image.test.ts`
- Modify: `workers/api/src/app.ts`

- [ ] **Step 1: api.toml 에 AI 바인딩 추가**

`infra/wrangler/api.toml` 의 `[[kv_namespaces]]`(기본) 블록 아래에 추가:
```toml
[ai]
binding = "AI"
```
그리고 `[[env.prod.kv_namespaces]]` 블록 아래(prod)에 추가:
```toml
[env.prod.ai]
binding = "AI"
```

- [ ] **Step 2: Env 타입에 AI 추가**

`workers/api/src/types.ts` 의 `Env` 인터페이스에 추가(마지막 필드 뒤):
```ts
  AI: { run(model: string, inputs: { prompt: string }): Promise<{ image?: string }> };
```

- [ ] **Step 3: 실패 테스트 작성**

`workers/api/src/routes/content_ai_image.test.ts`:
```ts
// AI 이미지 라우트의 서비스 인증·검증을 확인한다(실제 생성은 e2e).
import { env, SELF } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import { ensureActiveKey, loadActivePrivate } from "../db/signing_keys";
import { signAreaToken } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function workerToken(area = "content-worker") {
  await ensureActiveKey(env.DB);
  const k = await loadActivePrivate(env.DB);
  return signAreaToken({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "service:content-worker", email: "w@svc", area, aud: "popory-portal" }, ttlSeconds: 600 });
}

describe("POST /api/content/ai-image", () => {
  it("서비스 JWT 없으면 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/ai-image", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ prompt: "x" }) });
    expect(res.status).toBe(401);
  });
  it("잘못된 area 는 403", async () => {
    const token = await workerToken("brief");
    const res = await SELF.fetch("https://example.com/api/content/ai-image", { method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" }, body: JSON.stringify({ prompt: "x" }) });
    expect(res.status).toBe(403);
  });
  it("빈 prompt 는 400", async () => {
    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/ai-image", { method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" }, body: JSON.stringify({ prompt: "" }) });
    expect(res.status).toBe(400);
  });
});
```

- [ ] **Step 4: 실패 확인**

Run: `pnpm --filter @popory/api test -- --run content_ai_image`
Expected: FAIL (라우트 없음 → 404).

- [ ] **Step 5: 라우트 구현**

`workers/api/src/routes/content_ai_image.ts`:
```ts
// 컨텐츠 영상용 AI 이미지 생성 — Workers AI flux → PNG 바이트.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import type { AppVars } from "../middleware/session";

const WORKER_AREA = "content-worker";
type Vars = AppVars & ServiceVars;

export function mountContentAiImage(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/content/ai-image", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const body = (await c.req.json().catch(() => null)) as { prompt?: unknown } | null;
    const prompt = body?.prompt;
    if (typeof prompt !== "string" || prompt.length < 1 || prompt.length > 1500) return c.text("bad request", 400);
    const out = await c.env.AI.run("@cf/black-forest-labs/flux-1-schnell", { prompt });
    if (!out.image) return c.text("no image", 502);
    const bytes = Uint8Array.from(atob(out.image), (ch) => ch.charCodeAt(0));
    return new Response(bytes, { headers: { "content-type": "image/png" } });
  });
}
```

- [ ] **Step 6: app.ts 에 mount**

`workers/api/src/app.ts` 에 import 추가:
```ts
import { mountContentAiImage } from "./routes/content_ai_image";
```
mount 추가(`mountContentJobs(app);` 아래):
```ts
  mountContentAiImage(app);
```

- [ ] **Step 7: 통과 + 타입체크**

Run: `pnpm --filter @popory/api test -- --run content_ai_image 2>&1 | tail -4`
Expected: 3 passed.
Run: `pnpm --filter @popory/api typecheck 2>&1 | tail -3`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
cd /Users/daegong/projects/popory
git add infra/wrangler/api.toml workers/api/src/types.ts workers/api/src/routes/content_ai_image.ts workers/api/src/routes/content_ai_image.test.ts workers/api/src/app.ts
git commit -m "feat(content): AI 이미지 라우트 (Workers AI flux 바인딩)"
```

---

## Task 2: 대본 프롬프트·파서 — image_prompt

**Files:**
- Modify: `services/content/popory_content/video_prompt.py`
- Modify: `services/content/tests/test_video_prompt.py`
- Modify: `services/content/tests/test_video_contract.py`

- [ ] **Step 1: 테스트 갱신 (실패 유도)**

`services/content/tests/test_video_prompt.py` 의 `test_system_prompt_has_contract` 에 단언 추가:
```python
    assert "image_prompt" in sp
```

`services/content/tests/test_video_contract.py` 의 `test_parses_scenes_and_meta` 에서 첫 장면에 image_prompt 를 넣고 통과를 확인하도록 scenes_json 을 교체:
```python
<scenes_json>
[{"caption": "사피엔스란", "narration": "인류의 역사를 다룬 책입니다.", "image_prompt": "ancient humans by fire, cinematic"}, {"caption": "핵심 메시지", "narration": "허구가 협력을 낳았습니다."}]
</scenes_json>
```
그리고 단언 추가(`test_parses_scenes_and_meta` 안):
```python
    assert scenes[0]["image_prompt"].startswith("ancient")
    assert "image_prompt" not in scenes[1]  # image_prompt 없는 장면도 허용
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video_prompt.py tests/test_video_contract.py -q`
Expected: FAIL (prompt 에 image_prompt 없음).

- [ ] **Step 3: video_prompt.py 수정**

`services/content/popory_content/video_prompt.py` 의 `_BASE_RULES` 에서 "## 2. 구성" 의 caption/narration 설명 줄 뒤에 한 줄 추가:
```
- 각 장면에 image_prompt(그 장면 분위기를 묘사하는 영어 이미지 생성 프롬프트, 한 문장)도 포함합니다.
```
그리고 "## 3. 출력" 의 scenes_json 예시를 교체:
```
<scenes_json>
[{"caption": "...", "narration": "...", "image_prompt": "english description for image"}, ...]
</scenes_json>
```

(`video_contract.py` 는 변경 없음 — image_prompt 는 dict 에 그대로 통과, caption·narration 만 검증.)

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video_prompt.py tests/test_video_contract.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/video_prompt.py services/content/tests/test_video_prompt.py services/content/tests/test_video_contract.py
git commit -m "feat(content-worker): 장면별 image_prompt 추가"
```

---

## Task 3: video.py — 이미지 배경 합성 + image_fetcher

**Files:**
- Modify: `services/content/popory_content/video.py`
- Modify: `services/content/tests/test_video.py`

- [ ] **Step 1: _render_card 단위 테스트 추가 (실패 유도)**

`services/content/tests/test_video.py` 에 추가(스킵 마커 위쪽, 항상 실행되도록 별도 함수):
```python
import io
from PIL import Image as _Image
from popory_content.video import _render_card


def test_render_card_with_and_without_bg(tmp_path):
    # 가짜 배경 PNG 바이트
    buf = io.BytesIO()
    _Image.new("RGB", (320, 180), (200, 100, 50)).save(buf, format="PNG")
    bg = buf.getvalue()
    p1 = tmp_path / "with_bg.png"
    p2 = tmp_path / "no_bg.png"
    _render_card("제목", "본문 내레이션", p1, bg_image_bytes=bg)
    _render_card("제목", "본문 내레이션", p2, bg_image_bytes=None)
    assert p1.exists() and p1.stat().st_size > 1000
    assert p2.exists() and p2.stat().st_size > 1000
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video.py::test_render_card_with_and_without_bg -q`
Expected: FAIL (`_render_card` 시그니처에 bg_image_bytes 없음 → TypeError).

- [ ] **Step 3: video.py 수정**

`services/content/popory_content/video.py` 상단 import 에 추가:
```python
from io import BytesIO
```

`_render_card` 를 아래로 교체:
```python
def _cover(im: Image.Image, w: int, h: int) -> Image.Image:
    """이미지를 w×h 를 꽉 채우도록 비율 유지 크롭."""
    scale = max(w / im.width, h / im.height)
    nw, nh = int(im.width * scale), int(im.height * scale)
    im = im.resize((nw, nh))
    left, top = (nw - w) // 2, (nh - h) // 2
    return im.crop((left, top, left + w, top + h))


def _render_card(caption: str, narration: str, out_png: Path, bg_image_bytes: bytes | None = None) -> None:
    if bg_image_bytes:
        bg = Image.open(BytesIO(bg_image_bytes)).convert("RGB")
        img = _cover(bg, WIDTH, HEIGHT)
        img = Image.blend(img, Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0)), 0.45)
    else:
        img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)
    head = ImageFont.truetype(FONT_PATH, 96)
    body = ImageFont.truetype(FONT_PATH, 48)
    cap = "\n".join(textwrap.wrap(caption, width=16)) or " "
    d.multiline_text((WIDTH / 2, HEIGHT / 2 - 120), cap, font=head, fill=HEAD_COLOR, anchor="mm", align="center", spacing=18)
    nar = "\n".join(textwrap.wrap(narration, width=34)) or " "
    d.multiline_text((WIDTH / 2, HEIGHT - 300), nar, font=body, fill=BODY_COLOR, anchor="ma", align="center", spacing=14)
    img.save(out_png)
```

`render_video` 시그니처와 장면 루프를 교체:
```python
def render_video(scenes: list[dict[str, Any]], job_id: str = "adhoc",
                 image_fetcher: Any = None) -> Path:
    """장면 배열 → MP4. image_fetcher(prompt)->bytes|None 가 있으면 AI 이미지 배경 사용."""
    if not Path(FONT_PATH).exists():
        raise VideoError(f"한국어 폰트 없음: {FONT_PATH}")
    work = TMP / f"video_{job_id}"
    work.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for i, scene in enumerate(scenes):
        narration = str(scene["narration"]).strip()
        caption = str(scene["caption"]).strip()
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
        clips.append(clip)

    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{p}'\n" for p in clips), encoding="utf-8")
    out = work / "out.mp4"
    _run([FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(out)])
    return out
```

`make_video` 시그니처에 image_fetcher 추가:
```python
def make_video(*, topic: str, sources: list[dict[str, Any]], style_samples: list[str],
               job_id: str = "adhoc", image_fetcher: Any = None) -> tuple[Path, list[dict[str, Any]], dict[str, Any]]:
    scenes, meta = generate_scenes(topic=topic, sources=sources, style_samples=style_samples, job_id=job_id)
    mp4 = render_video(scenes, job_id=job_id, image_fetcher=image_fetcher)
    return mp4, scenes, meta
```

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video.py -q`
Expected: PASS (카드 단위테스트 + 렌더 스모크).

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/video.py services/content/tests/test_video.py
git commit -m "feat(content-worker): AI 이미지 배경 합성 + image_fetcher 주입"
```

---

## Task 4: portal_client + worker — image_fetcher 연결

**Files:**
- Modify: `services/content/popory_content/portal_client.py`
- Modify: `services/content/popory_content/worker.py`
- Modify: `services/content/tests/test_worker.py`

- [ ] **Step 1: portal_client 에 post_for_bytes 추가**

`services/content/popory_content/portal_client.py` 의 `put_binary` 뒤에 추가:
```python
    def post_for_bytes(self, path: str, *, json: Any) -> bytes:
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.token_provider()}", "Content-Type": "application/json"}
        try:
            resp = requests.post(url, headers=headers, json=json, timeout=60)
        except requests.RequestException as e:
            raise PortalError(f"network: {e}", exit_code=5) from e
        if resp.status_code >= 400:
            raise PortalError(f"ai-image {resp.status_code}: {resp.text[:200]}", exit_code=4)
        return resp.content
```

- [ ] **Step 2: worker 테스트 갱신 (image_fetcher 전달 확인)**

`services/content/tests/test_worker.py` 의 `test_youtube_branch_uploads_video_and_reviews` 에서 make_video monkeypatch 를 kwargs 캡처로 바꾼다:
```python
    captured = {}
    def fake_make_video(**kw):
        captured.update(kw)
        return (mp4, [{"caption": "c", "narration": "n"}], {"title": "T"})
    monkeypatch.setattr(worker, "make_video", fake_make_video)
```
그리고 단언 추가(파일 끝 같은 테스트 안):
```python
    assert callable(captured.get("image_fetcher"))
```

새 테스트 추가(파일 끝):
```python
def test_safe_image_returns_none_on_error():
    class C:
        def post_for_bytes(self, path, *, json):
            raise worker.PortalError("boom", exit_code=4)
    assert worker._safe_image(C(), "prompt") is None


def test_safe_image_returns_bytes():
    class C:
        def post_for_bytes(self, path, *, json):
            return b"\x89PNG"
    assert worker._safe_image(C(), "prompt") == b"\x89PNG"
```

- [ ] **Step 3: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_worker.py -q`
Expected: FAIL (`worker._safe_image` 없음 / image_fetcher 미전달).

- [ ] **Step 4: worker.py 수정**

`services/content/popory_content/worker.py` 에 헬퍼 추가(`_report` 함수 아래):
```python
def _safe_image(client, prompt: str):
    """AI 이미지 1장. 실패하면 None(단색 폴백)."""
    try:
        return client.post_for_bytes("/api/content/ai-image", json={"prompt": prompt})
    except Exception:  # noqa: BLE001
        return None
```

youtube 분기의 make_video 호출에 image_fetcher 주입:
```python
        if platform == "youtube":
            mp4, scenes, meta = make_video(
                topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id,
                image_fetcher=lambda p: _safe_image(client, p),
            )
```

- [ ] **Step 5: 통과 + 전체 회귀**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_worker.py -q`
Expected: PASS.
Run: `pytest -q --ignore=tests/test_video.py`
Expected: 전체 PASS(영상 스모크 제외 빠르게).

- [ ] **Step 6: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/portal_client.py services/content/popory_content/worker.py services/content/tests/test_worker.py
git commit -m "feat(content-worker): 워커가 AI 이미지 fetcher 를 영상에 주입"
```

---

## Task 5: 검증 + 배포

**Files:** 없음

- [ ] **Step 1: 전체 회귀**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest -q --ignore=tests/test_video.py` → PASS.
Run: `cd /Users/daegong/projects/popory && pnpm --filter @popory/api test -- --run 2>&1 | grep Tests` → PASS.
Run: `pnpm -r typecheck 2>&1 | grep -E "Done|error"` → 6 Done.

- [ ] **Step 2: prod 배포**

```bash
cd /Users/daegong/projects/popory/workers/api
pnpm exec wrangler deploy --env prod --config ../../infra/wrangler/api.toml
```
(AI 바인딩이 prod Worker 에 붙는다. 배포 로그의 bindings 에 `AI` 표시 확인.)
포털은 변경 없음(재배포 불필요).

- [ ] **Step 3: 워커 재시작**

```bash
launchctl kickstart -k "gui/$(id -u)/com.popory.content-worker"
```

- [ ] **Step 4: ai-image 스모크 (서비스 JWT)**

로컬에서 서비스 JWT 로 ai-image 를 호출해 PNG 가 오는지 확인:
```bash
cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && set -a && source secrets/env.sh && set +a && python - <<'PY'
from pathlib import Path
from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient
import os
m = KeyMaterial.load(Path(os.environ["POPORY_CONTENT_KEY_FILE"]))
c = PortalClient(base_url=os.environ["POPORY_PORTAL_API_BASE"], token_provider=lambda: sign_for_portal(m, area="content-worker", ttl_seconds=300))
b = c.post_for_bytes("/api/content/ai-image", json={"prompt": "a serene mountain landscape, minimalist illustration"})
print("image bytes:", len(b), "| png header:", b[:4])
PY
```
Expected: 수만 바이트 + PNG 헤더(`b'\x89PNG'`). 실패(401/403/500)면 prod 배포의 AI 바인딩·area 를 점검(추측 금지, 응답 메시지 확인).

- [ ] **Step 5: e2e (휴먼)**

새 YouTube 작업 → 워커가 장면별 flux 이미지 생성·합성 → review → 상세에서 이미지 배경 영상 재생.

---

## Self-Review (작성자 체크)

**Spec coverage:**
- §5.1 AI 바인딩·타입 → Task 1. ✅
- §5.2 이미지 라우트 → Task 1. ✅
- §5.3 image_prompt 프롬프트/파서 → Task 2. ✅
- §5.4 합성·image_fetcher → Task 3. ✅
- §5.5 post_for_bytes·worker 주입 → Task 4. ✅
- §6 폴백(이미지 실패→단색) → Task 3 render_video try/except + Task 4 _safe_image. ✅
- §7 테스트 → 각 Task. ✅

**Placeholder scan:** 모든 단계 실제 코드. flux 응답 `{image: base64}` 디코드 구체화. e2e 스모크 명령 구체. ✅

**Type consistency:** `_render_card(caption, narration, out_png, bg_image_bytes=None)`·`render_video(scenes, job_id, image_fetcher=None)`·`make_video(..., image_fetcher=None)`·`post_for_bytes(path, json)->bytes`·`_safe_image(client, prompt)` 명칭·시그니처가 Task 3·4 정의·사용 일치. `Env.AI.run(model, {prompt})->{image?}` Task 1 타입·라우트 일치. ai-image 경로·area(content-worker) Task 1·4 일관. ✅
