# 영상 배경 이미지 신뢰성·가시화 + 재생성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 영상 장면 배경 이미지 생성 실패를 재시도로 흡수하고, 남는 실패를 로그·작업 상태로 가시화하며, 배경 없는 기존 영상을 작업별 "재생성" 버튼으로 다시 생성한다.

**Architecture:** 콘텐츠 워커(`services/content`)의 이미지 페치를 재시도+로그로 바꾸고, `render_video`가 누락 이미지 수를 집계해 워커가 status(failed/review)를 결정한다. `parse_video`가 `image_prompt`를 필수화한다. 포털 API에 `regenerate` 엔드포인트와 작업 상세에 재생성 버튼을 추가한다.

**Tech Stack:** Python(pytest, pytest-mock) 콘텐츠 워커, Cloudflare Workers(Hono)+D1, Next.js 14(edge), Vitest.

**Base:** 브랜치 `feat/video-background-reliability` (현재 `main` 0780040 + 스펙 갱신 1커밋). 2026-06-13 영상 품질 개선 머지가 반영된 `video.py`(render_video 176~232, make_video 235~) 기준.

---

## File Structure

| 파일 | 책임 | 생성/수정 |
|---|---|---|
| `services/content/popory_content/video_contract.py` | `parse_video` image_prompt 필수 | 수정 |
| `services/content/tests/test_video_contract.py` | 기존 갱신 + 신규 | 수정 |
| `services/content/popory_content/video.py` | render_video/make_video 누락 집계 반환 | 수정 |
| `services/content/tests/test_video.py` | 집계 테스트 | 수정 |
| `services/content/popory_content/worker.py` | `_safe_image` 재시도·로그 + `_finalize_video` + 영상 분기 | 수정 |
| `services/content/tests/test_worker.py` | 재시도·분기 테스트 | 수정 |
| `workers/api/src/routes/content_jobs.ts` | `regenerate` 엔드포인트 | 수정 |
| `workers/api/src/routes/content_jobs.test.ts` | regenerate 테스트 | 수정 |
| `apps/portal/src/app/(authed)/content/[id]/RegenerateButton.tsx` | 재생성 버튼 | 생성 |
| `apps/portal/src/app/(authed)/content/[id]/page.tsx` | 버튼·경고 배지 | 수정 |

pytest 실행: `cd /Users/daegong/projects/popory/services/content && .venv/bin/python -m pytest`. vitest: `cd /Users/daegong/projects/popory/workers/api && npx vitest run`. portal tsc: `cd /Users/daegong/projects/popory/apps/portal && npx tsc --noEmit`.

---

## Task 1: parse_video — image_prompt 필수화

**Files:**
- Modify: `services/content/popory_content/video_contract.py`
- Modify: `services/content/tests/test_video_contract.py`

- [ ] **Step 1: 기존 테스트 갱신 + 실패 테스트 추가**

`tests/test_video_contract.py`의 `test_parses_scenes_and_meta`는 현재 `scenes[1]`에 image_prompt가 없고 `assert "image_prompt" not in scenes[1]  # image_prompt 없는 장면도 허용`로 "허용"을 검증한다. 이 동작을 뒤집으므로 수정한다.

(1) 픽스처의 `scenes_json` 둘째 장면에 `image_prompt`를 추가하고, (2) "허용" 단언을 교체한다. `test_parses_scenes_and_meta` 본문을 다음으로 교체:

```python
def test_parses_scenes_and_meta():
    text = """잡담
<scenes_json>
[{"caption": "사피엔스란", "narration": "인류의 역사를 다룬 책입니다.", "image_prompt": "ancient humans by fire, cinematic"}, {"caption": "핵심 메시지", "narration": "허구가 협력을 낳았습니다.", "image_prompt": "abstract cooperation, no text"}]
</scenes_json>
<video_meta>
{"title": "사피엔스 요약", "description": "책 요약 영상", "tags": ["책", "사피엔스"]}
</video_meta>
끝"""
    scenes, meta = parse_video(text)
    assert len(scenes) == 2
    assert scenes[0]["caption"] == "사피엔스란"
    assert scenes[1]["narration"].endswith("협력을 낳았습니다.")
    assert meta["title"] == "사피엔스 요약"
    assert meta["tags"] == ["책", "사피엔스"]
    assert scenes[0]["image_prompt"].startswith("ancient")
    assert scenes[1]["image_prompt"]  # 모든 장면에 image_prompt 필수
```

