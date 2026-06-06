# YouTube 영상 생성 (텍스트카드 슬라이드쇼) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 컨텐츠 작업에 `platform=youtube`를 추가해, claude 대본 + macOS say(한국어 TTS) + ffmpeg(텍스트카드 슬라이드쇼)로 MP4를 생성·R2 저장하고 포털에서 재생한다.

**Architecture:** 기존 큐·워커·포털 재사용. 워커가 platform으로 분기 — youtube면 claude로 장면 대본 생성 → 장면별 say 음성 → ffmpeg로 텍스트카드+자막+오디오 클립 → concat → MP4 → Worker API `PUT /:id/video`로 R2 저장. 포털 상세는 youtube면 `<video>` 플레이어.

**Tech Stack:** Python(워커, pytest), TypeScript(Hono Worker · Next.js), claude CLI, macOS `say`, `ffmpeg`/`ffprobe`.

**전제:** Slice 1(A·B·C) + 리치 HTML이 prod 가동. 도구 확인 완료 — ffmpeg 8.1, say 한국어 음성(Yuna). 스펙 `docs/superpowers/specs/2026-06-06-youtube-video-generation-design.md`.

---

## File Structure

| 파일 | 변경 | 책임 |
|------|------|------|
| `packages/types/src/content_job.ts` | 수정 | platform enum(naver-blog\|youtube) |
| `packages/types/src/content_job.test.ts` | 수정 | platform 단언 |
| `services/content/popory_content/generate.py` | 수정 | `run_claude_cli(parse=...)` 추출(DRY) |
| `services/content/popory_content/video_prompt.py` | 신규 | 영상 대본 system/user 프롬프트 |
| `services/content/popory_content/video_contract.py` | 신규 | `<scenes_json>`·`<video_meta>` 파싱 |
| `services/content/popory_content/video.py` | 신규 | generate_scenes + render_video(say+ffmpeg) + make_video |
| `services/content/popory_content/portal_client.py` | 수정 | `put_binary` (MP4 업로드) |
| `services/content/popory_content/worker.py` | 수정 | platform 분기 → youtube 영상 경로 |
| `workers/api/src/routes/content_jobs.ts` | 수정 | PUT/GET `/:id/video` |
| `apps/portal/src/app/(authed)/content/new/NewJobForm.tsx` | 수정 | platform 선택 |
| `apps/portal/src/app/(authed)/content/[id]/page.tsx` | 수정 | youtube면 video 플레이어 |
| 각 신규 모듈의 `tests/test_*.py` | 신규 | pytest |

---

## Task 1: types — platform enum

**Files:**
- Modify: `packages/types/src/content_job.ts`
- Modify: `packages/types/src/content_job.test.ts`

- [ ] **Step 1: 테스트 추가 (실패 유도)**

`packages/types/src/content_job.test.ts` 의 `ContentJobCreateSchema` describe 블록에 케이스 추가:

```ts
  it("platform youtube 허용", () => {
    expect(ContentJobCreateSchema.parse({ topic: "t", platform: "youtube" }).platform).toBe("youtube");
  });
  it("알 수 없는 platform 거부", () => {
    expect(ContentJobCreateSchema.safeParse({ topic: "t", platform: "tiktok" }).success).toBe(false);
  });
```

- [ ] **Step 2: 실패 확인**

Run: `pnpm --filter @popory/types test -- --run content_job`
Expected: FAIL (현재 platform은 `z.literal("naver-blog")` 라 youtube 거부).

- [ ] **Step 3: 스키마 수정**

`packages/types/src/content_job.ts` 의 `ContentJobCreateSchema` 안 platform 한 줄을 변경. 변경 전:
```ts
  platform: z.literal("naver-blog").default("naver-blog"),
```
변경 후:
```ts
  platform: z.enum(["naver-blog", "youtube"]).default("naver-blog"),
```
(`StyleProfileCreateSchema` 의 platform 은 그대로 둔다 — 스타일은 블로그용.)

- [ ] **Step 4: 통과 확인**

