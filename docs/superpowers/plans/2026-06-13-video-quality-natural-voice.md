# YouTube 영상 품질·자연음성 개선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** popory YouTube 영상 생성을 무료 수단만으로 더 자연스럽게 — Chirp3-HD 음성·장면 통째 합성·켄번스 모션·크로스페이드·BGM·음량정규화·이미지 톤 일관성.

**Architecture:** 변경은 로컬 워커 `services/content`에 집중. `tts.py`(Chirp3-HD + `[pause]` markup + speakingRate), `video.py`(합성·렌더 단위를 문장→장면, zoompan/xfade, BGM·loudnorm 마스터 패스), `video_prompt.py`(스타일 접미사), `options.py`(VOICE 매핑). Worker API·포털·D1 무변경. ffmpeg는 현 빌드가 zoompan/xfade/loudnorm/amix 지원함을 확인함(libass/freetype 없음 → 자막은 Pillow 유지).

**Tech Stack:** Python 3.11, Google Cloud TTS REST, ffmpeg(libx264), Pillow, pytest + responses.

---

## File Structure

- `services/content/popory_content/tts.py` — 수정. Chirp3-HD markup 합성. 자체 문장분할(`_split_for_pauses`).
- `services/content/popory_content/options.py` — 수정. `VOICE` 값을 Chirp3-HD 보이스명으로.
- `services/content/popory_content/video_prompt.py` — 수정. 영상 단위 스타일 접미사 부착.
- `services/content/popory_content/video.py` — 수정. 장면 단위 합성·렌더, zoompan, xfade 조인, BGM+loudnorm 마스터.
- `services/content/assets/bgm/.gitkeep` + `services/content/assets/bgm/README.md` — 신규. 사용자가 CC0 음원 배치할 곳.
- 테스트: `tests/test_tts.py`, `tests/test_options.py`, `tests/test_video_prompt.py`, `tests/test_video.py` — 수정/추가.

**작업 디렉토리:** 모든 `pytest`·`git` 명령은 `services/content`에서 실행. 워커 venv는 `services/content/.venv`. 실행 전 `cd services/content && source .venv/bin/activate` 가정.

---

### Task 1: 이미지 스타일 접미사 (video_prompt.py)

영상 단위 공통 스타일 토큰을 모든 장면 `image_prompt` 끝에 붙이도록 claude에 지시 → 장면 간 톤 통일. 순수 프롬프트 문자열 변경이라 가장 안전.

**Files:**
- Modify: `services/content/popory_content/video_prompt.py:16` (가로형 rules), `:70` (쇼츠 rules)
- Test: `services/content/tests/test_video_prompt.py`

- [ ] **Step 1: Write the failing test**

`tests/test_video_prompt.py`에 추가:

```python
def test_system_prompt_demands_consistent_style_suffix():
    from popory_content.video_prompt import build_video_system_prompt
    sp = build_video_system_prompt([], scene_count=8, image_style_kw="watercolor painting")
    # 모든 장면이 같은 톤이 되도록 '일관된'/'동일' 류 지시가 image_prompt 규칙에 있어야 한다
    assert "일관" in sp
    assert "watercolor painting" in sp
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_video_prompt.py::test_system_prompt_demands_consistent_style_suffix -v`
Expected: FAIL (`assert "일관" in sp` → AssertionError)

- [ ] **Step 3: Write minimal implementation**

`video_prompt.py`의 `_rules` 함수에서 image_prompt 설명 줄(현재 `:16`)을 아래로 교체:

```python
- 각 장면에 image_prompt(그 장면을 묘사하는 영어 이미지 생성 프롬프트, 한 문장. {image_style_kw} 스타일이며 이미지 안에 글자/텍스트는 넣지 않습니다)도 포함합니다.
- 모든 장면의 image_prompt는 색감·조명·분위기를 일관되게 유지해 한 영상처럼 보이게 합니다(같은 {image_style_kw} 톤 유지).
```