파일 끝에 신규 테스트 추가:

```python
def test_missing_image_prompt_raises():
    text = """<scenes_json>
[{"caption": "장면", "narration": "내레이션 있음."}]
</scenes_json>
<video_meta>
{"title": "t", "description": "d", "tags": []}
</video_meta>"""
    with pytest.raises(ContractError):
        parse_video(text)
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && .venv/bin/python -m pytest tests/test_video_contract.py -q`
Expected: `test_missing_image_prompt_raises` FAIL(현재는 image_prompt 없어도 통과하므로 raises 안 함).

- [ ] **Step 3: parse_video에 image_prompt 검증 추가**

`video_contract.py`의 장면 검증 루프(현재):
```python
    for s in scenes:
        if not s.get("caption") or not s.get("narration"):
            raise ContractError("scene 에 caption/narration 누락")
    return scenes, meta
```
를 다음으로 변경:
```python
    for s in scenes:
        if not s.get("caption") or not s.get("narration"):
            raise ContractError("scene 에 caption/narration 누락")
        if not s.get("image_prompt"):
            raise ContractError("scene 에 image_prompt 누락")
    return scenes, meta
```

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/services/content && .venv/bin/python -m pytest tests/test_video_contract.py -q`
Expected: PASS (기존 갱신 + 신규 전부).

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory && git add services/content/popory_content/video_contract.py services/content/tests/test_video_contract.py && git commit -m "feat(content): parse_video image_prompt 필수화"
```

---

## Task 2: render_video/make_video — 누락 이미지 집계 반환

**Files:**
- Modify: `services/content/popory_content/video.py`
- Modify: `services/content/tests/test_video.py`

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_video.py` 파일 끝에 추가. ffmpeg/say는 monkeypatch로 우회하고, image_fetcher가 일부 장면에 None을 반환하게 해 집계를 검증한다.

```python
def test_render_video_counts_missing_images(monkeypatch, tmp_path):
    from popory_content import video
    monkeypatch.setattr(video, "FONT_PATH", str(tmp_path))  # 폰트 존재 체크 통과
    monkeypatch.setattr(video, "synthesize", lambda text, voice=None: b"AUDIO")
    monkeypatch.setattr(video, "_run", lambda cmd: None)
    monkeypatch.setattr(video, "_duration", lambda path: 1.0)
    monkeypatch.setattr(video, "_render_card", lambda *a, **k: None)
    monkeypatch.setattr(video, "_master_audio", lambda src, out, bgm: None)
    monkeypatch.setattr(video, "_pick_bgm", lambda d, j: None)
    monkeypatch.setattr(video, "_xfade_graph", lambda durs, td=0.4: ("", "v", "a"))
    scenes = [
        {"caption": "a", "narration": "n1", "image_prompt": "ok one"},
        {"caption": "b", "narration": "n2", "image_prompt": "fail two"},
        {"caption": "c", "narration": "n3", "image_prompt": "fail three"},
        {"caption": "d", "narration": "n4"},  # image_prompt 없음 → total 미포함
    ]
    fetcher = lambda p: b"IMG" if "ok" in p else None
    out, missing, total = video.render_video(scenes, job_id="vbtest", image_fetcher=fetcher)
    assert total == 3   # image_prompt 있는 장면 수
    assert missing == 2 # 'fail' 2개
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && .venv/bin/python -m pytest tests/test_video.py::test_render_video_counts_missing_images -q`
Expected: FAIL — `render_video`가 `Path`만 반환해 `out, missing, total = ...` 언패킹에서 ValueError.

- [ ] **Step 3: render_video 집계 + 반환 변경**

`video.py`의 `render_video` 시그니처(현재 `-> Path`)를 `-> tuple[Path, int, int]`로 변경. 함수 시작 `clips: list[Path] = []` 다음 줄에 카운터 추가:
```python
    clips: list[Path] = []
    images_missing = 0
    images_total = 0
```
장면 루프에서 `bg_bytes`를 정한 직후(try/except 블록 다음, `audio_bytes = synthesize(...)` 전)에 집계 추가:
```python
        if prompt:
            images_total += 1
            if bg_bytes is None:
                images_missing += 1
```
함수 끝 `return out`을 변경:
```python
    return out, images_missing, images_total