Run: `pnpm --filter @popory/types test -- --run content_job`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add packages/types/src/content_job.ts packages/types/src/content_job.test.ts
git commit -m "feat(types): content 작업 platform 에 youtube 추가"
```

---

## Task 2: video_prompt.py — 영상 대본 프롬프트

**Files:**
- Create: `services/content/popory_content/video_prompt.py`
- Create: `services/content/tests/test_video_prompt.py`

- [ ] **Step 1: 실패 테스트**

`services/content/tests/test_video_prompt.py`:

```python
# 영상 대본 system prompt 가 장면·메타 출력 계약을 담는지 검증.
from popory_content.video_prompt import build_video_system_prompt, build_video_user_message


def test_system_prompt_has_contract():
    sp = build_video_system_prompt([])
    assert "scenes_json" in sp
    assert "video_meta" in sp
    assert "narration" in sp
    assert "caption" in sp


def test_system_prompt_embeds_style():
    sp = build_video_system_prompt(["내 말투 샘플"])
    assert "내 말투 샘플" in sp


def test_user_message_has_topic():
    um = build_video_user_message("사피엔스 요약", [])
    assert "사피엔스 요약" in um
    assert "scenes_json" in um
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video_prompt.py -q`
Expected: FAIL (모듈 없음).

- [ ] **Step 3: 구현**

`services/content/popory_content/video_prompt.py`:

```python
# claude CLI 에 줄 YouTube 영상 대본 system/user 프롬프트. 장면 배열 + 메타를 출력시킨다.
from typing import Any

_BASE_RULES = """당신은 한국어 YouTube 영상 대본 작가입니다. 주제로 슬라이드쇼형 영상의 대본을 만듭니다.

## 1. 리서치
- WebSearch·WebFetch 로 주제 관련 신뢰할 자료를 수집합니다.
- 사용자가 제공한 참고 링크가 있으면 반영합니다.
- 확인된 사실만 씁니다.

## 2. 구성
- 영상은 장면(scene) 6~12개로 구성합니다.
- 각 장면은 caption(화면에 크게 띄울 짧은 헤드라인, 20자 이내)과 narration(그 장면에서 읽어줄 내레이션, 2~4문장)으로 이뤄집니다.
- 도입(후킹) → 본문 → 마무리(구독 유도) 흐름.
- 자연스러운 한국어 구어체. 문장은 마침표로 끝냅니다.

## 3. 출력 (반드시 마지막 응답에 두 태그를 정확히 포함)
- 태그 안에는 코드 블록 표시(```)를 쓰지 말고 내용만 넣습니다.
<scenes_json>
[{"caption": "...", "narration": "..."}, ...]
</scenes_json>
<video_meta>
{"title": "...", "description": "...", "tags": ["..."]}
</video_meta>
"""

_STYLE_HEADER = "\n## 4. 말투 스타일 (아래 샘플의 어조를 따르세요)\n"


def build_video_system_prompt(style_samples: list[str]) -> str:
    sp = _BASE_RULES
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
git commit -m "feat(content-worker): 영상 대본 프롬프트"
```

---

## Task 3: video_contract.py — 장면·메타 파싱

**Files:**
- Create: `services/content/popory_content/video_contract.py`
- Create: `services/content/tests/test_video_contract.py`

- [ ] **Step 1: 실패 테스트**

`services/content/tests/test_video_contract.py`:

```python
# claude 출력에서 scenes_json·video_meta 추출을 검증.
import pytest
from popory_content.video_contract import parse_video
from popory_content.contract import ContractError