`_shorts_rules`의 대응 줄(현재 `:70`)도 동일하게 일관성 문장 한 줄 추가:

```python
- 각 장면에 image_prompt(영어, {image_style_kw} 스타일, 글자 없음)도 포함합니다.
- 모든 장면의 image_prompt는 색감·조명·분위기를 일관되게 유지합니다(같은 {image_style_kw} 톤).
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_video_prompt.py -v`
Expected: PASS (기존 + 신규 모두)

- [ ] **Step 5: Commit**

```bash
git add services/content/popory_content/video_prompt.py services/content/tests/test_video_prompt.py
git commit -m "feat(content): 영상 장면 이미지 톤 일관성 지시 추가"
```

---

### Task 2: Chirp3-HD 음성 + 호흡 markup + 속도 (tts.py, options.py)

Neural2 → Chirp3-HD 교체, 문장 사이 `[pause short]` markup 주입, `speakingRate=0.96`. 2026-06-13 검증: ko-KR Chirp3-HD 30종 제공, `input.markup`·speakingRate 동작.

**Files:**
- Modify: `services/content/popory_content/tts.py` (전체 `synthesize` + 신규 `_split_for_pauses`)
- Modify: `services/content/popory_content/options.py:6` (`VOICE`)
- Test: `services/content/tests/test_tts.py`, `services/content/tests/test_options.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_tts.py`에 추가:

```python
def test_split_for_pauses_inserts_pause_markup():
    from popory_content.tts import _split_for_pauses
    out = _split_for_pauses("첫째 문장입니다. 둘째 문장이에요!")
    assert out == "첫째 문장입니다. [pause short] 둘째 문장이에요!"


@responses.activate
def test_synthesize_uses_markup_and_rate(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    responses.add(responses.POST, tts.TTS_URL,
                  json={"audioContent": base64.b64encode(b"x").decode()}, status=200)
    tts.synthesize("첫 문장. 둘째 문장.", voice="ko-KR-Chirp3-HD-Aoede")
    import json as _json
    body = responses.calls[0].request.body
    payload = _json.loads(body if isinstance(body, str) else body.decode())
    assert payload["input"].get("markup")  # text 아니라 markup 사용
    assert "[pause short]" in payload["input"]["markup"]
    assert payload["audioConfig"]["speakingRate"] == 0.96
    assert payload["voice"]["name"] == "ko-KR-Chirp3-HD-Aoede"
```

`tests/test_options.py`에 추가:

```python
def test_voice_map_uses_chirp3hd():
    from popory_content.options import VOICE
    assert VOICE["female-calm"] == "ko-KR-Chirp3-HD-Aoede"
    assert VOICE["female-bright"] == "ko-KR-Chirp3-HD-Leda"
    assert VOICE["male"] == "ko-KR-Chirp3-HD-Charon"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tts.py::test_synthesize_uses_markup_and_rate tests/test_options.py::test_voice_map_uses_chirp3hd -v`
Expected: FAIL (`_split_for_pauses` 미정의 / markup 없음 / VOICE 값 Neural2)

- [ ] **Step 3: Write implementation**

`tts.py`의 `synthesize` 위에 헬퍼 추가하고 `synthesize` 본문 교체:

```python
import re

_SENT = re.compile(r"(?<=[.?!])\s+")


def _split_for_pauses(text: str) -> str:
    """문장 사이에 Chirp3-HD 네이티브 [pause short] 마크업을 끼워 호흡을 만든다."""
    parts = [p.strip() for p in _SENT.split(text.strip()) if p.strip()]
    return " [pause short] ".join(parts) if parts else text.strip()


def synthesize(text: str, voice: str = "ko-KR-Chirp3-HD-Aoede") -> bytes | None:
    key = os.environ.get("GOOGLE_TTS_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            f"{TTS_URL}?key={key}",
            json={
                "input": {"markup": _split_for_pauses(text)},
                "voice": {"languageCode": LANGUAGE, "name": voice},
                "audioConfig": {"audioEncoding": "MP3", "speakingRate": 0.96},
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

기존 `synthesize`의 기본 인자 `voice="ko-KR-Neural2-A"`도 `"ko-KR-Chirp3-HD-Aoede"`로 바뀜(위 시그니처 반영).

`options.py:6`의 `VOICE`를 교체:

```python
VOICE = {"female-calm": "ko-KR-Chirp3-HD-Aoede", "female-bright": "ko-KR-Chirp3-HD-Leda", "male": "ko-KR-Chirp3-HD-Charon"}
```

`video.py`의 `render_video`/`make_video` 기본 인자 `voice="ko-KR-Neural2-A"`(현재 `:115`, `:162`)도 `"ko-KR-Chirp3-HD-Aoede"`로 교체(워커는 항상 VOICE 매핑을 넘기므로 동작 영향은 기본값 정합 목적).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tts.py tests/test_options.py -v`
Expected: PASS (기존 `test_synthesize_uses_voice` 포함 — voice는 여전히 body에 들어감)

- [ ] **Step 5: Commit**

```bash
git add services/content/popory_content/tts.py services/content/popory_content/options.py services/content/popory_content/video.py services/content/tests/test_tts.py services/content/tests/test_options.py
git commit -m "feat(content): TTS Chirp3-HD + 호흡 markup + 속도 0.96"
```

---

### Task 3: 장면 통째 합성 + 헤드라인 렌더 (video.py)

`render_video` 루프를 문장 단위 → 장면 단위로. 장면 내레이션 전체를 1회 TTS 합성(억양 연속) + 헤드라인(caption)만 카드에 표시. `_split_sentences`는 이 변경으로 미사용 → 제거(규칙 3 orphan 정리). 이 시점 조인은 기존 `concat -c copy` 유지(모션·전환은 Task 4·5).

**Files:**
- Modify: `services/content/popory_content/video.py` (`render_video` `:114-156`, `_split_sentences` `:109-111` 제거)
- Test: `services/content/tests/test_video.py` (`test_split_sentences` 제거, 스모크 갱신)

- [ ] **Step 1: Update tests (failing)**

`tests/test_video.py`에서 `test_split_sentences`(`:26-29`) 삭제. 스모크 테스트를 장면당 클립 1개를 검증하도록 교체:

```python
@pytest.mark.skipif(not _HAS_TOOLS, reason="ffmpeg/say/폰트 없음 (CI 등)")
def test_render_two_scenes_makes_mp4(tmp_path, monkeypatch):
    import popory_content.video as v
    monkeypatch.setattr(v, "TMP", tmp_path)
    scenes = [
        {"caption": "테스트 장면 하나", "narration": "이것은 첫 문장입니다. 두 번째 문장이에요."},
        {"caption": "테스트 장면 둘", "narration": "이것은 다른 장면입니다. 마지막 문장입니다."},
    ]
    out = render_video(scenes, job_id="smoketest")
    assert out.exists() and out.stat().st_size > 10000
    # 장면당 클립 1개(문장 분할 안 함): scene_*.mp4 가 정확히 2개
    work = tmp_path / "video_smoketest"
    clips = sorted(work.glob("scene_*.mp4"))
    assert len(clips) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_video.py -v`
Expected: `test_split_sentences` 임포트/수집 단계는 OK(삭제됨). 스모크는 로컬에서 FAIL(아직 `scene_*.mp4` 네이밍 아님), CI에선 skip.

- [ ] **Step 3: Write implementation**

`video.py`에서 `_split_sentences`(`:109-111`) 삭제. `render_video`(`:114-156`)를 교체:

```python
def render_video(scenes: list[dict[str, Any]], job_id: str = "adhoc",
                 image_fetcher: Any = None, voice: str = "ko-KR-Chirp3-HD-Aoede",
                 portrait: bool = False) -> Path:
    """장면당 클립 1개(배경+헤드라인+장면 내레이션 통째 합성) → concat MP4."""
    if not Path(FONT_PATH).exists():
        raise VideoError(f"한국어 폰트 없음: {FONT_PATH}")
    work = TMP / f"video_{job_id}"
    work.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for i, scene in enumerate(scenes):
        caption = str(scene["caption"]).strip()
        narration = str(scene["narration"]).strip() or " "
        bg_bytes = None
        prompt = scene.get("image_prompt")
        if image_fetcher and prompt:
            try:
                bg_bytes = image_fetcher(prompt)
            except Exception:  # noqa: BLE001 — 이미지 실패는 단색 폴백
                bg_bytes = None
        audio_bytes = synthesize(narration, voice=voice)
        if audio_bytes:
            audio = work / f"{i}.mp3"
            audio.write_bytes(audio_bytes)
        else:
            audio = work / f"{i}.aiff"
            _run([SAY_BIN, "-v", SAY_VOICE, "-o", str(audio), narration])
        dur = _duration(audio)
        png = work / f"{i}.png"
        _render_card(caption, "", png, bg_image_bytes=bg_bytes, portrait=portrait)
        clip = work / f"scene_{i}.mp4"
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

`_render_card`는 그대로 사용(subtitle="" → 중앙 자막 비고 헤드라인만 좌상단 표시). 시그니처 불변이라 기존 `_render_card` 테스트도 유지.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_video.py -v`
Expected: 로컬 PASS(스모크 포함, `scene_*.mp4` 2개). CI는 스모크 skip.

- [ ] **Step 5: Commit**

```bash
git add services/content/popory_content/video.py services/content/tests/test_video.py
git commit -m "feat(content): 장면 통째 TTS 합성 + 헤드라인 단일 자막"
```

---

### Task 4: 켄번스 모션 (zoompan)

정지 `-loop 1` 장면 클립에 느린 줌인. 순수 헬퍼 `_zoompan_filter`로 필터 문자열을 만들고 단위 테스트.

**Files:**
- Modify: `services/content/popory_content/video.py` (`_zoompan_filter` 신규, `render_video` 클립 ffmpeg 명령)
- Test: `services/content/tests/test_video.py`

- [ ] **Step 1: Write the failing test**

```python
def test_zoompan_filter_landscape_and_portrait():
    from popory_content.video import _zoompan_filter
    fl = _zoompan_filter(3.0, portrait=False)
    assert "zoompan" in fl and "s=1920x1080" in fl and "fps=30" in fl
    fp = _zoompan_filter(3.0, portrait=True)
    assert "s=1080x1920" in fp
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_video.py::test_zoompan_filter_landscape_and_portrait -v`
Expected: FAIL (`_zoompan_filter` 미정의)

- [ ] **Step 3: Write implementation**

`video.py`에 헬퍼 추가(예: `_render_card` 아래):

```python
def _zoompan_filter(dur: float, portrait: bool = False) -> str:
    """정지 이미지에 느린 줌인(켄번스). 입력을 1.2배로 키워 떨림을 줄인다."""
    w, h = (PORTRAIT_W, PORTRAIT_H) if portrait else (LANDSCAPE_W, LANDSCAPE_H)
    frames = max(1, round(dur * 30))
    up_w, up_h = int(w * 1.2), int(h * 1.2)
    return (
        f"scale={up_w}:{up_h},"
        f"zoompan=z='min(zoom+0.0006,1.12)':d={frames}"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=30,format=yuv420p"
    )
```

`render_video`의 클립 생성 `_run([...])`(Task 3에서 작성한 정지 명령)을 zoompan 버전으로 교체:

```python
        clip = work / f"scene_{i}.mp4"
        _run([
            FFMPEG_BIN, "-y", "-loop", "1", "-i", str(png), "-i", str(audio),
            "-filter_complex", f"[0:v]{_zoompan_filter(dur, portrait)}[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-t", f"{dur:.3f}",
            "-c:a", "aac", "-shortest", str(clip),
        ])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_video.py -v`