```

- [ ] **Step 4: make_video 반환 확장**

`video.py`의 `make_video` 반환 타입 주석을 `-> tuple[Path, list[dict[str, Any]], dict[str, Any], int, int]`로 바꾸고, 본문의 render_video 호출·반환을 변경. 현재:
```python
    mp4 = render_video(scenes, job_id=job_id, image_fetcher=image_fetcher, voice=voice, portrait=portrait)
    return mp4, scenes, meta
```
를:
```python
    mp4, img_missing, img_total = render_video(scenes, job_id=job_id, image_fetcher=image_fetcher, voice=voice, portrait=portrait)
    return mp4, scenes, meta, img_missing, img_total
```

- [ ] **Step 5: 통과 + 회귀 확인**

Run: `cd /Users/daegong/projects/popory/services/content && .venv/bin/python -m pytest tests/test_video.py -q`
Expected: 신규 PASS, 기존 video 테스트도 PASS(`_render_card` 테스트는 영향 없음; render_video 스모크 테스트가 있으면 5-튜플 언패킹 필요 — 있으면 Step 6에서 처리).

- [ ] **Step 6: 기존 render_video 호출처 점검**

Run: `grep -rn "render_video(" services/content/`
기존 테스트나 코드에서 `x = render_video(...)`로 단일 반환을 기대하는 곳이 있으면 5-튜플… 아니라 3-튜플 언패킹으로 고친다(`make_video` 외에 직접 호출은 test_video.py 스모크뿐일 가능성). 해당 호출을 `out, _, _ = render_video(...)`로 수정.
Run: `cd /Users/daegong/projects/popory/services/content && .venv/bin/python -m pytest tests/test_video.py -q` → PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/daegong/projects/popory && git add services/content/popory_content/video.py services/content/tests/test_video.py && git commit -m "feat(content): render_video/make_video 누락 이미지 집계 반환"
```

---

## Task 3: worker — _safe_image 재시도·로그 + _finalize_video + 영상 분기

**Files:**
- Modify: `services/content/popory_content/worker.py`
- Modify: `services/content/tests/test_worker.py`

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_worker.py`의 `FakeClient`에 `put_binary`를 추가하고(영상 분기가 호출), 재시도·분기 테스트를 더한다. `FakeClient.__init__`에 `self.uploaded = []`를 추가하고 메서드 추가:
```python
    def put_binary(self, path, *, data, content_type):
        self.uploaded.append(path)
        return {"ok": True}
```
파일 끝에 테스트 추가:
```python
def test_safe_image_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    calls = {"n": 0}

    class C:
        def post_for_bytes(self, path, *, json):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("boom")
            return b"img"

    assert worker._safe_image(C(), "p") == b"img"
    assert calls["n"] == 3


def test_safe_image_all_fail_returns_none(monkeypatch):
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)

    class C:
        def post_for_bytes(self, path, *, json):
            raise RuntimeError("boom")

    assert worker._safe_image(C(), "p") is None


class _Mp4:
    def read_bytes(self):
        return b""


def test_youtube_most_images_failed_reports_failed(monkeypatch):
    monkeypatch.setattr(worker, "make_video",
                        lambda **kw: (_Mp4(), [{"caption": "c", "narration": "n"}], {"title": "t"}, 5, 6))
    client = FakeClient({"job": {"id": "j1", "topic": "t", "platform": "youtube",
                                 "params_json": '{"length":"5","voice":"male","image_style":"photo"}'},
                         "sources": [], "style_samples": []})
    assert worker.run_once(client) is True
    result = [p for p in client.patched if p[0].endswith("/result")][-1]
    assert result[1]["status"] == "failed"
    assert "배경 이미지 생성 실패" in result[1]["error"]


def test_youtube_few_images_failed_reports_review(monkeypatch):
    monkeypatch.setattr(worker, "make_video",
                        lambda **kw: (_Mp4(), [{"caption": "c", "narration": "n"}], {"title": "t"}, 1, 6))
    client = FakeClient({"job": {"id": "j2", "topic": "t", "platform": "youtube",
                                 "params_json": '{"length":"5","voice":"male","image_style":"photo"}'},
                         "sources": [], "style_samples": []})
    assert worker.run_once(client) is True
    result = [p for p in client.patched if p[0].endswith("/result")][-1]
    assert result[1]["status"] == "review"
    assert result[1]["meta"]["images_missing"] == 1
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && .venv/bin/python -m pytest tests/test_worker.py -q`
Expected: FAIL — `_safe_image`가 재시도 안 함(`calls["n"]==1`), 영상 분기가 5-튜플 언패킹 안 됨(현재 3-튜플 기대 → ValueError) 및 failed 분기 없음.

- [ ] **Step 3: _safe_image 재시도+로그**

`worker.py`의 `_safe_image`(현재):
```python
def _safe_image(client, prompt: str):
    """AI 이미지 1장. 실패하면 None(단색 폴백)."""
    try:
        return client.post_for_bytes("/api/content/ai-image", json={"prompt": prompt})
    except Exception:  # noqa: BLE001
        return None
