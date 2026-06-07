# 멀티플랫폼 Slice C — Instagram Image(캐러셀) 파이프라인 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 인스타그램 캐러셀(1080×1080 정사각형 슬라이드 여러 장)을 생성하는 파이프라인을 추가한다.

**Architecture:** Claude CLI가 슬라이드 배열(제목+본문+image_prompt)을 생성하고, Pillow로 1080×1080 PNG를 렌더한다. 워커가 `/api/content/jobs/:id/carousel` API에 base64 이미지를 업로드하고, R2에 `content/carousel/{id}/{n}.jpg` 키로 저장한다. 포털 상세 페이지에 슬라이드 그리드 프리뷰를 추가한다.

**Tech Stack:** Python 3.11, Pillow, Hono, Next.js

**선행 조건:** Slice A 완료 (content_topics, idle 상태).

---

## 파일 맵

| 경로 | 변경 |
|---|---|
| `services/content/popory_content/instagram_image_prompt.py` | 신규 |
| `services/content/popory_content/instagram_image_contract.py` | 신규 |
| `services/content/popory_content/instagram_image_render.py` | 신규 |
| `services/content/popory_content/portal_client.py` | 수정 — put_carousel 추가 |
| `services/content/popory_content/worker.py` | 수정 — instagram-image 분기 추가 |
| `workers/api/src/routes/content_jobs.ts` | 수정 — carousel 엔드포인트 추가 |
| `workers/api/src/routes/content_jobs.test.ts` | 수정 — carousel 테스트 추가 |
| `apps/portal/src/app/(authed)/content/[id]/CarouselPreview.tsx` | 신규 |
| `apps/portal/src/app/(authed)/content/[id]/page.tsx` | 수정 — instagram-image 분기 |
| `services/content/tests/test_instagram_image_prompt.py` | 신규 |
| `services/content/tests/test_instagram_image_contract.py` | 신규 |
| `services/content/tests/test_instagram_image_render.py` | 신규 |

---

### Task 1: Claude 프롬프트 모듈

**Files:**
- Create: `services/content/popory_content/instagram_image_prompt.py`
- Create: `services/content/tests/test_instagram_image_prompt.py`

- [ ] **Step 1: 테스트 작성**

```python
# 인스타그램 캐러셀 프롬프트 빌더 테스트.
from popory_content.instagram_image_prompt import build_carousel_system_prompt, build_carousel_user_message


def test_system_prompt_includes_slide_count():
    sp = build_carousel_system_prompt([], slide_count=7)
    assert "7" in sp


def test_system_prompt_includes_style_samples():
    sp = build_carousel_system_prompt(["샘플 텍스트"], slide_count=5)
    assert "샘플 텍스트" in sp


def test_user_message_includes_topic():
    msg = build_carousel_user_message("전세사기 예방", [])
    assert "전세사기 예방" in msg
    assert "slides_json" in msg


def test_user_message_includes_sources():
    sources = [{"url": "https://example.com", "note": "참고"}]
    msg = build_carousel_user_message("t", sources)
    assert "https://example.com" in msg
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd services/content
.venv/bin/pytest tests/test_instagram_image_prompt.py -v 2>&1 | tail -10
```

Expected: FAIL

- [ ] **Step 3: instagram_image_prompt.py 작성**

