<!-- 유튜브 임팩트 썸네일(전용 후킹 카피 + 전용 배경) 생성·적용 구현 계획. -->

# 유튜브 임팩트 썸네일 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 영상·쇼츠에 전용 후킹 카피를 크게 얹은 커스텀 썸네일을 자동 생성해 유튜브에 설정한다.

**Architecture:** claude 메타에 `thumbnail_copy`·`thumbnail_image_prompt` 추가 → 워커가 `video.render_thumbnail`(imagegen 배경 + Pillow 큰 카피)로 JPEG 생성 → `PUT /api/content/jobs/:id/thumbnail`(R2) → 업로드 후 워커가 `GET thumbnail` + `youtube_upload.set_thumbnail`(thumbnails.set). 모두 베스트 에포트(실패해도 업로드 유지).

**Tech Stack:** Python 3.11(Pillow, requests, pytest) · TypeScript(Hono, vitest, cloudflare:test) · YouTube Data API.

## Global Constraints

- 신규 소스 파일 없음(모두 기존 파일 수정). 마이그레이션 없음(썸네일은 R2 `content/thumb/{id}.jpg`만).
- 한국어 마침표 종결, 콜론 금지(주석·로그).
- 썸네일 크기: 영상 16:9 = 1280×720, 쇼츠 9:16 = 1080×1920. JPEG.
- `thumbnail_image_prompt`는 이미지 안에 텍스트 없음(카피는 Pillow가 얹음). `thumbnail_copy`는 16자 내외 후킹.
- 베스트 에포트: 썸네일 렌더/PUT 실패는 영상 생성 흐름 유지(로그만). set_thumbnail 실패는 업로드 done 유지(로그만, 별도 try/except).
- 구 콘텐츠(메타에 썸네일 키 없음) → render_thumbnail None → 생략(무해).
- 기존 상수 재사용: `FONT_PATH`, `BG`, `_cover`, `LANDSCAPE_*`/`PORTRAIT_*`는 video.py에 이미 있음.
- 외부 유튜브 호출(thumbnails.set)은 e2e — 단위 테스트는 requests 모킹.

---

### Task 1: 메타 2키 지시 + `render_thumbnail`

**Files:**
- Modify: `services/content/popory_content/video_prompt.py` (video·shorts 메타 지시)
- Modify: `services/content/popory_content/video.py` (`render_thumbnail`)
- Test: `services/content/tests/test_video_thumbnail.py` (신규 테스트 파일 — Korean 헤더)

**Interfaces:**
- Produces: `render_thumbnail(copy: str | None, image_prompt: str | None, out_jpg: Path, portrait: bool = False, image_fetcher=None) -> Path | None`. copy/image_prompt 없으면 None. 있으면 지정 크기 JPEG 생성 후 경로 반환.
- video/shorts 시스템 프롬프트의 `<video_meta>` JSON에 `thumbnail_copy`·`thumbnail_image_prompt` 포함.

- [ ] **Step 1: render_thumbnail 테스트 작성(실패)**

`services/content/tests/test_video_thumbnail.py`:

```python
# 유튜브 썸네일 렌더(전용 카피·배경) 단위 테스트.
import io
from pathlib import Path
from PIL import Image
from popory_content import video


def _png(color=(20, 40, 80)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (16, 9), color).save(b, format="PNG")
    return b.getvalue()


def test_none_when_missing_copy_or_prompt(tmp_path):
    assert video.render_thumbnail(None, "bg", tmp_path / "t.jpg", image_fetcher=lambda p: _png()) is None
    assert video.render_thumbnail("후킹", None, tmp_path / "t.jpg", image_fetcher=lambda p: _png()) is None


def test_landscape_1280x720(tmp_path):
    out = video.render_thumbnail("인생을 바꾼 한 문장", "cinematic library", tmp_path / "t.jpg", portrait=False, image_fetcher=lambda p: _png())
    assert out is not None
    im = Image.open(out)
    assert im.size == (1280, 720)
    assert im.format == "JPEG"


def test_portrait_1080x1920_with_solid_fallback(tmp_path):
    # image_fetcher가 None 반환 → 단색 폴백 경로
    out = video.render_thumbnail("강렬한 한 줄", "cinematic", tmp_path / "t.jpg", portrait=True, image_fetcher=lambda p: None)
    assert out is not None
    im = Image.open(out)
    assert im.size == (1080, 1920)


def test_broken_image_bytes_falls_back(tmp_path):
    out = video.render_thumbnail("카피", "cinematic", tmp_path / "t.jpg", image_fetcher=lambda p: b"not-an-image")
    assert out is not None
    assert Image.open(out).size == (1280, 720)
```

