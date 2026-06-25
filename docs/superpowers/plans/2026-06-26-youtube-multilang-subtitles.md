# 유튜브 다국어 소프트자막 (KO/EN/ZH/JA) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 유튜브 동영상·쇼츠 생성 시 한국어 음성·번인은 유지하고 KO/EN/ZH/JA `.srt`를 만들어 유튜브 caption 트랙으로 업로드한다.

**Architecture:** 생성 단계(`render_video`)에서 번인에 쓰는 문장·타임코드를 전역 cue 목록으로 재사용한다. 워커가 claude CLI로 EN/ZH/JA를 1:1 번역해 4개 `.srt`를 R2에 저장하고, 유튜브 업로드 시 `captions.insert`로 트랙을 올린다. 번역·자막 업로드 실패는 영상 흐름을 막지 않는다.

**Tech Stack:** Python 3.11(`services/content`, pytest + `responses`), Hono/TypeScript Worker(`workers/api`, vitest), Cloudflare R2, YouTube Data API v3, claude CLI.

## Global Constraints

- 신규 Python 파일 첫 줄에 역할을 설명하는 한국어 한 줄 주석(`# …`). 마침표로 끝낸다. (CLAUDE.md 규칙 6·5)
- 음성·내레이션·번인 자막은 한국어 고정 — 변경 금지.
- 소프트 트랙 언어는 정확히 `ko, en, zh, ja` 4개.
- 자막 언어 코드 허용목록은 `("ko","en","zh","ja")`로 통일(파이썬·TS 동일).
- 크로스페이드 전이 길이는 `XFADE_TD = 0.4`초(기존 `_xfade_graph` 기본값과 동일 값).
- 번역·자막 업로드 실패는 경고 로그 후 진행하며 영상 생성/업로드를 실패시키지 않는다.
- 외과적 변경: 기존 반환 구조·테스트는 필요한 만큼만 수정한다.

---

### Task 1: `subtitles.py` — SRT 직렬화 + 장면 오프셋 (순수 함수)

**Files:**
- Create: `services/content/popory_content/subtitles.py`
- Test: `services/content/tests/test_subtitles.py`

**Interfaces:**
- Produces: `Cue = tuple[float, float, str]`; `scene_offsets(scene_durations: list[float], td: float) -> list[float]`; `to_srt(cues: list[Cue]) -> str`

- [ ] **Step 1: Write the failing test**

`services/content/tests/test_subtitles.py`:
```python
# subtitles 모듈(오프셋·SRT 직렬화) 검증.
from popory_content.subtitles import scene_offsets, to_srt


def test_scene_offsets_subtracts_transition_overlap():
    # 장면 길이 [10,8,6], 전이 0.4 → 누적에서 전이마다 0.4 차감.
    assert scene_offsets([10.0, 8.0, 6.0], 0.4) == [0.0, 9.6, 17.2]


def test_scene_offsets_single_scene():
    assert scene_offsets([12.5], 0.4) == [0.0]


def test_to_srt_formats_timecodes_and_numbers():
    srt = to_srt([(0.0, 1.5, "안녕"), (1.5, 3.25, "반가워")])
    assert srt == (
        "1\n00:00:00,000 --> 00:00:01,500\n안녕\n\n"
        "2\n00:00:01,500 --> 00:00:03,250\n반가워\n\n"
    )


def test_to_srt_skips_empty_text_and_renumbers():
    srt = to_srt([(0.0, 1.0, "  "), (1.0, 2.0, "본문")])
    assert srt.startswith("1\n00:00:01,000 --> 00:00:02,000\n본문\n")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/content && .venv/bin/pytest tests/test_subtitles.py -v`
Expected: FAIL — `ModuleNotFoundError: popory_content.subtitles`

- [ ] **Step 3: Write minimal implementation**