```python
# claude CLI에 줄 인스타그램 캐러셀 시스템/유저 프롬프트.
from typing import Any


def _rules(slide_count: int) -> str:
    return f"""당신은 한국어 인스타그램 캐러셀 콘텐츠 작가입니다. 주제로 슬라이드 {slide_count}장짜리 캐러셀 게시물을 만듭니다.

## 1. 리서치
- WebSearch·WebFetch 로 주제 관련 신뢰할 자료를 수집합니다.
- 확인된 사실만 씁니다.

## 2. 구성
- 슬라이드 {slide_count}장을 만듭니다.
- 첫 슬라이드: 강렬한 후킹 제목(팔로우 욕구 유발).
- 중간 슬라이드: 핵심 내용을 슬라이드별 하나씩.
- 마지막 슬라이드: 요약 + 팔로우 유도.
- 각 슬라이드: title(10자 이내 굵은 헤드라인), body(2~3줄 본문), image_prompt(영어, 정사각형 이미지 묘사, 텍스트 없음).
- 전체 게시물 caption도 작성합니다(해시태그 포함, 500자 이내).

## 3. 출력 (반드시 마지막 응답에 두 태그를 정확히 포함)
- 태그 안에는 코드 블록 표시(```)를 쓰지 않습니다.
<slides_json>
[{{"title": "...", "body": "...", "image_prompt": "english square image description"}}, ...]
</slides_json>
<carousel_meta>
{{"caption": "...", "hashtags": ["..."]}}
</carousel_meta>
"""


_STYLE_HEADER = "\n## 4. 말투 스타일 (아래 샘플의 어조를 따르세요)\n"


def build_carousel_system_prompt(style_samples: list[str], slide_count: int = 7) -> str:
    sp = _rules(slide_count)
    if style_samples:
        sp += _STYLE_HEADER
        for i, s in enumerate(style_samples, 1):
            sp += f"\n--- 샘플 {i} ---\n{s.strip()}\n"
    return sp


def build_carousel_user_message(topic: str, sources: list[dict[str, Any]]) -> str:
    lines = [f"주제: {topic}", "", "시스템 규칙에 따라 인스타그램 캐러셀을 작성하세요."]
    refs = [s for s in sources if s.get("url")]
    if refs:
        lines.append("\n참고 링크:")
        for s in refs:
            note = f" — {s['note']}" if s.get("note") else ""
            lines.append(f"- {s['url']}{note}")
    lines.append("")
    lines.append("마지막 응답에 <slides_json>...</slides_json> 과 <carousel_meta>...</carousel_meta> 두 태그를 정확히 포함하세요.")
    return "\n".join(lines)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd services/content
.venv/bin/pytest tests/test_instagram_image_prompt.py -v 2>&1 | tail -10
```

Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/instagram_image_prompt.py \
        services/content/tests/test_instagram_image_prompt.py
git commit -m "feat(worker): 인스타그램 캐러셀 프롬프트 빌더 추가"
```

---

### Task 2: 출력 계약 파서

**Files:**
- Create: `services/content/popory_content/instagram_image_contract.py`
- Create: `services/content/tests/test_instagram_image_contract.py`

- [ ] **Step 1: 테스트 작성**

```python
# 인스타그램 캐러셀 출력 계약 파서 테스트.
import pytest
from popory_content.instagram_image_contract import parse_carousel
from popory_content.contract import ContractError


VALID_OUTPUT = """
여기 캐러셀입니다.
<slides_json>
[{"title": "제목1", "body": "본문1", "image_prompt": "sunny sky"},
 {"title": "제목2", "body": "본문2", "image_prompt": "green field"}]