```
를 다음으로 교체(상단 상수도 추가):
```python
IMAGE_MAX_ATTEMPTS = 3
IMAGE_BACKOFF = [2, 5]


def _safe_image(client, prompt: str):
    """AI 이미지 1장. 일시 실패는 재시도, 최종 실패는 로그+None(단색 폴백)."""
    last = ""
    for attempt in range(1, IMAGE_MAX_ATTEMPTS + 1):
        try:
            return client.post_for_bytes("/api/content/ai-image", json={"prompt": prompt})
        except Exception as e:  # noqa: BLE001
            last = str(e)[:200]
            if attempt < IMAGE_MAX_ATTEMPTS:
                time.sleep(IMAGE_BACKOFF[attempt - 1])
    append_log(LOGS_DIR, {"worker": "content", "status": "image_failed", "error": last})
    return None
```
(`time`·`append_log`·`LOGS_DIR`는 worker.py에 이미 import/정의됨.)

- [ ] **Step 4: _finalize_video 헬퍼 추가**

`_safe_image` 근처(같은 파일)에 헬퍼와 상수 추가:
```python
IMAGE_FAIL_RATIO = 0.5


def _finalize_video(client, job_id, script, meta, img_missing, img_total):
    """누락 이미지 비율로 status 결정. 대부분 실패면 failed, 일부면 review+경고."""
    if img_total > 0 and img_missing / img_total >= IMAGE_FAIL_RATIO:
        _report(client, job_id, {
            "status": "failed", "draft": script, "meta": meta,
            "error": f"배경 이미지 생성 실패 ({img_missing}/{img_total} 장면) — 재생성 필요",
        }, "failed")
    else:
        if img_missing:
            meta = {**meta, "images_missing": img_missing, "images_total": img_total}
        _report(client, job_id, {"status": "review", "draft": script, "meta": meta}, "review")
```

- [ ] **Step 5: youtube·shorts 분기 변경**

`worker.py` `run_once`의 youtube 분기(현재):
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
            client.put_binary(f"/api/content/jobs/{job_id}/video", data=mp4.read_bytes(), content_type="video/mp4")
            script = "\n\n".join(f"[{s['caption']}]\n{s['narration']}" for s in scenes)
            _report(client, job_id, {"status": "review", "draft": script, "meta": meta}, "review")
```
를:
```python
        if platform == "youtube":
            opts = parse_options(job.get("params_json"))
            mp4, scenes, meta, img_missing, img_total = make_video(
                topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id,
                image_fetcher=lambda p: _safe_image(client, p),
                scene_count=SCENE_COUNT[opts["length"]],
                image_style_kw=STYLE[opts["image_style"]],
                voice=VOICE[opts["voice"]],
            )
            client.put_binary(f"/api/content/jobs/{job_id}/video", data=mp4.read_bytes(), content_type="video/mp4")
            script = "\n\n".join(f"[{s['caption']}]\n{s['narration']}" for s in scenes)
            _finalize_video(client, job_id, script, meta, img_missing, img_total)
```
shorts 분기(현재):
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
를(언패킹 5-튜플 + `_finalize_video`로 교체, 나머지 인자 동일):
```python
        elif platform == "shorts":
            opts = parse_shorts_options(job.get("params_json"))
            mp4, scenes, meta, img_missing, img_total = make_video(
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
            _finalize_video(client, job_id, script, meta, img_missing, img_total)
```

- [ ] **Step 6: 통과 + 회귀**