`services/content/popory_content/subtitles.py`:
```python
# 자막 cue를 SRT로 직렬화하고 장면 크로스페이드 오프셋을 산출하는 순수 함수 모듈.
from __future__ import annotations

Cue = tuple[float, float, str]


def scene_offsets(scene_durations: list[float], td: float) -> list[float]:
    """각 장면의 최종 영상 절대 시작 시각. 장면은 전이 td만큼 겹치므로 장면마다 td를 뺀다."""
    offsets: list[float] = []
    for i in range(len(scene_durations)):
        if i == 0:
            offsets.append(0.0)
        else:
            offsets.append(offsets[i - 1] + scene_durations[i - 1] - td)
    return offsets


def _fmt_ts(t: float) -> str:
    """초 → SRT 타임코드 HH:MM:SS,mmm."""
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues: list[Cue]) -> str:
    """cue 목록을 SRT 텍스트로. 빈 텍스트 cue는 건너뛰고 번호를 다시 매긴다."""
    out: list[str] = []
    n = 0
    for st, en, text in cues:
        text = (text or "").strip()
        if not text:
            continue
        n += 1
        out.append(f"{n}\n{_fmt_ts(st)} --> {_fmt_ts(en)}\n{text}\n")
    return "\n".join(out) + ("\n" if out else "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/content && .venv/bin/pytest tests/test_subtitles.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add services/content/popory_content/subtitles.py services/content/tests/test_subtitles.py
git commit -m "feat(content): 자막 SRT 직렬화·장면 오프셋 모듈"
```

---

### Task 2: `video.py` — 전역 자막 cue 반환

**Files:**
- Modify: `services/content/popory_content/video.py` (상수 추가, `_xfade_graph` 기본값, `render_video`/`make_video` 반환, 장면 cue 누적)
- Modify: `services/content/popory_content/worker.py:55-79` (run_once 두 분기 언팩)
- Modify: `services/content/tests/test_video.py:177,203` (언팩)
- Test: `services/content/tests/test_video.py` (cue 정렬 단위 테스트 추가)

**Interfaces:**
- Consumes: `subtitles.scene_offsets`, `subtitles.Cue`
- Produces: `render_video(...) -> tuple[Path, int, int, list[Cue]]`; `make_video(...) -> tuple[Path, list[dict], dict, int, int, list[Cue]]`

- [ ] **Step 1: Write the failing test**

`services/content/tests/test_video.py` 끝에 추가:
```python
def test_global_cues_offset_by_scene(monkeypatch):
    # 장면 2개, 각 1문장. 장면 클립 길이를 고정해 전역 cue 오프셋을 검증.
    from popory_content import video as V

    monkeypatch.setattr(V, "_duration", lambda p: 5.0)  # 모든 클립 5초로 측정
    # render 내부의 무거운 ffmpeg/TTS 호출을 우회: 장면-로컬 cue를 직접 합성.
    local = [[(0.0, 2.0, "첫 문장")], [(0.0, 1.5, "둘째 문장")]]
    durations = [5.0, 5.0]
    offsets = V.scene_offsets(durations, V.XFADE_TD)
    cues = []
    for off, scene in zip(offsets, local):
        cues += [(off + st, off + en, t) for (st, en, t) in scene]
    assert cues[0] == (0.0, 2.0, "첫 문장")
    assert cues[1] == (4.6, 6.1, "둘째 문장")  # 5.0 - 0.4 = 4.6 오프셋
```