def test_parses_scenes_and_meta():
    text = """잡담
<scenes_json>
[{"caption": "사피엔스란", "narration": "인류의 역사를 다룬 책입니다."}, {"caption": "핵심 메시지", "narration": "허구가 협력을 낳았습니다."}]
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


def test_missing_tags_raises():
    with pytest.raises(ContractError):
        parse_video("장면 없음")


def test_empty_scenes_raises():
    text = '<scenes_json>[]</scenes_json><video_meta>{"title":"t"}</video_meta>'
    with pytest.raises(ContractError):
        parse_video(text)
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video_contract.py -q`
Expected: FAIL (모듈 없음).

- [ ] **Step 3: 구현**

`services/content/popory_content/video_contract.py`:

```python
# claude 출력에서 scenes_json·video_meta 두 태그를 추출·파싱. ContractError 는 contract 모듈 재사용.
import json
import re
from typing import Any

from popory_content.contract import ContractError


def parse_video(text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    scenes_m = re.search(r"<scenes_json>\s*(\[.*\])\s*</scenes_json>", text, re.DOTALL)
    meta_m = re.search(r"<video_meta>\s*(\{.*?\})\s*</video_meta>", text, re.DOTALL)
    if not scenes_m or not meta_m:
        raise ContractError("scenes_json/video_meta 태그를 찾지 못함")
    try:
        scenes = json.loads(scenes_m.group(1).strip())
        meta = json.loads(meta_m.group(1).strip())
    except json.JSONDecodeError as e:
        raise ContractError(f"video JSON 파싱 실패: {e}") from e
    if not isinstance(scenes, list) or not scenes:
        raise ContractError("scenes 가 비어있음")
    for s in scenes:
        if not s.get("caption") or not s.get("narration"):
            raise ContractError("scene 에 caption/narration 누락")
    return scenes, meta
```

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video_contract.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/video_contract.py services/content/tests/test_video_contract.py
git commit -m "feat(content-worker): 영상 대본 파서"
```

---

## Task 4: generate.py — run_claude_cli 추출 (DRY)

**Files:**
- Modify: `services/content/popory_content/generate.py`

영상 대본도 claude CLI를 호출하므로, 기존 `generate()`의 subprocess+재시도 로직을 `run_claude_cli(parse=...)`로 추출해 재사용한다.

- [ ] **Step 1: generate.py 교체**

`services/content/popory_content/generate.py` 전체를 아래로 교체:

```python
# claude CLI(비대화형, Claude Max) 호출 공통 헬퍼 + 블로그 HTML 생성.
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from popory_content.contract import parse_generation, ContractError
from popory_content.prompt import build_system_prompt, build_user_message

CLAUDE_BIN = "/opt/homebrew/bin/claude"
DEFAULT_MODEL = "claude-sonnet-4-6"
TIMEOUT_SECONDS = 1200
MAX_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 10

T = TypeVar("T")


class GenerateError(Exception):
    """생성 실패(CLI 부재/타임아웃/비제로 종료/계약 위반)."""


def run_claude_cli(*, system_prompt: str, user_msg: str, parse: Callable[[str], T],
                   job_id: str = "adhoc", model: str = DEFAULT_MODEL) -> T:
    """claude CLI 호출 → parse(stdout). 타임아웃·비제로종료·파싱실패에 1회 재시도."""
    if not Path(CLAUDE_BIN).exists():
        raise GenerateError(f"claude CLI not found at {CLAUDE_BIN}")
    sys_path = Path(f"/tmp/content_system_{job_id}.txt")
    sys_path.write_text(system_prompt, encoding="utf-8")
    cmd = [
        CLAUDE_BIN, "--print", "--model", model,
        "--allowed-tools", "WebSearch", "WebFetch",
        "--system-prompt-file", str(sys_path), "--output-format", "text",
    ]
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            last = attempt == MAX_ATTEMPTS
            try:
                result = subprocess.run(cmd, input=user_msg, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                if not last:
                    time.sleep(RETRY_BACKOFF_SECONDS); continue
                raise GenerateError(f"claude CLI timeout after {TIMEOUT_SECONDS}s (시도 {attempt})")
            if result.returncode != 0:
                tail = ((result.stderr or "")[-300:] + " || stdout: " + (result.stdout or "")[-600:]).strip()
                if not last:
                    time.sleep(RETRY_BACKOFF_SECONDS); continue
                raise GenerateError(f"claude CLI exit {result.returncode} (시도 {attempt}): {tail}")
            try:
                return parse(result.stdout)
            except Exception as e:  # noqa: BLE001 — 파싱 실패도 재시도 대상
                if not last:
                    time.sleep(RETRY_BACKOFF_SECONDS); continue
                raise GenerateError(f"{e} (시도 {attempt})") from e
    finally:
        sys_path.unlink(missing_ok=True)
    raise GenerateError("run_claude_cli 도달 불가 경로")


def generate(*, topic: str, sources: list[dict[str, Any]], style_samples: list[str],
             model: str = DEFAULT_MODEL, job_id: str = "adhoc") -> tuple[str, dict[str, Any]]:
    sp = build_system_prompt(style_samples)
    um = build_user_message(topic, sources)
    try:
        return run_claude_cli(system_prompt=sp, user_msg=um, parse=parse_generation, job_id=job_id, model=model)
    except ContractError as e:  # 방어적: run_claude_cli 가 이미 GenerateError 로 감쌈
        raise GenerateError(str(e)) from e
```

- [ ] **Step 2: import + 회귀 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && python -c "from popory_content.generate import generate, run_claude_cli, GenerateError; print('ok')" && pytest -q`
Expected: `ok` + 기존 전체 pytest PASS (worker 테스트는 `worker.generate` 를 monkeypatch 하므로 영향 없음).

- [ ] **Step 3: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/generate.py
git commit -m "refactor(content-worker): claude 호출을 run_claude_cli 로 추출 (영상 대본 재사용)"
```

---

## Task 5: video.py — 장면 생성 + 영상 조립

**Files:**
- Create: `services/content/popory_content/video.py`
- Create: `services/content/tests/test_video.py`

- [ ] **Step 1: 구현**

`services/content/popory_content/video.py`:

```python
# 영상 생성 — claude 대본(generate_scenes) + macOS say + ffmpeg 텍스트카드 슬라이드쇼(render_video).
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from popory_content.generate import run_claude_cli
from popory_content.video_prompt import build_video_system_prompt, build_video_user_message
from popory_content.video_contract import parse_video

SAY_BIN = shutil.which("say") or "/usr/bin/say"
FFMPEG_BIN = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE_BIN = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
SAY_VOICE = "Yuna"
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
WIDTH, HEIGHT = 1920, 1080
BG_COLOR = "0x0b1f3a"
TMP = Path("/tmp")


class VideoError(Exception):
    """영상 생성 실패(say/ffmpeg/ffprobe 오류)."""


def generate_scenes(*, topic: str, sources: list[dict[str, Any]], style_samples: list[str],
                    job_id: str = "adhoc") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sp = build_video_system_prompt(style_samples)
    um = build_video_user_message(topic, sources)
    return run_claude_cli(system_prompt=sp, user_msg=um, parse=parse_video, job_id=job_id)


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise VideoError(f"{Path(cmd[0]).name} exit {r.returncode}: {r.stderr[-400:]}")


def _duration(path: Path) -> float:
    r = subprocess.run(
        [FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise VideoError(f"ffprobe exit {r.returncode}: {r.stderr[-300:]}")
    return float(r.stdout.strip())


def render_video(scenes: list[dict[str, Any]], job_id: str = "adhoc") -> Path:
    """장면 배열 → MP4 경로. 각 장면 = 텍스트카드 + 자막 + 내레이션 음성."""
    if not Path(FONT_PATH).exists():
        raise VideoError(f"한국어 폰트 없음: {FONT_PATH}")
    work = TMP / f"video_{job_id}"
    work.mkdir(parents=True, exist_ok=True)
    clip_paths: list[Path] = []
    for i, scene in enumerate(scenes):
        narration = str(scene["narration"]).strip()
        caption = str(scene["caption"]).strip()
        aiff = work / f"{i}.aiff"
        _run([SAY_BIN, "-v", SAY_VOICE, "-o", str(aiff), narration])
        dur = _duration(aiff)
        cap_file = work / f"{i}_cap.txt"
        nar_file = work / f"{i}_nar.txt"
        cap_file.write_text(textwrap.fill(caption, width=18), encoding="utf-8")
        nar_file.write_text(textwrap.fill(narration, width=34), encoding="utf-8")
        clip = work / f"{i}.mp4"
        vf = (
            f"drawtext=fontfile={FONT_PATH}:textfile={cap_file}:fontcolor=white:fontsize=84:"
            f"x=(w-text_w)/2:y=(h-text_h)/2-120:line_spacing=18,"
            f"drawtext=fontfile={FONT_PATH}:textfile={nar_file}:fontcolor=0xdfe7f5:fontsize=46:"
            f"x=(w-text_w)/2:y=h-text_h-120:line_spacing=14"
        )
        _run([
            FFMPEG_BIN, "-y",
            "-f", "lavfi", "-i", f"color=c={BG_COLOR}:s={WIDTH}x{HEIGHT}:d={dur:.3f}",
            "-i", str(aiff),
            "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-shortest", str(clip),
        ])
        clip_paths.append(clip)

    concat_list = work / "concat.txt"
    concat_list.write_text("".join(f"file '{p}'\n" for p in clip_paths), encoding="utf-8")
    out = work / "out.mp4"
    _run([FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
          "-c", "copy", str(out)])
    return out


def make_video(*, topic: str, sources: list[dict[str, Any]], style_samples: list[str],
               job_id: str = "adhoc") -> tuple[Path, list[dict[str, Any]], dict[str, Any]]:
    scenes, meta = generate_scenes(topic=topic, sources=sources, style_samples=style_samples, job_id=job_id)
    mp4 = render_video(scenes, job_id=job_id)
    return mp4, scenes, meta
```

- [ ] **Step 2: 스모크 테스트 작성 (실제 렌더, 짧은 2장면)**

`services/content/tests/test_video.py`:

```python
# render_video 가 실제로 MP4 를 만드는지 2장면 스모크. say/ffmpeg 통합 (느릴 수 있음).
import shutil
import pytest
from popory_content.video import render_video, VideoError, FONT_PATH
from pathlib import Path

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("say") and Path(FONT_PATH).exists()),
    reason="ffmpeg/say/폰트 없음 (CI 등)",
)


def test_render_two_scenes_makes_mp4():
    scenes = [
        {"caption": "테스트 장면 하나", "narration": "이것은 첫 번째 장면입니다."},
        {"caption": "테스트 장면 둘", "narration": "이것은 두 번째 장면입니다."},
    ]
    out = render_video(scenes, job_id="smoketest")
    assert out.exists()
    assert out.stat().st_size > 10000  # 비어있지 않은 MP4
```

- [ ] **Step 3: 스모크 실행 → 통과**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_video.py -q -s`
Expected: 1 passed (수십 초 소요). 실패 시 ffmpeg/say stderr 를 읽고 폰트 경로·명령을 점검(추측 금지). 폰트 경로가 다르면 `FONT_PATH` 를 실제 경로(`ls /System/Library/Fonts/ | grep -i gothic`)로 교정.

- [ ] **Step 4: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/video.py services/content/tests/test_video.py
git commit -m "feat(content-worker): 영상 생성(say+ffmpeg 텍스트카드 슬라이드쇼)"
```

---

## Task 6: Worker API — video 저장/스트리밍

**Files:**
- Modify: `workers/api/src/routes/content_jobs.ts`
- Modify: `workers/api/src/routes/content_jobs.test.ts`

- [ ] **Step 1: 실패 테스트 추가**

`content_jobs.test.ts` 의 `PATCH /api/content/jobs/:id/result` describe 블록 바로 뒤(파일에서 `describe("POST /api/content/jobs — style_profile_id 소유권"` 앞)에 추가:

```ts
describe("video PUT/GET", () => {
  it("워커가 PUT 으로 MP4 저장, 소유자가 GET 으로 받음", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t", platform: "youtube" }) });
    const { id } = await create.json<{ id: string }>();
    const token = await workerToken();
    const bytes = new Uint8Array([0, 1, 2, 3, 4]);
    const put = await SELF.fetch(`https://example.com/api/content/jobs/${id}/video`, {
      method: "PUT", headers: { authorization: `Bearer ${token}`, "content-type": "video/mp4" }, body: bytes,
    });
    expect(put.status).toBe(200);
    const get = await SELF.fetch(`https://example.com/api/content/jobs/${id}/video`, { headers: { cookie: ck } });
    expect(get.status).toBe(200);
    expect(new Uint8Array(await get.arrayBuffer())).toEqual(bytes);
  });

  it("워커 PUT 은 서비스 JWT 없으면 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/jobs/x/video", { method: "PUT", body: new Uint8Array([1]) });
    expect(res.status).toBe(401);
  });

  it("남의 영상 GET 은 404", async () => {
    const a = await userCookie("u1", "u1@e.com");
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: a, "content-type": "application/json" }, body: JSON.stringify({ topic: "t", platform: "youtube" }) });
    const { id } = await create.json<{ id: string }>();
    const token = await workerToken();
    await SELF.fetch(`https://example.com/api/content/jobs/${id}/video`, { method: "PUT", headers: { authorization: `Bearer ${token}`, "content-type": "video/mp4" }, body: new Uint8Array([9]) });
    const b = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/video`, { headers: { cookie: b } });
    expect(res.status).toBe(404);
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `pnpm --filter @popory/api test -- --run content_jobs`
Expected: FAIL (video 라우트 404/405).

- [ ] **Step 3: 라우트 구현**

`workers/api/src/routes/content_jobs.ts` 의 워커 result 핸들러(`app.patch("/api/content/jobs/:id/result", ...)`) 바로 뒤에 추가:

```ts
  app.put("/api/content/jobs/:id/video", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT id FROM content_jobs WHERE id=?").bind(id).first<{ id: string }>();
    if (!row) return c.text("not found", 404);
    const body = await c.req.arrayBuffer();
    await c.env.R2.put(`content/video/${id}.mp4`, body, {
      httpMetadata: { contentType: "video/mp4" },
    });
    return c.json({ ok: true });
  });

  app.get("/api/content/jobs/:id/video", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT id, owner_sub FROM content_jobs WHERE id=?").bind(id).first<{ id: string; owner_sub: string }>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    const obj = await c.env.R2.get(`content/video/${id}.mp4`);
    if (!obj) return c.text("not found", 404);
    return new Response(obj.body, { headers: { "content-type": "video/mp4" } });
  });
```

- [ ] **Step 4: 통과 확인 + 타입체크**

Run: `pnpm --filter @popory/api test -- --run content_jobs 2>&1 | tail -4`
Expected: 21 passed (18 + 3 video).
Run: `pnpm --filter @popory/api typecheck 2>&1 | tail -3`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add workers/api/src/routes/content_jobs.ts workers/api/src/routes/content_jobs.test.ts
git commit -m "feat(content): 영상 PUT/GET 라우트 (R2 video)"
```

---

## Task 7: portal_client put_binary + worker.py 분기

**Files:**
- Modify: `services/content/popory_content/portal_client.py`
- Modify: `services/content/popory_content/worker.py`
- Modify: `services/content/tests/test_worker.py`

- [ ] **Step 1: portal_client 에 put_binary 추가**

`services/content/popory_content/portal_client.py` 의 `patch` 메서드 바로 뒤에 추가:

```python
    def put_binary(self, path: str, *, data: bytes, content_type: str) -> Any:
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.token_provider()}", "Content-Type": content_type}
        try:
            resp = requests.put(url, headers=headers, data=data, timeout=60)
        except requests.RequestException as e:
            raise PortalError(f"network: {e}", exit_code=5) from e
        if resp.status_code >= 400:
            raise PortalError(f"video upload {resp.status_code}: {resp.text[:200]}", exit_code=4)
        return resp.json() if resp.content else {}
```

(파일 상단에 `import requests` 가 이미 있다. 없으면 추가.)

- [ ] **Step 2: worker 테스트 추가 (youtube 분기, 실패 유도)**

`services/content/tests/test_worker.py` 끝에 추가:

```python
def test_youtube_branch_uploads_video_and_reviews(monkeypatch, tmp_path):
    mp4 = tmp_path / "v.mp4"
    mp4.write_bytes(b"\x00\x01\x02")
    monkeypatch.setattr(worker, "make_video", lambda **kw: (mp4, [{"caption": "c", "narration": "n"}], {"title": "T"}))

    class VidClient(FakeClient):
        def __init__(self, claim):
            super().__init__(claim)
            self.put_bin = []
        def put_binary(self, path, *, data, content_type):
            self.put_bin.append((path, len(data), content_type)); return {"ok": True}

    client = VidClient({"job": {"id": "yt1", "topic": "t", "platform": "youtube"}, "sources": [], "style_samples": []})
    assert worker.run_once(client) is True
    assert client.put_bin[0][0] == "/api/content/jobs/yt1/video"
    assert client.put_bin[0][2] == "video/mp4"
    path, body = client.patched[0]
    assert path == "/api/content/jobs/yt1/result"
    assert body["status"] == "review"
```

(기존 blog 테스트들은 platform 키가 없는 job 을 쓰므로 blog 경로로 가야 한다 — Step 3에서 `job.get("platform")` 기본값 처리.)

- [ ] **Step 3: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_worker.py -q`
Expected: FAIL (`worker.make_video` 없음 / youtube 분기 없음).

- [ ] **Step 4: worker.py 분기 구현**

`services/content/popory_content/worker.py` 수정.

import 에 추가:
```python
from popory_content.video import make_video, VideoError
```

`run_once` 를 아래로 교체:
```python
def run_once(client) -> bool:
    """큐에서 한 건 처리. 처리했으면 True, 큐가 비었으면 False."""
    data = client.post("/api/content/jobs/claim", json=None)
    if not data:
        return False
    job = data["job"]
    sources = data.get("sources", [])
    samples = data.get("style_samples", [])
    job_id = job["id"]
    platform = job.get("platform", "naver-blog")
    try:
        if platform == "youtube":
            mp4, scenes, meta = make_video(topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id)
            client.put_binary(f"/api/content/jobs/{job_id}/video", data=mp4.read_bytes(), content_type="video/mp4")
            script = "\n\n".join(f"[{s['caption']}]\n{s['narration']}" for s in scenes)
            _report(client, job_id, {"status": "review", "draft": script, "meta": meta}, "review")
        else:
            draft, meta = generate(topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id)
            _report(client, job_id, {"status": "review", "draft": draft, "meta": meta}, "review")
    except Exception as e:  # noqa: BLE001 — 생성 실패는 failed 로 회신
        _report(client, job_id, {"status": "failed", "error": str(e)[:2000]}, "failed")
    return True
```

(`VideoError`·`make_video` 는 import 로 worker 네임스페이스에 있어 테스트 monkeypatch 가 동작한다. `generate` 도 그대로 import 유지.)

- [ ] **Step 5: 통과 + 전체 회귀**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_worker.py -q`
Expected: 5 passed (기존 4 + youtube 1).
Run: `pytest -q` (video 스모크 포함 시 느림 — 또는 `pytest -q --ignore=tests/test_video.py` 로 빠르게)
Expected: 전체 PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/portal_client.py services/content/popory_content/worker.py services/content/tests/test_worker.py
git commit -m "feat(content-worker): platform=youtube 영상 경로 (대본→MP4→업로드)"
```

---

## Task 8: 포털 — platform 선택 + 영상 플레이어

**Files:**
- Modify: `apps/portal/src/app/(authed)/content/new/NewJobForm.tsx`
- Modify: `apps/portal/src/app/(authed)/content/[id]/page.tsx`

- [ ] **Step 1: NewJobForm 에 platform 선택 추가**

`apps/portal/src/app/(authed)/content/new/NewJobForm.tsx` 수정.

state 추가(`const [styleId, setStyleId] = useState("");` 아래):
```tsx
  const [platform, setPlatform] = useState<"naver-blog" | "youtube">("naver-blog");
```

POST 바디에 platform 추가 — `body: JSON.stringify({` 블록을 아래로:
```tsx
        body: JSON.stringify({
          topic,
          platform,
          style_profile_id: styleId || undefined,
          sources: cleanSources.length ? cleanSources : undefined,
        }),
```

주제 입력 `<label>` 바로 뒤에 platform 선택 UI 추가:
```tsx
      <label className="block">
        <span className="block text-xs font-semibold text-popory-muted mb-1">콘텐츠 종류</span>
        <select value={platform} onChange={(e) => setPlatform(e.target.value as "naver-blog" | "youtube")} className={INPUT}>
          <option value="naver-blog">네이버 블로그 (리치 HTML)</option>
          <option value="youtube">YouTube 영상 (슬라이드쇼)</option>
        </select>
      </label>
```

- [ ] **Step 2: 상세 페이지에 영상 플레이어 분기**

`apps/portal/src/app/(authed)/content/[id]/page.tsx` 수정.

`JobDetail` 인터페이스에 platform 추가:
```tsx
  platform: "naver-blog" | "youtube";
```

review/done 렌더 분기를 아래로 교체(기존 `{(job.status === "review" || job.status === "done") && ( <DraftEditor ... /> )}` 블록):
```tsx
        {(job.status === "review" || job.status === "done") && job.platform === "youtube" && (
          <div className="mt-8 space-y-4">
            <video controls className="w-full rounded-md border border-popory-border bg-black" src={`${API_BASE}/api/content/jobs/${job.id}/video`} />
            <details>
              <summary className="cursor-pointer text-xs text-popory-accent">대본 보기</summary>
              <pre className="mt-2 whitespace-pre-wrap rounded-md border border-popory-border bg-popory-card p-3 text-xs text-popory-fg">{job.draft}</pre>
            </details>
          </div>
        )}

        {(job.status === "review" || job.status === "done") && job.platform !== "youtube" && (
          <DraftEditor
            jobId={job.id}
            initialDraft={job.draft ?? ""}
            done={job.status === "done"}
            seo={meta?.seo ?? null}
            copyright={meta?.copyright ?? null}
            sources={job.sources}
          />
        )}
```

- [ ] **Step 3: 타입체크 + 빌드**

Run: `pnpm --filter @popory/portal typecheck 2>&1 | tail -3`
Expected: clean.
Run: `NEXT_PUBLIC_API_BASE=https://api.poporyfamily.com pnpm --filter @popory/portal build:cf 2>&1 | grep -E "Build completed|error"`
Expected: `Build completed successfully.`

- [ ] **Step 4: Commit**

```bash
cd /Users/daegong/projects/popory
git add "apps/portal/src/app/(authed)/content/new/NewJobForm.tsx" "apps/portal/src/app/(authed)/content/[id]/page.tsx"
git commit -m "feat(portal): YouTube 플랫폼 선택 + 영상 플레이어"
```

---

## Task 9: 검증 + 배포

**Files:** 없음

- [ ] **Step 1: 전체 회귀**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest -q --ignore=tests/test_video.py` → PASS (빠른 회귀).
Run: `cd /Users/daegong/projects/popory && pnpm --filter @popory/api test -- --run 2>&1 | grep Tests` → PASS.
Run: `pnpm -r typecheck 2>&1 | grep -E "Done|error"` → 6 Done.

- [ ] **Step 2: prod 배포 (사용자 확인 후)**

```bash
cd /Users/daegong/projects/popory/workers/api
pnpm exec wrangler deploy --env prod --config ../../infra/wrangler/api.toml
NEXT_PUBLIC_API_BASE=https://api.poporyfamily.com pnpm --filter @popory/portal build:cf
pnpm exec wrangler pages deploy /Users/daegong/projects/popory/apps/portal/.vercel/output/static --project-name popory-portal --branch main
```

- [ ] **Step 3: 워커 재시작 (새 모듈 로드)**

```bash
launchctl kickstart -k "gui/$(id -u)/com.popory.content-worker"
```

- [ ] **Step 4: e2e (휴먼)**

포털 새 작업 → 콘텐츠 종류 "YouTube 영상" → 주제 입력 → 워커가 대본·TTS·ffmpeg(수 분) → review → 상세에서 영상 재생.

---

## Self-Review (작성자 체크)

**Spec coverage:**
- §5.1 platform enum → Task 1. ✅
- §5.2 영상 대본 프롬프트 → Task 2. ✅
- §5.3 대본 파서 → Task 3. ✅
- §5.4 video.py(render_video) + generate_scenes → Task 5 (run_claude_cli 는 Task 4). ✅
- §5.5 워커 분기 → Task 7. ✅
- §5.6 PUT/GET video → Task 6. ✅
- §5.7 포털 platform 선택 + 영상 플레이어 → Task 8. ✅
- §7 에러(VideoError·failed 회신·업로드 실패 swallow) → Task 5·7(_report 재사용). ✅
- §8 테스트 → 각 Task. ✅

**Placeholder scan:** 모든 단계 실제 코드·명령. ffmpeg/say 명령 구체화. 폰트 경로 미존재 시 교정 지시 명시(추측 아님). ✅

**Type consistency:** `run_claude_cli(parse=...)` 시그니처를 Task 4 정의·Task 5(video.py)에서 동일 사용. `make_video`/`render_video`/`generate_scenes` 명칭 Task 5 정의·Task 7 사용 일치. `put_binary(path, data, content_type)` Task 7 정의·사용 일치. PUT/GET R2 키 `content/video/{id}.mp4` Task 6 일관. job `platform` 키 Task 1(스키마)·6·7·8 일관. worker `_report`·`generate` 기존 유지. ✅