Run: `cd /Users/daegong/projects/popory/services/content && .venv/bin/python -m pytest tests/test_worker.py -q`
Expected: PASS.
Run: `cd /Users/daegong/projects/popory/services/content && .venv/bin/python -m pytest -q`
Expected: 전체 PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/daegong/projects/popory && git add services/content/popory_content/worker.py services/content/tests/test_worker.py && git commit -m "feat(content): 이미지 재시도·로그 + 영상 누락 비율로 status 결정"
```

---

## Task 4: API — regenerate 엔드포인트

**Files:**
- Modify: `workers/api/src/routes/content_jobs.ts`
- Modify: `workers/api/src/routes/content_jobs.test.ts`

- [ ] **Step 1: 실패 테스트 추가**

`content_jobs.test.ts` 파일 끝에 추가(파일 상단에 `userCookie` 헬퍼·`beforeEach`가 이미 있음):
```typescript
describe("POST /api/content/jobs/:id/regenerate", () => {
  async function makeJob(ck: string, platform = "youtube", status = "review", youtubeStatus: string | null = "done") {
    const r = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", platform }),
    });
    const { id } = await r.json<{ id: string }>();
    await env.DB.prepare("UPDATE content_jobs SET status=?, youtube_status=? WHERE id=?").bind(status, youtubeStatus, id).run();
    return id;
  }

  it("review 영상 작업을 queued로 되돌리고 youtube_status는 보존", async () => {
    const ck = await userCookie();
    const id = await makeJob(ck, "youtube", "review", "done");
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/regenerate`, { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const job = await env.DB.prepare("SELECT status, youtube_status FROM content_jobs WHERE id=?").bind(id).first<{ status: string; youtube_status: string }>();
    expect(job?.status).toBe("queued");
    expect(job?.youtube_status).toBe("done");
  });

  it("failed 영상 작업도 재생성 가능", async () => {
    const ck = await userCookie();
    const id = await makeJob(ck, "shorts", "failed", null);
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/regenerate`, { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const job = await env.DB.prepare("SELECT status FROM content_jobs WHERE id=?").bind(id).first<{ status: string }>();
    expect(job?.status).toBe("queued");
  });

  it("영상 플랫폼이 아니면 409", async () => {
    const ck = await userCookie();
    const id = await makeJob(ck, "naver-blog", "review", null);
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/regenerate`, { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(409);
  });

  it("queued 상태면 409", async () => {
    const ck = await userCookie();
    const id = await makeJob(ck, "youtube", "queued", null);
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/regenerate`, { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(409);
  });

  it("타인 작업은 404", async () => {
    const ck1 = await userCookie("u1", "u1@e.com");
    const id = await makeJob(ck1, "youtube", "review", null);
    const ck2 = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/regenerate`, { method: "POST", headers: { cookie: ck2 } });
    expect(res.status).toBe(404);
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/workers/api && npx vitest run src/routes/content_jobs.test.ts`
Expected: FAIL — 엔드포인트 미존재로 200 기대가 깨짐(404/etc).

- [ ] **Step 3: regenerate 엔드포인트 구현**

`content_jobs.ts`의 `app.post("/api/content/jobs/:id/start", ...)` 핸들러 뒤(닫는 `});` 다음)에 추가:
```typescript
  app.post("/api/content/jobs/:id/regenerate", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT id, owner_sub, platform, status FROM content_jobs WHERE id=?")
      .bind(c.req.param("id")).first<{ id: string; owner_sub: string; platform: string; status: string }>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    if (!["youtube", "shorts", "instagram-image"].includes(row.platform)) return c.text("not regeneratable", 409);
    if (row.status !== "review" && row.status !== "failed") return c.text("not regeneratable", 409);
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare("UPDATE content_jobs SET status='queued', error=NULL, updated_at=? WHERE id=?")
      .bind(now, row.id).run();
    return c.json({ ok: true });
  });
```
(youtube_status·instagram_status는 건드리지 않음 — 이미 올라간 영상 보존.)

- [ ] **Step 4: 통과 + 회귀**

Run: `cd /Users/daegong/projects/popory/workers/api && npx vitest run src/routes/content_jobs.test.ts`
Expected: PASS.
Run: `cd /Users/daegong/projects/popory/workers/api && npx vitest run`
Expected: 전체 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory && git add workers/api/src/routes/content_jobs.ts workers/api/src/routes/content_jobs.test.ts && git commit -m "feat(api): 영상 작업 재생성 엔드포인트(review/failed→queued)"
```

---

## Task 5: 포털 — 재생성 버튼 + 경고 배지

**Files:**
- Create: `apps/portal/src/app/(authed)/content/[id]/RegenerateButton.tsx`
- Modify: `apps/portal/src/app/(authed)/content/[id]/page.tsx`

- [ ] **Step 1: RegenerateButton 컴포넌트 작성**

`apps/portal/src/app/(authed)/content/[id]/RegenerateButton.tsx`:
```tsx
"use client";
// 영상 작업을 다시 생성(queued로 되돌림)하는 버튼.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function RegenerateButton({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function regenerate() {
    if (!confirm("이 영상을 다시 생성할까요? 기존 영상은 새 영상으로 덮어써집니다(YouTube에 올라간 영상은 그대로 유지).")) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/regenerate`, { method: "POST", credentials: "include" });
      if (!res.ok) { setErr(`${res.status}`); return; }
      startTransition(() => router.refresh());
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="inline-flex items-center gap-2">
      <button onClick={regenerate} disabled={busy || pending}
        className="rounded-md border border-popory-border px-3 py-1.5 text-xs text-popory-fg hover:bg-popory-card disabled:opacity-50">
        {busy || pending ? "요청 중…" : "재생성"}
      </button>
      {err && <span className="text-xs text-red-600">오류 {err}</span>}
    </div>
  );
}
```

- [ ] **Step 2: page.tsx에 버튼·배지 연결**

`apps/portal/src/app/(authed)/content/[id]/page.tsx` 상단 import에 추가:
```tsx
import { RegenerateButton } from "./RegenerateButton";
```
영상 작업(review/done, youtube/shorts) 블록 — 현재 `{(job.status === "review" || job.status === "done") && (job.platform === "youtube" || job.platform === "shorts") && ( ... <YoutubeUpload .../> ... )}` — 내부의 `<YoutubeUpload .../>` 바로 위(또는 아래)에 재생성 버튼과 배경 경고 배지를 추가한다. `<YoutubeUpload ... />`가 있는 줄 앞에 삽입:
```tsx
              {(() => {
                const meta = job.meta_json ? (JSON.parse(job.meta_json) as { images_missing?: number; images_total?: number }) : {};
                return meta.images_missing ? (
                  <p className="mb-2 text-xs text-amber-600">배경 이미지 일부 누락 ({meta.images_missing}/{meta.images_total}). 재생성을 권장합니다.</p>
                ) : null;
              })()}
              <div className="mb-3"><RegenerateButton jobId={job.id} /></div>
```
또한 `failed` 상태 영상 작업에서도 재생성할 수 있도록, 현재 `{job.status === "failed" && ( ... )}` 블록 안에 영상 플랫폼이면 재생성 버튼을 추가한다:
```tsx
            {(job.platform === "youtube" || job.platform === "shorts" || job.platform === "instagram-image") && (
              <div className="mt-2"><RegenerateButton jobId={job.id} /></div>
            )}
```
참고: `JobDetail` 인터페이스에는 이미 `meta_json: string | null`(page.tsx:23)이 있으므로 위 배지 블록은 타입 안전하다. 별도 인터페이스 수정 불필요.

- [ ] **Step 3: 타입체크**

Run: `cd /Users/daegong/projects/popory/apps/portal && npx tsc --noEmit`
Expected: 에러 없음. (meta_json 타입 이슈가 나면 인터페이스에 `meta_json?: string | null` 추가하거나 배지 블록 제거.)

- [ ] **Step 4: Commit**

```bash
cd /Users/daegong/projects/popory && git add "apps/portal/src/app/(authed)/content/[id]/RegenerateButton.tsx" "apps/portal/src/app/(authed)/content/[id]/page.tsx" && git commit -m "feat(portal): 영상 재생성 버튼 + 배경 누락 경고 배지"
```

---

## 마무리

- [ ] **전체 회귀**: `cd services/content && .venv/bin/python -m pytest -q`(전체 green), `cd workers/api && npx vitest run`(전체 green), `cd apps/portal && npx tsc --noEmit`.
- [ ] **배포(머지 후)**: 워커는 launchd 상주 → 코드 반영 위해 `launchctl kickstart -k gui/501/com.popory.content-worker`(레이블 확인). API `npx wrangler deploy --config infra/wrangler/api.toml --env prod`. 포털 `pnpm --filter @popory/portal build:cf` → `npx wrangler pages deploy apps/portal/.vercel/output/static --project-name popory-portal --branch main`.
- [ ] **재생성 운영**: 배포 후 사용자가 배경 없는 영상 상세에서 "재생성" 버튼으로 순차 진행(한도 재소진 방지). Part 1 덕분에 재생성 시 실패가 로그·status로 보임.