(이 테스트는 `video.py`가 `scene_offsets`·`XFADE_TD`를 노출하는지까지 확인한다.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/content && .venv/bin/pytest tests/test_video.py::test_global_cues_offset_by_scene -v`
Expected: FAIL — `AttributeError: module 'popory_content.video' has no attribute 'XFADE_TD'`

- [ ] **Step 3: Implement — 상수·import·반환 변경**

`video.py` 상단 import 근처(예: `from typing import Any` 아래)에 추가:
```python
from popory_content.subtitles import scene_offsets, to_srt, Cue
```

`SENTENCE_GAP = 0.35` 아래에 추가:
```python
XFADE_TD = 0.4  # 장면 크로스페이드 전이 길이(초). _xfade_graph·자막 오프셋이 공유.
```

`_xfade_graph` 시그니처의 기본값을 상수로:
```python
def _xfade_graph(durations: list[float], td: float = XFADE_TD) -> tuple[str, str, str]:
```

`render_video`의 장면 루프에서 장면-로컬 cue와 클립을 누적한다. 루프 진입 전(`clips: list[Path] = []` 옆)에 추가:
```python
    scene_local_cues: list[list[Cue]] = []
```

루프 안에서 `spans = _spans_from_durations(seg_durs, SENTENCE_GAP)` 직후에 추가:
```python
        scene_local_cues.append([(st, en, sentences[k]) for k, (st, en) in enumerate(spans)])
```

루프 종료 후 기존 꼬리(`joined = work / "joined.mp4"` 직전)에서 클립 길이를 한 번만 측정하도록 바꾸고, else 분기의 재측정을 제거한다.

기존:
```python
    joined = work / "joined.mp4"
    if len(clips) == 1:
        shutil.copy(clips[0], joined)
    else:
        durations = [_duration(c) for c in clips]
        graph, vlabel, alabel = _xfade_graph(durations)
```
변경:
```python
    clip_durations = [_duration(c) for c in clips]
    joined = work / "joined.mp4"
    if len(clips) == 1:
        shutil.copy(clips[0], joined)
    else:
        graph, vlabel, alabel = _xfade_graph(clip_durations)
```

`render_video`의 마지막 `return out, images_missing, images_total` 을 교체:
```python
    offsets = scene_offsets(clip_durations, XFADE_TD)
    cues: list[Cue] = []
    for off, local in zip(offsets, scene_local_cues):
        for st, en, text in local:
            cues.append((off + st, off + en, text))
    return out, images_missing, images_total, cues
```

`make_video`의 마지막 두 줄을 교체:
```python
    mp4, img_missing, img_total, cues = render_video(scenes, job_id=job_id, image_fetcher=image_fetcher, voice=voice, portrait=portrait)
    return mp4, scenes, meta, img_missing, img_total, cues
```

- [ ] **Step 4: Fix callers (worker + 기존 video 테스트)**

`worker.py`의 youtube 분기(약 55행)와 shorts 분기(약 67행) 두 곳 모두 언팩을 6요소로:
```python
            mp4, scenes, meta, img_missing, img_total, cues = make_video(
```
(두 분기 동일하게 변경. `cues`는 Task 6에서 사용하므로 지금은 받아만 둔다.)

`tests/test_video.py:177`:
```python
    out, _, _, _ = render_video(scenes, job_id="smoketest")
```
`tests/test_video.py:203`:
```python
    out, missing, total, _ = video.render_video(scenes, job_id="vbtest", image_fetcher=fetcher)
```

- [ ] **Step 5: Run tests**

Run: `cd services/content && .venv/bin/pytest tests/test_video.py tests/test_worker.py -v`
Expected: PASS (신규 cue 테스트 포함, 기존 스모크 통과)

- [ ] **Step 6: Commit**

```bash
git add services/content/popory_content/video.py services/content/popory_content/worker.py services/content/tests/test_video.py
git commit -m "feat(content): render_video가 전역 자막 cue 반환"
```

---

### Task 3: `translate.py` — claude CLI 1:1 번역

**Files:**
- Create: `services/content/popory_content/translate.py`
- Test: `services/content/tests/test_translate.py`

**Interfaces:**
- Consumes: `generate.run_claude_cli`, `generate.GenerateError`
- Produces: `translate_lines(ko_lines: list[str], langs=("en","zh","ja"), *, job_id="adhoc", runner=run_claude_cli) -> dict[str, list[str]] | None`

- [ ] **Step 1: Write the failing test**

`services/content/tests/test_translate.py`:
```python
# 한국어 문장 1:1 다국어 번역(claude CLI) 검증 — runner 스텁 주입.
from popory_content import translate
from popory_content.generate import GenerateError


def test_translate_aligns_each_language():
    def fake_runner(*, system_prompt, user_msg, parse, job_id):
        return parse('{"en":["a","b"],"zh":["甲","乙"],"ja":["あ","い"]}')
    out = translate.translate_lines(["가", "나"], runner=fake_runner)
    assert out == {"en": ["a", "b"], "zh": ["甲", "乙"], "ja": ["あ", "い"]}


def test_translate_length_mismatch_returns_none():
    # run_claude_cli는 parse 실패를 재시도 후 GenerateError로 감싼다 → None.
    def bad_runner(*, system_prompt, user_msg, parse, job_id):
        raise GenerateError("length mismatch")
    assert translate.translate_lines(["가", "나"], runner=bad_runner) is None


def test_translate_empty_returns_empty_arrays():
    assert translate.translate_lines([]) == {"en": [], "zh": [], "ja": []}


def test_parse_rejects_wrong_length():
    import pytest
    captured = {}
    def runner(*, system_prompt, user_msg, parse, job_id):
        captured["parse"] = parse
        return parse('{"en":["only-one"],"zh":["甲","乙"],"ja":["あ","い"]}')
    # en 길이 1 != 입력 2 → parse 가 ValueError
    with pytest.raises(ValueError):
        translate.translate_lines(["가", "나"], runner=runner)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/content && .venv/bin/pytest tests/test_translate.py -v`
Expected: FAIL — `ModuleNotFoundError: popory_content.translate`

- [ ] **Step 3: Write minimal implementation**

`services/content/popory_content/translate.py`:
```python
# 한국어 자막 문장을 EN/ZH/JA로 1:1 정렬 번역하는 claude CLI 래퍼.
from __future__ import annotations

import json
import re
from typing import Callable

from popory_content.generate import run_claude_cli, GenerateError

LANGS = ("en", "zh", "ja")

_SYSTEM = (
    "당신은 자막 번역가입니다. 한국어 문장 목록을 받아 각 언어로 번역합니다. "
    "규칙. 입력 문장 수와 출력 배열 길이를 정확히 같게 유지합니다. "
    "문장을 합치거나 나누지 않습니다. 자연스러운 구어체로 번역하고 고유명사·인용은 보존합니다. "
    "광고·구독·홍보 문구를 추가하지 않습니다. "
    'JSON 객체 하나만 출력합니다. 형식 {"en":[...],"zh":[...],"ja":[...]}. 코드블록 표시 금지.'
)


def _build_parse(n: int, langs) -> Callable[[str], dict[str, list[str]]]:
    def parse(stdout: str) -> dict[str, list[str]]:
        m = re.search(r"\{.*\}", stdout, re.S)
        if not m:
            raise ValueError("번역 JSON 없음")
        data = json.loads(m.group(0))
        out: dict[str, list[str]] = {}
        for lang in langs:
            arr = data.get(lang)
            if not isinstance(arr, list) or len(arr) != n:
                got = len(arr) if isinstance(arr, list) else "none"
                raise ValueError(f"{lang} 길이 불일치: {got} != {n}")
            out[lang] = [str(x) for x in arr]
        return out
    return parse


def translate_lines(ko_lines: list[str], langs=LANGS, *, job_id: str = "adhoc",
                    runner=run_claude_cli) -> dict[str, list[str]] | None:
    """한국어 문장 배열 → {lang: 번역 배열}. 1:1 정렬을 보장 못 하면 None."""
    if not ko_lines:
        return {lang: [] for lang in langs}
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(ko_lines))
    user_msg = (
        f"다음 한국어 문장 {len(ko_lines)}개를 {', '.join(langs)}로 번역하세요. "
        "각 배열 길이는 정확히 입력 수와 같아야 합니다.\n\n" + numbered
    )
    try:
        return runner(system_prompt=_SYSTEM, user_msg=user_msg,
                      parse=_build_parse(len(ko_lines), langs), job_id=job_id)
    except GenerateError:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/content && .venv/bin/pytest tests/test_translate.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add services/content/popory_content/translate.py services/content/tests/test_translate.py
git commit -m "feat(content): 자막 EN/ZH/JA 1:1 번역 모듈"
```

---

### Task 4: TS 자막 저장·조회 엔드포인트

**Files:**
- Modify: `workers/api/src/routes/content_jobs.ts` (video GET 라우트 아래, 약 232행 뒤에 추가)
- Test: `workers/api/src/routes/content_jobs.test.ts`

**Interfaces:**
- Produces: `PUT /api/content/jobs/:id/subtitle/:lang` (service auth) → R2 `content/subs/{id}/{lang}.srt`; `GET /api/content/jobs/:id/subtitle/:lang` (service auth) → srt 본문 또는 404

- [ ] **Step 1: Write the failing test**

`workers/api/src/routes/content_jobs.test.ts`에 추가(기존 service bearer 헬퍼·makeJob 패턴 재사용; 파일 상단 헬퍼 이름이 다르면 동일 파일의 기존 헬퍼를 사용):
```typescript
describe("자막 저장·조회", () => {
  it("워커가 .srt를 저장하고 다시 읽는다", async () => {
    const auth = await serviceBearer();
    await makeJob("sub1", "youtube");
    const put = await SELF.fetch("https://example.com/api/content/jobs/sub1/subtitle/en", {
      method: "PUT", headers: { authorization: auth }, body: "1\n00:00:00,000 --> 00:00:01,000\nhi\n",
    });
    expect(put.status).toBe(200);
    const get = await SELF.fetch("https://example.com/api/content/jobs/sub1/subtitle/en", {
      headers: { authorization: auth },
    });
    expect(get.status).toBe(200);
    expect(await get.text()).toContain("00:00:00,000");
  });

  it("허용 안 된 언어는 400", async () => {
    const auth = await serviceBearer();
    await makeJob("sub2", "youtube");
    const res = await SELF.fetch("https://example.com/api/content/jobs/sub2/subtitle/fr", {
      method: "PUT", headers: { authorization: auth }, body: "x",
    });
    expect(res.status).toBe(400);
  });
});
```

(`content_jobs.test.ts`에 `serviceBearer`/`makeJob` 헬퍼가 없으면 `content_facebook_upload.test.ts`의 동일 헬퍼를 복사해 파일 상단에 추가한다.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd workers/api && npx vitest run src/routes/content_jobs.test.ts -t "자막"`
Expected: FAIL — PUT이 404/405 (라우트 없음)

- [ ] **Step 3: Implement — 라우트 추가**

`content_jobs.ts`의 `mountContentJobs` 안, video GET 라우트(약 232행 `});` 뒤)에 추가:
```typescript
  const SUB_LANGS = new Set(["ko", "en", "zh", "ja"]);

  app.put("/api/content/jobs/:id/subtitle/:lang", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const id = c.req.param("id");
    const lang = c.req.param("lang");
    if (!SUB_LANGS.has(lang)) return c.text("bad lang", 400);
    const row = await c.env.DB.prepare("SELECT id FROM content_jobs WHERE id=?").bind(id).first<{ id: string }>();
    if (!row) return c.text("not found", 404);
    const body = await c.req.arrayBuffer();
    await c.env.R2.put(`content/subs/${id}/${lang}.srt`, body, { httpMetadata: { contentType: "text/plain; charset=utf-8" } });
    return c.json({ ok: true });
  });

  app.get("/api/content/jobs/:id/subtitle/:lang", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const id = c.req.param("id");
    const lang = c.req.param("lang");
    if (!SUB_LANGS.has(lang)) return c.text("bad lang", 400);
    const obj = await c.env.R2.get(`content/subs/${id}/${lang}.srt`);
    if (!obj) return c.text("not found", 404);
    return new Response(obj.body, { headers: { "content-type": "text/plain; charset=utf-8" } });
  });
```

(`requireService`·`WORKER_AREA`는 같은 파일에서 이미 사용 중이므로 추가 import 불필요. 미정의면 `content_jobs.ts` 상단 import/상수를 video PUT 라우트와 동일하게 맞춘다.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd workers/api && npx vitest run src/routes/content_jobs.test.ts -t "자막"`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add workers/api/src/routes/content_jobs.ts workers/api/src/routes/content_jobs.test.ts
git commit -m "feat(content): 자막 .srt R2 저장·조회 워커 엔드포인트"
```

---

### Task 5: `youtube_upload.py` — `upload_caption`

**Files:**
- Modify: `services/content/popory_content/youtube_upload.py`
- Test: `services/content/tests/test_youtube_upload.py`

**Interfaces:**
- Produces: `CAPTION_URL: str`; `upload_caption(access_token: str, video_id: str, language: str, name: str, srt_bytes: bytes) -> None` (실패 시 `UploadError`)

- [ ] **Step 1: Write the failing test**

`services/content/tests/test_youtube_upload.py`에 추가:
```python
@responses.activate
def test_upload_caption_posts_multipart_related():
    from popory_content.youtube_upload import upload_caption, CAPTION_URL
    responses.add(responses.POST, CAPTION_URL, json={"id": "cap1"}, status=200)
    upload_caption("tok", "vid1", "en", "popory en", b"1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    req = responses.calls[0].request
    assert req.headers["Authorization"] == "Bearer tok"
    assert req.headers["Content-Type"].startswith("multipart/related; boundary=")


@responses.activate
def test_upload_caption_error_raises():
    from popory_content.youtube_upload import upload_caption, CAPTION_URL, UploadError
    responses.add(responses.POST, CAPTION_URL, status=403, json={"error": "scope"})
    with pytest.raises(UploadError):
        upload_caption("tok", "vid1", "en", "n", b"x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/content && .venv/bin/pytest tests/test_youtube_upload.py -k caption -v`
Expected: FAIL — `ImportError: cannot import name 'upload_caption'`

- [ ] **Step 3: Implement**

`youtube_upload.py` 상단 `import requests` 아래에 추가:
```python
import json

CAPTION_URL = "https://www.googleapis.com/upload/youtube/v3/captions?part=snippet&uploadType=multipart"
```

파일 끝에 함수 추가:
```python
def upload_caption(access_token: str, video_id: str, language: str, name: str, srt_bytes: bytes) -> None:
    """captions.insert(multipart/related)로 자막 트랙 1개 업로드. 실패 시 UploadError."""
    meta = {"snippet": {"videoId": video_id, "language": language, "name": name, "isDraft": False}}
    boundary = "popory_caption_boundary"
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(meta)}\r\n"
        f"--{boundary}\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + srt_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    resp = requests.post(
        CAPTION_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        data=body,
        timeout=60,
    )
    if resp.status_code not in (200, 201):
        raise UploadError(f"caption {resp.status_code}: {resp.text[:200]}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/content && .venv/bin/pytest tests/test_youtube_upload.py -v`
Expected: PASS (기존 + 신규 2건)

- [ ] **Step 5: Commit**

```bash
git add services/content/popory_content/youtube_upload.py services/content/tests/test_youtube_upload.py
git commit -m "feat(content): 유튜브 captions.insert 자막 업로드"
```

---

### Task 6: 워커 연결 — 생성 시 .srt 저장, 업로드 시 caption 전송

**Files:**
- Modify: `services/content/popory_content/worker.py` (import, 헬퍼 2개, run_once 두 분기, run_upload_once)
- Test: `services/content/tests/test_worker.py`

**Interfaces:**
- Consumes: `subtitles.to_srt`, `translate.translate_lines`, `youtube_upload.upload_caption`, Task 2의 `cues`, Task 4의 자막 엔드포인트
- Produces: `_store_subtitles(client, job_id: str, cues: list) -> None`; `_upload_captions(client, access_token: str, job_id: str, video_id: str) -> None`; `SUB_LANGS = ("ko", "en", "zh", "ja")`

- [ ] **Step 1: Write the failing test**

`services/content/tests/test_worker.py`에 추가:
```python
class SubClient:
    """put_binary/get_bytes를 기록·스텁하는 자막용 페이크."""
    def __init__(self, srt_by_lang=None):
        self.put = []  # (path, data)
        self._srt = srt_by_lang or {}

    def put_binary(self, path, *, data, content_type):
        self.put.append((path, data))
        return {"ok": True}

    def get_bytes(self, path):
        for lang, b in self._srt.items():
            if path.endswith(f"/subtitle/{lang}"):
                return b
        raise RuntimeError("404")


def test_store_subtitles_translates_and_stores_four(monkeypatch):
    monkeypatch.setattr(worker, "translate_lines",
                        lambda lines, **kw: {"en": ["A", "B"], "zh": ["甲", "乙"], "ja": ["あ", "い"]})
    client = SubClient()
    cues = [(0.0, 1.0, "가"), (1.0, 2.0, "나")]
    worker._store_subtitles(client, "j1", cues)
    langs = {p.rsplit("/", 1)[1] for p, _ in client.put}
    assert langs == {"ko", "en", "zh", "ja"}
    en = next(d for p, d in client.put if p.endswith("/subtitle/en"))
    assert b"00:00:00,000 --> 00:00:01,000" in en and b"A" in en


def test_store_subtitles_translation_failure_keeps_ko(monkeypatch):
    monkeypatch.setattr(worker, "translate_lines", lambda lines, **kw: None)
    client = SubClient()
    worker._store_subtitles(client, "j1", [(0.0, 1.0, "가")])
    langs = {p.rsplit("/", 1)[1] for p, _ in client.put}
    assert langs == {"ko"}


def test_upload_captions_uploads_present_langs(monkeypatch):
    sent = []
    monkeypatch.setattr(worker, "upload_caption",
                        lambda tok, vid, lang, name, b: sent.append((lang, vid)))
    client = SubClient(srt_by_lang={"en": b"1\n00:00:00,000 --> 00:00:01,000\nhi\n"})
    worker._upload_captions(client, "tok", "j1", "vid9")
    assert sent == [("en", "vid9")]


def test_store_subtitles_empty_cues_noop():
    client = SubClient()
    worker._store_subtitles(client, "j1", [])
    assert client.put == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/content && .venv/bin/pytest tests/test_worker.py -k "subtitle or caption" -v`
Expected: FAIL — `AttributeError: module 'popory_content.worker' has no attribute '_store_subtitles'`

- [ ] **Step 3: Implement — import·상수·헬퍼**

`worker.py` import 영역에 추가:
```python
from popory_content.subtitles import to_srt
from popory_content.translate import translate_lines
from popory_content.youtube_upload import upload, upload_caption, UploadError
```
(기존 `from popory_content.youtube_upload import upload` 줄이 있으면 그 줄을 위 형태로 교체.)

`WORKER_AREA = "content-worker"` 근처에 추가:
```python
SUB_LANGS = ("ko", "en", "zh", "ja")
```

`_issue_media_token` 위(또는 run_upload_once 위)에 헬퍼 2개 추가:
```python
def _store_subtitles(client, job_id: str, cues: list) -> None:
    """KO cue를 EN/ZH/JA로 번역해 4개 .srt를 R2에 저장. 실패는 경고만(영상 정상)."""
    if not cues:
        return
    ko_lines = [text for _, _, text in cues]
    by_lang: dict[str, list[str]] = {"ko": ko_lines}
    try:
        tr = translate_lines(ko_lines, job_id=job_id)
    except Exception as e:  # noqa: BLE001
        tr = None
        append_log(LOGS_DIR, {"worker": "content", "status": "subs_translate_failed", "job": job_id, "error": str(e)[:200]})
    if tr:
        by_lang.update(tr)
    for lang, lines in by_lang.items():
        srt = to_srt([(st, en, lines[i]) for i, (st, en, _) in enumerate(cues)])
        try:
            client.put_binary(f"/api/content/jobs/{job_id}/subtitle/{lang}",
                              data=srt.encode("utf-8"), content_type="text/plain; charset=utf-8")
        except Exception as e:  # noqa: BLE001
            append_log(LOGS_DIR, {"worker": "content", "status": "subs_store_failed", "job": job_id, "lang": lang, "error": str(e)[:200]})


def _upload_captions(client, access_token: str, job_id: str, video_id: str) -> None:
    """저장된 .srt를 유튜브 caption 트랙으로 업로드. lang별 실패는 경고만(영상 정상)."""
    for lang in SUB_LANGS:
        try:
            srt = client.get_bytes(f"/api/content/jobs/{job_id}/subtitle/{lang}")
        except Exception:  # noqa: BLE001 — 없으면 건너뜀
            continue
        if not srt:
            continue
        try:
            upload_caption(access_token, video_id, lang, f"popory {lang}", srt)
        except Exception as e:  # noqa: BLE001
            append_log(LOGS_DIR, {"worker": "content", "status": "caption_failed", "job": job_id, "lang": lang, "error": str(e)[:200]})
```

- [ ] **Step 4: Implement — run_once 분기에서 호출**

`worker.py` youtube 분기에서 `client.put_binary(.../video, ...)` 다음 줄에 추가:
```python
            _store_subtitles(client, job_id, cues)
```
shorts 분기에서도 `client.put_binary(.../video, ...)` 다음 줄에 동일하게 추가:
```python
            _store_subtitles(client, job_id, cues)
```

`run_upload_once`에서 `client.patch(.../youtube-result, {"status":"done", "video_id": video_id})` **앞**에 caption 업로드 추가:
```python
        _upload_captions(client, data["access_token"], job_id, video_id)
        client.patch(f"/api/content/jobs/{job_id}/youtube-result", json={"status": "done", "video_id": video_id})
```

- [ ] **Step 5: Run tests**

Run: `cd services/content && .venv/bin/pytest tests/test_worker.py -v`
Expected: PASS (신규 자막/caption 4건 + 기존 통과)

- [ ] **Step 6: Commit**

```bash
git add services/content/popory_content/worker.py services/content/tests/test_worker.py
git commit -m "feat(content): 워커가 .srt 저장·유튜브 caption 업로드 연결"
```

---

### Task 7: 유튜브 OAuth 스코프에 `force-ssl` 추가

**Files:**
- Modify: `workers/api/src/routes/content_youtube.ts:8`

**Interfaces:**
- 없음 (스코프 문자열 한 줄. 기존 연결 계정은 재연결해야 자막 권한 부여.)

- [ ] **Step 1: 스코프 변경**

`content_youtube.ts:8`:
```typescript
const SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.force-ssl https://www.googleapis.com/auth/youtube.readonly";
```

- [ ] **Step 2: 타입체크/빌드 확인**

Run: `cd workers/api && npx tsc --noEmit`
Expected: 신규 오류 없음(기존 test 파일의 사전 오류는 무관).

- [ ] **Step 3: Commit**

```bash
git add workers/api/src/routes/content_youtube.ts
git commit -m "feat(content): 유튜브 스코프에 force-ssl 추가(자막 업로드용)"
```

---

## 최종 검증 (전체)

- [ ] **Python 전체 테스트**

Run: `cd services/content && .venv/bin/pytest -q`
Expected: 전부 PASS

- [ ] **TS 관련 테스트**

Run: `cd workers/api && npx vitest run src/routes/content_jobs.test.ts src/routes/content_youtube_upload.test.ts`
Expected: 전부 PASS

## 배포 (구현·검증 후, 사용자 승인 시)

1. API 워커 배포: `cd workers/api && npx wrangler deploy --env prod --config ../../infra/wrangler/api.toml`
2. 콘텐츠 워커 재시작(`com.popory.content-worker` launchd) — 모듈을 메모리에 들고 있으므로 필수.
3. `/content/youtube`에서 기존 연결 계정 **재연결**(force-ssl 동의).

## 자가 검토 결과

- 스펙 커버리지: 번역(T3)·.srt 직렬화/타임라인(T1·T2)·저장(T4)·caption 업로드(T5)·워커 연결(T6)·스코프(T7) 모두 태스크 존재. KO+EN+ZH+JA 4개 트랙(T6), 항상 ON(run_once 무조건 호출), 내성(번역 None·caption 실패 경고)·R2 키 규약 반영.
- 플레이스홀더: 없음(모든 코드·명령·기대값 구체).
- 타입 일관성: `cues: list[Cue]`(T2)→`_store_subtitles`(T6), `translate_lines` 시그니처(T3)→worker import(T6), `upload_caption` 시그니처(T5)→`_upload_captions`(T6), `SUB_LANGS` 언어목록 파이썬/TS 동일.