- [ ] **Step 2: 실패 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_video_thumbnail.py -q`
Expected: FAIL — `render_thumbnail` 없음.

- [ ] **Step 3: render_thumbnail 구현**

`video.py` 상단 상수 근처에 썸네일 크기 추가.

```python
THUMB_W, THUMB_H = 1280, 720
THUMB_PW, THUMB_PH = 1080, 1920
```

`_render_headline_png` 다음 등 적절한 위치에 함수 추가.

```python
def render_thumbnail(copy: str | None, image_prompt: str | None, out_jpg: Path,
                     portrait: bool = False, image_fetcher=None) -> Path | None:
    """전용 카피·배경으로 유튜브 썸네일 JPEG 생성. copy/image_prompt 없으면 None."""
    if not copy or not image_prompt:
        return None
    w, h = (THUMB_PW, THUMB_PH) if portrait else (THUMB_W, THUMB_H)
    img = None
    if image_fetcher is not None:
        try:
            b = image_fetcher(image_prompt)
            if b:
                img = _cover(Image.open(BytesIO(b)).convert("RGB"), w, h)
        except Exception:  # noqa: BLE001 — 깨진/실패 이미지는 단색 폴백
            img = None
    if img is None:
        img = Image.new("RGB", (w, h), BG)
    # 전체 어두운 스크림으로 카피 가독성 확보
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 90))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)
    font_size = 130 if portrait else 150
    font = ImageFont.truetype(FONT_PATH, font_size)
    wrap = 8 if portrait else 9
    lines = "\n".join(textwrap.wrap(copy, width=wrap)) or " "
    d.multiline_text((w / 2, h / 2), lines, font=font, fill=(255, 255, 255), anchor="mm",
                     align="center", spacing=16, stroke_width=8, stroke_fill=(0, 0, 0))
    img.save(out_jpg, format="JPEG", quality=85)
    return out_jpg
```

- [ ] **Step 4: 통과 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_video_thumbnail.py -q`
Expected: PASS (4).

- [ ] **Step 5: 프롬프트 메타 2키 지시 추가**

`video_prompt.py`의 **video** 시스템 프롬프트 `<video_meta>` JSON 예시(현재 `{{"title": "...", "description": "...", "tags": ["..."]}}`)를 확장하고 가이드 한 줄 추가.

```
{{"title": "...", "description": "...", "tags": ["..."], "thumbnail_copy": "...", "thumbnail_image_prompt": "english cinematic background, no text"}}
```
가이드 라인(메타 설명부에 추가): `thumbnail_copy 는 썸네일에 크게 띄울 후킹 한 줄(16자 내외, 제목보다 짧고 강하게). thumbnail_image_prompt 는 썸네일 배경용 영어 묘사(시네마틱·고대비, 이미지 안에 글자 없음).`

**shorts** 시스템 프롬프트의 `<video_meta>`에도 동일하게 두 키 + 가이드 추가(쇼츠 카피는 더 짧게 10자 내외 권장 문구).

`build_video_system_prompt()`·`build_shorts_system_prompt()` 출력에 `"thumbnail_copy"` 문자열이 포함되는지 확인하는 테스트를 `test_video_thumbnail.py`에 추가.

```python
from popory_content.video_prompt import build_video_system_prompt, build_shorts_system_prompt

def test_prompts_instruct_thumbnail_keys():
    assert "thumbnail_copy" in build_video_system_prompt([], scene_count=8)
    assert "thumbnail_image_prompt" in build_video_system_prompt([], scene_count=8)
    assert "thumbnail_copy" in build_shorts_system_prompt([], scene_count=8)
```
(시그니처는 `video_prompt.py`의 실제 정의에 맞춰 인자 조정 — 파일을 읽고 맞춘다.)

- [ ] **Step 6: 전체 통과 + 커밋**