Expected: PASS(단위). 로컬 스모크도 PASS(움직이는 클립 생성). CI 스모크 skip.

- [ ] **Step 5: Commit**

```bash
git add services/content/popory_content/video.py services/content/tests/test_video.py
git commit -m "feat(content): 장면에 켄번스 줌인 모션(zoompan)"
```

---

### Task 5: 크로스페이드 조인 (xfade)

`concat -c copy` → 장면 간 0.4초 디졸브. 누적 오프셋 계산이 핵심이라 순수 헬퍼 `_xfade_graph`로 분리해 단위 테스트.

**Files:**
- Modify: `services/content/popory_content/video.py` (`_xfade_graph` 신규, `render_video` 조인부)
- Test: `services/content/tests/test_video.py`

- [ ] **Step 1: Write the failing test**

```python
def test_xfade_graph_offsets_and_labels():
    from popory_content.video import _xfade_graph
    graph, vlabel, alabel = _xfade_graph([3.0, 4.0, 5.0], td=0.4)
    # 첫 전환 offset = 3.0-0.4 = 2.6, 둘째 = (3.0-0.4)+(4.0-0.4)=2.6+3.6=6.2
    assert "offset=2.600" in graph
    assert "offset=6.200" in graph
    assert "acrossfade=d=0.4" in graph
    assert vlabel == "v2" and alabel == "a2"


def test_xfade_graph_single_clip_is_empty():
    from popory_content.video import _xfade_graph
    graph, vlabel, alabel = _xfade_graph([3.0], td=0.4)
    assert graph == "" and vlabel == "0:v" and alabel == "0:a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_video.py::test_xfade_graph_offsets_and_labels tests/test_video.py::test_xfade_graph_single_clip_is_empty -v`
Expected: FAIL (`_xfade_graph` 미정의)

- [ ] **Step 3: Write implementation**

`video.py`에 헬퍼 추가:

```python
def _xfade_graph(durations: list[float], td: float = 0.4) -> tuple[str, str, str]:
    """클립 길이 배열로 xfade/acrossfade filter_complex 그래프를 만든다.
    반환: (filter_complex 문자열, 최종 비디오 라벨, 최종 오디오 라벨)."""
    if len(durations) <= 1:
        return "", "0:v", "0:a"
    parts: list[str] = []
    v_prev, a_prev = "0:v", "0:a"
    total = durations[0]
    for i in range(1, len(durations)):
        off = total - td
        v_out, a_out = f"v{i}", f"a{i}"
        parts.append(
            f"[{v_prev}][{i}:v]xfade=transition=fade:duration={td}:offset={off:.3f}[{v_out}]"
        )
        parts.append(f"[{a_prev}][{i}:a]acrossfade=d={td}[{a_out}]")
        v_prev, a_prev = v_out, a_out
        total += durations[i] - td
    return ";".join(parts), v_prev, a_prev
```

`render_video`의 조인부(Task 3의 concat 블록)를 교체:

```python
    durations = [_duration(c) for c in clips]
    out = work / "out.mp4"
    if len(clips) == 1:
        shutil.copy(clips[0], out)
        return out
    graph, vlabel, alabel = _xfade_graph(durations)
    cmd = [FFMPEG_BIN, "-y"]
    for c in clips:
        cmd += ["-i", str(c)]
    cmd += [
        "-filter_complex", graph,
        "-map", f"[{vlabel}]", "-map", f"[{alabel}]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", str(out),
    ]
    _run(cmd)
    return out
```