</slides_json>
<carousel_meta>
{"caption": "캡션 #해시태그", "hashtags": ["해시태그"]}
</carousel_meta>
"""


def test_parse_carousel_success():
    slides, meta = parse_carousel(VALID_OUTPUT)
    assert len(slides) == 2
    assert slides[0]["title"] == "제목1"
    assert slides[1]["image_prompt"] == "green field"
    assert meta["caption"] == "캡션 #해시태그"


def test_parse_carousel_missing_tag_raises():
    with pytest.raises(ContractError):
        parse_carousel("태그가 없는 출력")


def test_parse_carousel_empty_slides_raises():
    bad = "<slides_json>[]</slides_json><carousel_meta>{\"caption\":\"c\"}</carousel_meta>"
    with pytest.raises(ContractError):
        parse_carousel(bad)


def test_parse_carousel_missing_title_raises():
    bad = '<slides_json>[{"body":"b","image_prompt":"p"}]</slides_json><carousel_meta>{"caption":"c"}</carousel_meta>'
    with pytest.raises(ContractError):
        parse_carousel(bad)
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd services/content
.venv/bin/pytest tests/test_instagram_image_contract.py -v
```

Expected: FAIL

- [ ] **Step 3: instagram_image_contract.py 작성**

```python
# claude 출력에서 slides_json·carousel_meta 두 태그를 추출·파싱.
import json
import re
from typing import Any

from popory_content.contract import ContractError


def parse_carousel(text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    slides_m = re.search(r"<slides_json>\s*(\[.*\])\s*</slides_json>", text, re.DOTALL)
    meta_m = re.search(r"<carousel_meta>\s*(\{.*?\})\s*</carousel_meta>", text, re.DOTALL)
    if not slides_m or not meta_m:
        raise ContractError("slides_json/carousel_meta 태그를 찾지 못함")
    try:
        slides = json.loads(slides_m.group(1).strip())
        meta = json.loads(meta_m.group(1).strip())
    except json.JSONDecodeError as e:
        raise ContractError(f"carousel JSON 파싱 실패: {e}") from e
    if not isinstance(slides, list) or not slides:
        raise ContractError("slides 가 비어있음")
    for s in slides:
        if not s.get("title") or not s.get("body"):
            raise ContractError("slide 에 title/body 누락")
    return slides, meta
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd services/content
.venv/bin/pytest tests/test_instagram_image_contract.py -v
```

Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/instagram_image_contract.py \
        services/content/tests/test_instagram_image_contract.py
git commit -m "feat(worker): 인스타그램 캐러셀 출력 계약 파서 추가"
```

---

### Task 3: Pillow 렌더러

**Files:**
- Create: `services/content/popory_content/instagram_image_render.py`
- Create: `services/content/tests/test_instagram_image_render.py`

- [ ] **Step 1: 테스트 작성**

```python
# 인스타그램 캐러셀 슬라이드 Pillow 렌더러 테스트.
from popory_content.instagram_image_render import render_slide, render_carousel


def test_render_slide_returns_jpeg_bytes():
    slide = {"title": "제목", "body": "본문 내용입니다.", "image_prompt": "sunny sky"}
    data = render_slide(slide)
    assert isinstance(data, bytes)
    assert len(data) > 1000
    # JPEG magic bytes
    assert data[:2] == b"\xff\xd8"


def test_render_carousel_returns_list():
    slides = [
        {"title": f"제목{i}", "body": "본문", "image_prompt": "sky"}
        for i in range(3)
    ]
    images = render_carousel(slides)
    assert len(images) == 3
    for img in images:
        assert img[:2] == b"\xff\xd8"


def test_render_slide_with_bg_image(tmp_path):
    """배경 이미지가 주어지면 커버 크롭해 사용한다."""
    from PIL import Image
    import io
    bg = Image.new("RGB", (800, 600), (100, 200, 100))
    buf = io.BytesIO()
    bg.save(buf, format="JPEG")
    bg_bytes = buf.getvalue()
    slide = {"title": "제목", "body": "본문", "image_prompt": "p"}
    data = render_slide(slide, bg_image_bytes=bg_bytes)
    assert data[:2] == b"\xff\xd8"
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd services/content
.venv/bin/pytest tests/test_instagram_image_render.py -v
```

Expected: FAIL

- [ ] **Step 3: instagram_image_render.py 작성**

```python
# Pillow로 인스타그램 캐러셀 슬라이드(1080×1080) PNG를 JPEG로 렌더링.
import io
import textwrap
from typing import Any

from PIL import Image, ImageDraw, ImageFont

SLIDE_SIZE = 1080
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
BG_COLOR = (11, 31, 58)
HEAD_COLOR = (255, 255, 255)
BODY_COLOR = (220, 230, 245)


def _cover(im: Image.Image, size: int) -> Image.Image:
    scale = max(size / im.width, size / im.height)
    nw, nh = int(im.width * scale), int(im.height * scale)
    im = im.resize((nw, nh))
    left = (nw - size) // 2
    top = (nh - size) // 2
    return im.crop((left, top, left + size, top + size))


def _scrim(img: Image.Image) -> None:
    grad_h = int(SLIDE_SIZE * 0.5)
    grad = Image.new("L", (1, grad_h))
    for y in range(grad_h):
        grad.putpixel((0, y), int(200 * y / grad_h))
    grad = grad.resize((SLIDE_SIZE, grad_h))
    black = Image.new("RGB", (SLIDE_SIZE, grad_h), (0, 0, 0))
    img.paste(black, (0, SLIDE_SIZE - grad_h), grad)


def render_slide(slide: dict[str, Any], bg_image_bytes: bytes | None = None) -> bytes:
    if bg_image_bytes:
        bg = Image.open(io.BytesIO(bg_image_bytes)).convert("RGB")
        img = _cover(bg, SLIDE_SIZE)
        _scrim(img)
    else:
        img = Image.new("RGB", (SLIDE_SIZE, SLIDE_SIZE), BG_COLOR)

    d = ImageDraw.Draw(img)
    try:
        title_font = ImageFont.truetype(FONT_PATH, 72)
        body_font = ImageFont.truetype(FONT_PATH, 48)
    except OSError:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    title = slide.get("title", "")
    body = slide.get("body", "")

    t = "\n".join(textwrap.wrap(title, width=14)) or " "
    d.multiline_text((80, 120), t, font=title_font, fill=HEAD_COLOR, anchor="la", spacing=12)

    b = "\n".join(textwrap.wrap(body, width=22)) or " "
    d.multiline_text((80, SLIDE_SIZE // 2), b, font=body_font, fill=BODY_COLOR, anchor="la", spacing=10)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def render_carousel(slides: list[dict[str, Any]],
                    image_fetcher: Any = None) -> list[bytes]:
    result = []
    for slide in slides:
        bg = None
        if image_fetcher and slide.get("image_prompt"):
            try:
                bg = image_fetcher(slide["image_prompt"])
            except Exception:  # noqa: BLE001
                bg = None
        result.append(render_slide(slide, bg_image_bytes=bg))
    return result
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd services/content
.venv/bin/pytest tests/test_instagram_image_render.py -v
```

Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/instagram_image_render.py \
        services/content/tests/test_instagram_image_render.py
git commit -m "feat(worker): 인스타그램 캐러셀 Pillow 렌더러 추가 (1080×1080 JPEG)"
```

---

### Task 4: carousel API 엔드포인트

**Files:**
- Modify: `workers/api/src/routes/content_jobs.ts`

- [ ] **Step 1: 테스트 추가**

`workers/api/src/routes/content_jobs.test.ts`에 추가:

```typescript
describe("PUT /api/content/jobs/:id/carousel (service)", () => {
  it("base64 이미지 배열을 R2에 저장한다", async () => {
    const ck = await userCookie();
    // service JWT 생성
    const k = await ensureActiveKey(env.DB);
    const svcToken = await signAreaToken({ privateJwk: k.privateJwk, kid: k.kid,
      claims: { area: "content-worker" } });
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare(
      "INSERT INTO content_jobs (id,owner_sub,topic,platform,status,created_at,updated_at) VALUES (?,?,'t','instagram-image','running',?,?)"
    ).bind("jig1", "u1", now, now).run();
    const images = [btoa("fake-jpeg-1"), btoa("fake-jpeg-2")];
    const res = await SELF.fetch("https://example.com/api/content/jobs/jig1/carousel", {
      method: "PUT",
      headers: { authorization: `Bearer ${svcToken}`, "content-type": "application/json" },
      body: JSON.stringify({ images }),
    });
    expect(res.status).toBe(200);
    const obj0 = await env.R2.get("content/carousel/jig1/0.jpg");
    expect(obj0).not.toBeNull();
    const obj1 = await env.R2.get("content/carousel/jig1/1.jpg");
    expect(obj1).not.toBeNull();
  });
});

describe("GET /api/content/jobs/:id/carousel/:n (user)", () => {
  it("슬라이드 이미지를 스트리밍한다", async () => {
    const ck = await userCookie();
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare(
      "INSERT INTO content_jobs (id,owner_sub,topic,platform,status,created_at,updated_at) VALUES (?,?,'t','instagram-image','review',?,?)"
    ).bind("jig2", "u1", now, now).run();
    await env.R2.put("content/carousel/jig2/0.jpg", new Uint8Array([0xff, 0xd8, 0x01]), {
      httpMetadata: { contentType: "image/jpeg" },
    });
    const res = await SELF.fetch("https://example.com/api/content/jobs/jig2/carousel/0", {
      headers: { cookie: ck },
    });
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("image/jpeg");
  });

  it("존재하지 않는 슬라이드는 404", async () => {
    const ck = await userCookie();
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare(
      "INSERT INTO content_jobs (id,owner_sub,topic,platform,status,created_at,updated_at) VALUES (?,?,'t','instagram-image','review',?,?)"
    ).bind("jig3", "u1", now, now).run();
    const res = await SELF.fetch("https://example.com/api/content/jobs/jig3/carousel/0", {
      headers: { cookie: ck },
    });
    expect(res.status).toBe(404);
  });
});
```

`content_jobs.test.ts` 상단 import에 `signAreaToken` 추가:

```typescript
import { signSession, signAreaToken } from "@popory/auth";
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd workers/api
npm test -- content_jobs 2>&1 | grep -E "FAIL|carousel"
```

Expected: FAIL (carousel 엔드포인트 미존재)

- [ ] **Step 3: content_jobs.ts에 carousel 엔드포인트 추가**

`mountContentJobs` 함수 끝(마지막 `}` 직전)에 추가:

```typescript
  app.put("/api/content/jobs/:id/carousel", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT id FROM content_jobs WHERE id=?").bind(id).first<{ id: string }>();
    if (!row) return c.text("not found", 404);
    const body = (await c.req.json()) as { images: string[] };
    if (!Array.isArray(body.images) || body.images.length === 0) return c.text("images required", 400);
    for (let n = 0; n < body.images.length; n++) {
      const bytes = Uint8Array.from(atob(body.images[n]), (ch) => ch.charCodeAt(0));
      await c.env.R2.put(`content/carousel/${id}/${n}.jpg`, bytes, {
        httpMetadata: { contentType: "image/jpeg" },
      });
    }
    return c.json({ ok: true, count: body.images.length });
  });

  app.get("/api/content/jobs/:id/carousel/:n", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const n = c.req.param("n");
    const row = await c.env.DB.prepare("SELECT owner_sub FROM content_jobs WHERE id=?")
      .bind(id).first<{ owner_sub: string }>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    const obj = await c.env.R2.get(`content/carousel/${id}/${n}.jpg`);
    if (!obj) return c.text("not found", 404);
    return new Response(obj.body, { headers: { "content-type": "image/jpeg" } });
  });
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd workers/api
npm test 2>&1 | tail -10
```

Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add workers/api/src/routes/content_jobs.ts workers/api/src/routes/content_jobs.test.ts
git commit -m "feat(api): carousel 이미지 PUT/GET 엔드포인트 추가"
```

---

### Task 5: portal_client.py에 put_carousel 추가

**Files:**
- Modify: `services/content/popory_content/portal_client.py`

- [ ] **Step 1: put_carousel 메서드 추가**

`PortalClient` 클래스에 `put_binary` 메서드 다음에 추가:

```python
    def put_carousel(self, job_id: str, images: list[bytes]) -> Any:
        """JPEG bytes 리스트를 base64 인코딩해 carousel API에 업로드."""
        import base64
        b64_images = [base64.b64encode(img).decode() for img in images]
        return self._call("PUT", f"/api/content/jobs/{job_id}/carousel", body={"images": b64_images})
```

- [ ] **Step 2: 커밋**

```bash
git add services/content/popory_content/portal_client.py
git commit -m "feat(worker): PortalClient에 put_carousel 메서드 추가"
```

---

### Task 6: worker.py에 instagram-image 분기 추가

**Files:**
- Modify: `services/content/popory_content/worker.py`

- [ ] **Step 1: import 추가**

`worker.py` 상단에 추가:

```python
from popory_content.instagram_image_prompt import build_carousel_system_prompt, build_carousel_user_message
from popory_content.instagram_image_contract import parse_carousel
from popory_content.instagram_image_render import render_carousel
```

- [ ] **Step 2: generate_carousel 헬퍼 추가**

```python
def _generate_carousel(*, topic: str, sources: list, style_samples: list, job_id: str, slide_count: int):
    """Claude CLI로 캐러셀 슬라이드 배열 생성."""
    from popory_content.generate import run_claude_cli
    sp = build_carousel_system_prompt(style_samples, slide_count=slide_count)
    um = build_carousel_user_message(topic, sources)
    return run_claude_cli(system_prompt=sp, user_msg=um, parse=parse_carousel, job_id=job_id)
```

- [ ] **Step 3: run_once에 instagram-image 분기 추가**

`run_once` 함수에서 `elif platform == "shorts":` 블록 다음에 추가:

```python
        elif platform == "instagram-image":
            import json as _json
            params = {}
            if job.get("params_json"):
                try:
                    params = _json.loads(job["params_json"])
                except Exception:
                    params = {}
            slide_count = int(params.get("slide_count", 7))
            slide_count = max(3, min(10, slide_count))
            slides, meta = _generate_carousel(
                topic=job["topic"], sources=sources, style_samples=samples,
                job_id=job_id, slide_count=slide_count,
            )
            images = render_carousel(
                slides, image_fetcher=lambda p: _safe_image(client, p)
            )
            client.put_carousel(job_id, images)
            caption = meta.get("caption", "")
            _report(client, job_id, {"status": "review", "draft": caption, "meta": meta}, "review")
```

- [ ] **Step 4: 전체 Python 테스트 통과 확인**

```bash
cd services/content
.venv/bin/pytest -v 2>&1 | tail -20
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/worker.py
git commit -m "feat(worker): instagram-image 플랫폼 분기 추가 (캐러셀 생성·업로드)"
```

---

### Task 7: 포털 — 캐러셀 프리뷰 UI

**Files:**
- Create: `apps/portal/src/app/(authed)/content/[id]/CarouselPreview.tsx`
- Modify: `apps/portal/src/app/(authed)/content/[id]/page.tsx`

- [ ] **Step 1: CarouselPreview.tsx 작성**

```typescript
"use client";
// 인스타그램 캐러셀 슬라이드 이미지 그리드 프리뷰.
import { useState } from "react";
import { API_BASE } from "@/lib/env";

interface Props {
  jobId: string;
  slideCount: number;
  caption: string;
}

export function CarouselPreview({ jobId, slideCount, caption }: Props) {
  const [current, setCurrent] = useState(0);

  return (
    <div className="space-y-4">
      <div className="relative w-full max-w-sm mx-auto aspect-square rounded-lg overflow-hidden border border-popory-border bg-popory-card">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`${API_BASE}/api/content/jobs/${jobId}/carousel/${current}`}
          alt={`슬라이드 ${current + 1}`}
          className="w-full h-full object-cover"
        />
        <div className="absolute bottom-2 left-0 right-0 flex justify-center gap-1">
          {Array.from({ length: slideCount }, (_, i) => (
            <button
              key={i}
              onClick={() => setCurrent(i)}
              className={`h-1.5 w-1.5 rounded-full transition-colors ${
                i === current ? "bg-white" : "bg-white/40"
              }`}
            />
          ))}
        </div>
        {current > 0 && (
          <button onClick={() => setCurrent((c) => c - 1)}
            className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-1 text-white text-xs">
            ‹
          </button>
        )}
        {current < slideCount - 1 && (
          <button onClick={() => setCurrent((c) => c + 1)}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-1 text-white text-xs">
            ›
          </button>
        )}
      </div>
      <p className="text-xs text-popory-muted">{current + 1} / {slideCount}</p>
      {caption && (
        <details>
          <summary className="cursor-pointer text-xs text-popory-accent">캡션 보기</summary>
          <pre className="mt-2 whitespace-pre-wrap rounded-md border border-popory-border bg-popory-card p-3 text-xs text-popory-fg">{caption}</pre>
        </details>
      )}
    </div>
  );
}
```

- [ ] **Step 2: page.tsx에 instagram-image 분기 추가**

`apps/portal/src/app/(authed)/content/[id]/page.tsx` 상단 import에 추가:

```typescript
import { CarouselPreview } from "./CarouselPreview";
```

`JobDetail` 인터페이스에 추가:
```typescript
  params_json: string | null;
```

기존 `platform !== 'youtube'` 분기 앞에 instagram-image 분기 추가:

```typescript
        {(job.status === "review" || job.status === "done") && job.platform === "instagram-image" && (() => {
          let slideCount = 7;
          try {
            const p = JSON.parse(job.params_json ?? "{}") as { slide_count?: number };
            if (p.slide_count) slideCount = p.slide_count;
          } catch { /* 기본값 사용 */ }
          return (
            <div className="mt-8">
              <CarouselPreview jobId={job.id} slideCount={slideCount} caption={job.draft ?? ""} />
            </div>
          );
        })()}

        {(job.status === "review" || job.status === "done") && job.platform !== "youtube" && job.platform !== "shorts" && job.platform !== "instagram-image" && (
```

- [ ] **Step 3: 빌드 확인**

```bash
cd apps/portal
npx tsc --noEmit 2>&1 | head -20
```

Expected: 오류 없음.

- [ ] **Step 4: 커밋**

```bash
git add apps/portal/src/app/\(authed\)/content/\[id\]/CarouselPreview.tsx \
        apps/portal/src/app/\(authed\)/content/\[id\]/page.tsx
git commit -m "feat(portal): 인스타그램 캐러셀 프리뷰 UI 추가"
```

---

### Task 8: prod 배포

- [ ] **Step 1: API Worker 배포**

```bash
cd workers/api
wrangler deploy --env prod
```

- [ ] **Step 2: 워커 재시작**

```bash
launchctl kickstart -k gui/$(id -u)/com.popory.content-worker
```

- [ ] **Step 3: Portal 배포**

```bash
cd apps/portal
npm run build:cf
wrangler pages deploy .vercel/output/static --project-name popory-portal --branch main
```

- [ ] **Step 4: 동작 확인**

주제 그룹에서 "인스타 이미지" idle 카드 → "생성 시작" → (워커 처리) → review → "결과 보기" → 캐러셀 슬라이드 프리뷰 확인. `‹ ›` 버튼으로 슬라이드 이동 확인.