Run: `cd services/content && .venv/bin/python -m pytest -q` → 전체 PASS.

```bash
git add services/content/popory_content/video_prompt.py services/content/popory_content/video.py services/content/tests/test_video_thumbnail.py
git commit -m "feat(content): 썸네일 메타 2키 지시 + render_thumbnail(전용 카피·배경)"
```

---

### Task 2: 썸네일 R2 PUT/GET 엔드포인트

**Files:**
- Modify: `workers/api/src/routes/content_jobs.ts`
- Test: `workers/api/src/routes/content_jobs.test.ts`

**Interfaces:**
- Consumes: 없음.
- Produces:
  - `PUT /api/content/jobs/:id/thumbnail` (서비스, area content-worker) → R2 `content/thumb/{id}.jpg`(contentType image/jpeg), 204.
  - `GET /api/content/jobs/:id/thumbnail` → R2 바이트(image/jpeg), 없으면 404. 인증은 기존 `GET /:id/video`와 동일 방식(서비스 JWT 허용).

- [ ] **Step 1: 테스트 작성(실패)**

`content_jobs.test.ts`에 추가(serviceToken area content-worker 헬퍼 사용; beforeEach 그대로). 기존 `/:id/video` PUT/GET 테스트가 있으면 그 패턴을 따른다.

```typescript
describe("썸네일 PUT/GET", () => {
  it("서비스가 PUT 후 GET으로 동일 바이트 반환", async () => {
    const tok = await serviceToken();
    const bytes = new Uint8Array([0xff, 0xd8, 0xff, 0x01, 0x02]); // JPEG 매직 흉내
    const put = await SELF.fetch("https://e.com/api/content/jobs/jthumb/thumbnail", {
      method: "PUT", headers: { authorization: `Bearer ${tok}`, "content-type": "image/jpeg" }, body: bytes,
    });
    expect(put.status).toBe(204);
    const get = await SELF.fetch("https://e.com/api/content/jobs/jthumb/thumbnail", { headers: { authorization: `Bearer ${tok}` } });
    expect(get.status).toBe(200);
    expect(new Uint8Array(await get.arrayBuffer())).toEqual(bytes);
  });
  it("없으면 404", async () => {
    const tok = await serviceToken();
    const get = await SELF.fetch("https://e.com/api/content/jobs/none/thumbnail", { headers: { authorization: `Bearer ${tok}` } });
    expect(get.status).toBe(404);
  });
  it("PUT 미서비스 401", async () => {
    const put = await SELF.fetch("https://e.com/api/content/jobs/x/thumbnail", { method: "PUT", headers: { "content-type": "image/jpeg" }, body: new Uint8Array([1]) });
    expect(put.status).toBe(401);
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd workers/api && npx vitest run src/routes/content_jobs.test.ts -t "썸네일"`
Expected: FAIL.

- [ ] **Step 3: 구현**

`content_jobs.ts`의 `PUT /api/content/jobs/:id/video` 핸들러를 찾아 그 바로 뒤에 썸네일 핸들러를 추가(동일 인증·패턴, contentType만 image/jpeg, 키만 `content/thumb/{id}.jpg`). GET도 `/:id/video` GET과 동일 인증 방식으로.

```typescript
  app.put("/api/content/jobs/:id/thumbnail", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const id = c.req.param("id");
    const body = await c.req.arrayBuffer();
    await c.env.R2.put(`content/thumb/${id}.jpg`, body, { httpMetadata: { contentType: "image/jpeg" } });
    return c.body(null, 204);
  });

  app.get("/api/content/jobs/:id/thumbnail", async (c) => {
    // 인증은 /:id/video GET과 동일 방식으로(서비스 JWT 허용). 해당 핸들러의 인증 코드를 그대로 복제한다.
    const id = c.req.param("id");
    const obj = await c.env.R2.get(`content/thumb/${id}.jpg`);
    if (!obj) return c.text("not found", 404);
    return new Response(obj.body, { headers: { "content-type": "image/jpeg" } });
  });
```
주의: `WORKER_AREA` 상수가 content_jobs.ts에 있는지 확인(없으면 `"content-worker"` 리터럴). `GET /:id/video` 핸들러를 읽어 인증 처리(서비스/사용자 허용 범위)를 동일하게 맞춘다 — video GET이 별도 인증 없이 R2를 반환하면 thumbnail GET도 동일하게, 서비스 가드가 있으면 동일 가드 적용.