`concat.txt` 작성 줄은 제거(미사용 orphan). `shutil`은 이미 import됨(`:3`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_video.py -v`
Expected: PASS(단위 + 로컬 스모크 — 2장면 크로스페이드 MP4 생성). CI 스모크 skip.

- [ ] **Step 5: Commit**

```bash
git add services/content/popory_content/video.py services/content/tests/test_video.py
git commit -m "feat(content): 장면 전환 크로스페이드(xfade/acrossfade)"
```

---

### Task 6: BGM + 음량정규화 마스터 패스

조인된 영상에 CC0 BGM(있으면) `amix` + `loudnorm -14 LUFS`. BGM 선택은 결정적(`zlib.crc32`). 파일 없으면 loudnorm만.

**Files:**
- Create: `services/content/assets/bgm/.gitkeep`, `services/content/assets/bgm/README.md`
- Modify: `services/content/popory_content/video.py` (`BGM_DIR` 상수, `_pick_bgm`, `_master_audio`, `render_video` 말미)
- Test: `services/content/tests/test_video.py`

- [ ] **Step 1: Write the failing test**

```python
def test_pick_bgm_none_when_empty(tmp_path):
    from popory_content.video import _pick_bgm
    assert _pick_bgm(tmp_path, "job1") is None


def test_pick_bgm_deterministic(tmp_path):
    from popory_content.video import _pick_bgm
    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "b.mp3").write_bytes(b"y")
    first = _pick_bgm(tmp_path, "job1")
    assert first is not None
    assert first == _pick_bgm(tmp_path, "job1")  # 같은 job_id → 같은 선택
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_video.py::test_pick_bgm_none_when_empty tests/test_video.py::test_pick_bgm_deterministic -v`
Expected: FAIL (`_pick_bgm` 미정의)

- [ ] **Step 3: Write implementation**

`video.py` 상단 import에 `import zlib` 추가. 상수부(`TMP = Path("/tmp")` 아래)에 추가:

```python
BGM_DIR = Path(__file__).resolve().parent.parent / "assets" / "bgm"
```

헬퍼 추가:

```python
def _pick_bgm(bgm_dir: Path, job_id: str) -> Path | None:
    """assets/bgm/*.mp3 중 job_id로 결정적 선택. 없으면 None(BGM 생략)."""
    if not bgm_dir.is_dir():
        return None
    files = sorted(bgm_dir.glob("*.mp3"))
    if not files:
        return None
    return files[zlib.crc32(job_id.encode()) % len(files)]


def _master_audio(src: Path, out: Path, bgm: Path | None) -> None:
    """loudnorm(-14 LUFS) + (BGM 있으면) amix. 비디오는 copy."""
    if bgm:
        cmd = [
            FFMPEG_BIN, "-y", "-i", str(src), "-stream_loop", "-1", "-i", str(bgm),
            "-filter_complex",
            "[1:a]volume=0.15[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[mix];"
            "[mix]loudnorm=I=-14:TP=-1.5:LRA=11[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-shortest", str(out),
        ]
    else:
        cmd = [
            FFMPEG_BIN, "-y", "-i", str(src),
            "-filter_complex", "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", str(out),
        ]
    _run(cmd)
```

`render_video`의 조인부(Task 5에서 작성한 `durations = ...`부터 끝까지)를 아래 **최종본**으로 교체. 조인 결과는 `joined.mp4`로 통일하고, 단일·다중 모두 마지막에 `_master_audio`로 `out.mp4`를 만든다:

```python
    durations = [_duration(c) for c in clips]
    joined = work / "joined.mp4"
    if len(clips) == 1:
        shutil.copy(clips[0], joined)
    else:
        graph, vlabel, alabel = _xfade_graph(durations)
        cmd = [FFMPEG_BIN, "-y"]
        for c in clips:
            cmd += ["-i", str(c)]
        cmd += [
            "-filter_complex", graph,
            "-map", f"[{vlabel}]", "-map", f"[{alabel}]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", str(joined),
        ]
        _run(cmd)
    out = work / "out.mp4"
    _master_audio(joined, out, _pick_bgm(BGM_DIR, job_id))
    return out