- [ ] **Step 4: 통과 + 회귀 + 커밋**

Run: `cd workers/api && npx vitest run` → 전체 PASS.

```bash
git add workers/api/src/routes/content_jobs.ts workers/api/src/routes/content_jobs.test.ts
git commit -m "feat(content): 썸네일 R2 PUT/GET 엔드포인트"
```

---

### Task 3: set_thumbnail + 워커 배선(생성 후 PUT, 업로드 후 set)

**Files:**
- Modify: `services/content/popory_content/youtube_upload.py` (`set_thumbnail`)
- Modify: `services/content/popory_content/worker.py` (생성부 thumbnail PUT, 업로드부 set_thumbnail)
- Test: `services/content/tests/test_youtube_upload.py`(있으면) 또는 `test_video_thumbnail.py`에 set_thumbnail·워커 베스트에포트 테스트

**Interfaces:**
- Consumes: `render_thumbnail`(Task 1), `PUT/GET /:id/thumbnail`(Task 2).
- Produces: `set_thumbnail(access_token: str, video_id: str, jpg_bytes: bytes) -> None` (실패 시 UploadError). 워커 youtube/shorts 생성부가 썸네일 PUT, `run_upload_once`가 업로드 후 set_thumbnail(베스트 에포트).

- [ ] **Step 1: set_thumbnail 테스트 작성(실패)**

```python
# test_video_thumbnail.py 에 추가(또는 test_youtube_upload.py)
import responses
import pytest
from popory_content.youtube_upload import set_thumbnail, UploadError

@responses.activate
def test_set_thumbnail_ok():
    responses.add(responses.POST, "https://www.googleapis.com/upload/youtube/v3/thumbnails/set", json={"items": [{}]}, status=200)
    set_thumbnail("tok", "vid123", b"\xff\xd8\xff")  # 예외 없으면 통과

@responses.activate
def test_set_thumbnail_403_raises():
    responses.add(responses.POST, "https://www.googleapis.com/upload/youtube/v3/thumbnails/set", json={"error": {}}, status=403)
    with pytest.raises(UploadError):
        set_thumbnail("tok", "vid123", b"\xff\xd8\xff")
```

- [ ] **Step 2: 실패 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_video_thumbnail.py -q -k set_thumbnail`
Expected: FAIL — `set_thumbnail` 없음.

- [ ] **Step 3: set_thumbnail 구현**

`youtube_upload.py`에 추가(기존 `UploadError`·`requests` 재사용).

```python
THUMBNAIL_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"


def set_thumbnail(access_token: str, video_id: str, jpg_bytes: bytes) -> None:
    """업로드된 영상에 커스텀 썸네일 설정. 채널 미인증 등 실패 시 UploadError."""
    resp = requests.post(
        f"{THUMBNAIL_URL}?videoId={video_id}",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "image/jpeg"},
        data=jpg_bytes, timeout=60,
    )
    if resp.status_code not in (200, 201):
        raise UploadError(f"thumbnail {resp.status_code}: {resp.text[:200]}")
```

- [ ] **Step 4: 통과 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_video_thumbnail.py -q -k set_thumbnail` → PASS.

- [ ] **Step 5: 워커 배선 — 생성부 PUT thumbnail**

`worker.py` import에 `render_thumbnail` 추가(`from popory_content.video import make_video, VideoError, render_thumbnail`). 헬퍼 추가.

```python
def _maybe_put_thumbnail(client, job_id: str, meta: dict, portrait: bool) -> None:
    """메타에 썸네일 키가 있으면 렌더 후 PUT. 실패는 로그만(영상 흐름 유지)."""
    try:
        out = Path("/tmp") / f"thumb_{job_id}.jpg"
        res = render_thumbnail(meta.get("thumbnail_copy"), meta.get("thumbnail_image_prompt"), out,
                               portrait=portrait, image_fetcher=lambda p: _safe_image(client, p, job_id))
        if res:
            client.put_binary(f"/api/content/jobs/{job_id}/thumbnail", data=res.read_bytes(), content_type="image/jpeg")
    except Exception as e:  # noqa: BLE001
        append_log(LOGS_DIR, {"worker": "content", "status": "thumbnail_failed", "job": job_id, "error": str(e)[:200]})
```
run_once의 youtube 분기 `_finalize_video(...)` 직전에 `_maybe_put_thumbnail(client, job_id, meta, portrait=False)`, shorts 분기에 `_maybe_put_thumbnail(client, job_id, meta, portrait=True)` 추가.

- [ ] **Step 6: 워커 배선 — 업로드부 set_thumbnail(베스트 에포트)**

`worker.py` import에 `set_thumbnail` 추가(`from popory_content.youtube_upload import upload, upload_caption, set_thumbnail` 형태). `run_upload_once`의 `_upload_captions(...)` 다음, `youtube-result done` patch 전에 추가.

```python
        try:
            thumb = client.get_bytes(f"/api/content/jobs/{job_id}/thumbnail")
            if thumb:
                set_thumbnail(data["access_token"], video_id, thumb)
        except Exception as e:  # noqa: BLE001 — 썸네일 실패는 업로드 done 유지
            append_log(LOGS_DIR, {"worker": "content", "status": "thumbnail_set_failed", "job": job_id, "error": str(e)[:200]})
```
(`client.get_bytes`는 404 시 PortalError를 던지므로 이 try가 흡수 — 썸네일 없으면 조용히 건너뜀.)

- [ ] **Step 7: 워커 베스트에포트 테스트**

`run_upload_once`에서 set_thumbnail이 실패해도 youtube-result done이 유지되는지 검증. `test_worker.py`에 추가(기존 FakeClient/monkeypatch 패턴 사용; `upload`·`set_thumbnail`·`_upload_captions` monkeypatch).

```python
def test_upload_thumbnail_failure_keeps_done(monkeypatch):
    from popory_content import worker
    monkeypatch.setattr(worker, "upload", lambda *a, **k: "vid1")
    monkeypatch.setattr(worker, "_upload_captions", lambda *a, **k: None)
    def boom(*a, **k): raise RuntimeError("thumb 403")
    monkeypatch.setattr(worker, "set_thumbnail", boom)
    patched = []
    class C:
        def post(self, path, *, json=None): return {"job_id": "j1", "access_token": "t", "title": "t"}
        def get_bytes(self, path): return b"\xff\xd8\xff"
        def patch(self, path, *, json): patched.append((path, json)); return {}
    assert worker.run_upload_once(C()) is True
    assert any("youtube-result" in p and j.get("status") == "done" for p, j in patched)
```
(claim-upload 응답 형태·get_bytes(video) 호출이 있으면 FakeClient를 그에 맞게 보강 — `run_upload_once` 본문을 읽고 필요한 메서드/반환을 맞춘다.)

- [ ] **Step 8: 전체 통과 + 커밋**

Run: `cd services/content && .venv/bin/python -m pytest -q` → 전체 PASS.

```bash
git add services/content/popory_content/youtube_upload.py services/content/popory_content/worker.py services/content/tests/test_video_thumbnail.py services/content/tests/test_worker.py
git commit -m "feat(content): 썸네일 set_thumbnail + 워커 배선(생성 PUT·업로드 set, 베스트에포트)"
```

---

## 배포·셋업 (구현 후 1회)

- [ ] 워커 재배포(thumbnail PUT/GET 엔드포인트). `set -a; source ~/.zshenv; set +a` 후 `pnpm --filter @popory/api exec wrangler deploy --env prod --config ../../infra/wrangler/api.toml`.
- [ ] 로컬 워커 코드 반영(editable install — 재시작 불필요, 다음 생성/업로드부터 적용).
- [ ] 휴먼 e2e. 영상/쇼츠 1건 생성 → R2 `content/thumb/{id}.jpg` 저장 확인 → 유튜브 업로드 후 스튜디오에서 큰 카피 썸네일 적용 확인. 채널 미인증이면 `thumbnail_set_failed` 로그 + 기본 프레임 썸네일(영상은 정상).

## 롤백

워커 이전 버전 복원. 썸네일 엔드포인트·R2 객체는 무해 잔존. set_thumbnail 미호출 시 기본 프레임 썸네일로 복귀.