```

스모크 테스트(`test_render_two_scenes_makes_mp4`)는 여전히 `out.mp4`를 최종 산출물로, `scene_*.mp4` 2개를 검증하므로 그대로 통과한다.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_video.py -v`
Expected: PASS. 로컬 스모크: BGM 없으면 loudnorm만 적용된 `out.mp4` 생성.

- [ ] **Step 5: Create assets scaffold**

`services/content/assets/bgm/.gitkeep` — 빈 파일.

`services/content/assets/bgm/README.md`:

```markdown
# 영상 BGM (무료 CC0 음원만)

이 폴더의 `*.mp3`가 생성 영상에 배경음악으로 깔립니다(볼륨 0.15, loudnorm 적용). 파일이 없으면 BGM 없이 음량정규화만 됩니다.

## 음원 출처 (무료·저작권 안전)
- YouTube 오디오 보관함 (studio.youtube.com → 오디오 보관함). 수익화·저작권 안전.
- Pixabay Music (pixabay.com/music) — CC0.
- incompetech.com (Kevin MacLeod) — CC-BY, 영상 설명란에 출처 표기 필요.

## 주의
- 저작권 불명 음원 금지. 반드시 CC0 또는 사용 허가된 음원만.
- 파일명 자유. 여러 개 두면 작업마다 결정적으로 하나가 선택됩니다.
```

- [ ] **Step 6: Commit**

```bash
git add services/content/popory_content/video.py services/content/tests/test_video.py services/content/assets/bgm/.gitkeep services/content/assets/bgm/README.md
git commit -m "feat(content): BGM(amix)+음량정규화(loudnorm) 마스터 패스"
```

---

### Task 7: 전체 회귀 + 로컬 스모크 + 워커 정합 확인

워커(`worker.py`)는 `VOICE` 매핑·`make_video`만 호출하므로 코드 변경 불필요. 전체 테스트와 실제 영상 1건 생성으로 끝단 확인.

**Files:**
- (변경 없음 — 검증만)

- [ ] **Step 1: 전체 테스트**

Run: `pytest -q`
Expected: PASS. 기존 + 신규 전부 녹색. ffmpeg 의존 스모크는 로컬에서 실행(있으면), CI/툴 없으면 skip.

- [ ] **Step 2: 로컬 실제 영상 스모크(수동)**

`say`+`ffmpeg`로 BGM 없이 2장면 영상이 만들어지고, 음량정규화 통과를 확인:

Run:
```bash
python -c "
from popory_content.video import render_video
s=[{'caption':'첫 헤드라인','narration':'첫 문장입니다. 둘째 문장이에요.'},
   {'caption':'둘째 헤드라인','narration':'다른 장면입니다. 마지막 문장입니다.'}]
p=render_video(s, job_id='manualsmoke')
print('OK', p, p.stat().st_size)
"
```
Expected: `OK /tmp/video_manualsmoke/out.mp4 <size>` (수만 바이트 이상). 재생 시 줌인·디졸브·정규화된 음량 확인.

- [ ] **Step 3: 워커 재시작 안내(배포 시)**

워커는 launchd 상주(editable install). 배포 시 코드 반영:
```bash
launchctl kickstart -k gui/$(id -u)/com.popory.content-worker
```
(이 플랜 실행 단계에선 실행하지 않음 — prod 반영은 사용자 승인 후.)

- [ ] **Step 4: 최종 커밋(필요 시)**

검증만이면 커밋 없음. 스모크 중 수정이 생기면 해당 Task로 돌아가 수정·재실행.

---

## 배포 메모 (실행 후, 사용자 승인 시)

- 로컬 워커만 변경 → prod 배포는 워커 재시작 1줄(`launchctl kickstart`). API/포털/D1 배포 불필요.
- BGM은 사용자가 `services/content/assets/bgm/`에 CC0 mp3 배치 후 워커 재시작 시 즉시 반영.
- 효과는 다음 영상 작업부터.
