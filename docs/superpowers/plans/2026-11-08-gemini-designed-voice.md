# Gemini 설계 음성 도입 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 롱폼·쇼츠 남성 기본 음성을 Gemini 설계 음성 `voice_s8vzho2m0lq6` 으로 바꾸고, 짧은 연출 지시·만료 경고·재생성 도구를 갖춘다.

**Architecture:** `gemini_tts.payload` 가 화자 문자열이 `voice_` 로 시작하면 `voiceConfig.voice` 로 보낸다. 기본 음성·만료일은 `options.py` 한 곳에 두고, 워커가 영상 작업마다 만료일을 확인해 30일 안이면 실패 로그로 남긴다(포털 오류 화면·헬스체크로 전파). 재생성은 독립 CLI 도구다.

**Tech Stack:** Python 3.11, requests, pytest(`services/content`, `services/healthcheck`).

**Spec:** `docs/superpowers/specs/2026-11-08-gemini-designed-voice-design.md`

## Global Constraints

- 설계 음성 ID `voice_s8vzho2m0lq6`, 기본 음성 문자열 `gemini-3.8-flash-tts/voice_s8vzho2m0lq6`, 만료일 `2027-11-08`, 경고 시작 30일 전.
- 기본 연출 지시는 정확히 `Calm, warm and conversational.` — env `POPORY_GEMINI_TTS_STYLE` 덮어쓰기 유지.
- 새 로그 상태는 정확히 `gemini_voice_expiry_failed`.
- 새 소스 파일 첫 줄은 역할을 설명하는 한국어 한 줄 주석(AGENTS.md 규칙 6).
- 커밋 메시지는 Conventional Commits 프리픽스 + 한국어 제목·본문(한다체), 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- 테스트는 실제 Gemini·텔레그램·포털에 닿으면 안 된다 — HTTP 는 monkeypatch 로 바꾼다. content 테스트는 `tests/conftest.py` 의 `_no_real_alerts`·`_isolate_logs_dir` 픽스처에 기댄다.
- 테스트 실행은 워크트리의 `services/content`(또는 `services/healthcheck`)에서 `env -i PATH=/opt/homebrew/bin:/usr/bin:/bin LANG=en_US.UTF-8 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/daegong/projects/popory/services/<서비스>/.venv/bin/python -m pytest -o addopts= -q -p no:cacheprovider <대상>`.

## Review Focus

- 설계 음성이 삭제·만료돼 API 가 404 를 줄 때 — 안내 문구가 모델만이 아니라 설계 음성 만료를 가리켜야 한다(Task 1 `test_explain_404_mentions_designed_voice`).
- 만료일이 오늘이거나 지난 뒤 — 경고가 멈추지 않고 '만료됨'으로 남아야 한다(Task 3 `test_voice_expiry_logs_after_expiry`).
- 프리셋·여성·알 수 없는 음성 — 만료 경고가 나오면 안 된다(Task 3 `test_voice_expiry_ignores_voices_without_expiry`).
- env 로 연출 지시를 덮어쓴 경우 — 짧은 기본값 검사가 env 값과 섞이지 않게 기본값 상수를 따로 검사한다(Task 2).
- 헬스체크가 새 상태를 놓치는 경우 — 마커는 반드시 `"status": "..."` 형태여야 부분일치 오탐이 없다(Task 3 `test_scan_log_markers_flags_designed_voice_expiry`).

---

### Task 1: 요청 본문이 설계 음성 ID 를 보낸다

**Files:**
- Modify: `services/content/popory_content/gemini_tts.py` — `payload()`(160행 근처), `_explain()`(404 안내)
- Test: `services/content/tests/test_gemini_tts.py`

**Interfaces:**
- Produces: `payload(text: str, speaker: str, style: str = STYLE) -> dict` — `speaker` 가 `voice_` 로 시작하면 `generationConfig.speechConfig.voiceConfig == {"voice": speaker}`, 아니면 지금처럼 `{"prebuiltVoiceConfig": {"voiceName": speaker}}`. 본문 텍스트 형식(`### DIRECTOR'S NOTES` / `#### TRANSCRIPT`)은 그대로.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_payload_uses_voice_id_for_designed_voice():
    body = g.payload("대본입니다.", "voice_s8vzho2m0lq6", style="calm")
    assert body["generationConfig"]["speechConfig"]["voiceConfig"] == {"voice": "voice_s8vzho2m0lq6"}
    assert body["contents"][0]["parts"][0]["text"] == "### DIRECTOR'S NOTES\ncalm\n\n#### TRANSCRIPT\n대본입니다."


def test_synthesize_scene_sends_designed_voice_to_model_url(monkeypatch):
    # 기존 test_synthesize_scene_returns_pcm_and_records_usage 와 같은 준비(키·가짜 응답·장부)를 따른다.
    # 가짜 post 가 받은 url·json 을 기록해 두고:
    #   url 에 "gemini-3.8-flash-tts" 가 들어 있고
    #   json["generationConfig"]["speechConfig"]["voiceConfig"] == {"voice": "voice_s8vzho2m0lq6"}
    g.synthesize_scene("대본입니다.", "gemini-3.8-flash-tts/voice_s8vzho2m0lq6")


def test_explain_404_mentions_designed_voice():
    msg = g._explain(404, "NOT_FOUND")
    assert "설계 음성" in msg and "모델" in msg
```

- [ ] **Step 2: 실패를 확인한다**

Run: `... -m pytest -o addopts= -q -p no:cacheprovider tests/test_gemini_tts.py -k "designed_voice or explain_404"`
Expected: 3 failed(voiceConfig 에 prebuiltVoiceConfig 가 있음, 404 안내에 '설계 음성' 없음)

- [ ] **Step 3: `payload()` 분기와 `_explain()` 404 안내를 고친다**

404 안내는 `모델 이름 또는 설계 음성(voice_…)을 찾을 수 없음 — 모델 ID 변경·설계 음성 만료(tools/design_voice.py) 확인`.

- [ ] **Step 4: 통과를 확인한다**

Run: `... -m pytest -o addopts= -q -p no:cacheprovider tests/test_gemini_tts.py`
Expected: 전부 PASS(기존 `test_payload_separates_direction_from_transcript` 포함)

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/gemini_tts.py services/content/tests/test_gemini_tts.py
git commit -m "feat(tts): Gemini 요청이 설계 음성 ID(voice_…)를 voiceConfig.voice 로 보낸다" -m "..." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: 기본 남성 음성을 설계 음성으로, 연출 지시를 짧게

**Files:**
- Modify: `services/content/popory_content/options.py:6-10` — `VOICE["male"]` 와 주석(이력·근거·되돌리는 법)
- Modify: `services/content/popory_content/gemini_tts.py:26-35` — `STYLE` 기본값과 주석
- Test: `services/content/tests/test_options.py`, `services/content/tests/test_gemini_tts.py`

**Interfaces:**
- Consumes: Task 1 의 `payload()` 분기.
- Produces: `options.VOICE["male"] == "gemini-3.8-flash-tts/voice_s8vzho2m0lq6"`, `gemini_tts.DEFAULT_STYLE: str = "Calm, warm and conversational."`, `gemini_tts.STYLE = os.environ.get("POPORY_GEMINI_TTS_STYLE") or DEFAULT_STYLE`.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/test_options.py
def test_male_default_is_a_designed_gemini_voice():
    from popory_content import gemini_tts as g
    model, speaker = g.parse_voice(VOICE["male"])
    assert g.is_gemini_voice(VOICE["male"]) and model == "gemini-3.8-flash-tts"
    assert speaker == "voice_s8vzho2m0lq6"
    assert g.payload("x", speaker)["generationConfig"]["speechConfig"]["voiceConfig"] == {"voice": speaker}

# tests/test_gemini_tts.py
def test_default_style_is_one_short_constant_without_meta_instructions():
    assert g.DEFAULT_STYLE == "Calm, warm and conversational."
    lowered = g.DEFAULT_STYLE.lower()
    assert "same voice" not in lowered and "forties" not in lowered and "blank line" not in lowered
```

- [ ] **Step 2: 실패를 확인한다**

Run: `... -m pytest -o addopts= -q -p no:cacheprovider tests/test_options.py tests/test_gemini_tts.py -k "designed_gemini_voice or short_constant"`
Expected: 2 failed

- [ ] **Step 3: `VOICE["male"]`·`DEFAULT_STYLE`·`STYLE` 를 바꾸고 주석을 고친다**

options.py 주석에는 Iapetus(2026-10-05) → 설계 음성(2026-11-08) 이력, 실험 수치 한 줄, 되돌리는 법(Iapetus 로 한 줄 교체 + 워커 재시작), Charon 기각 이력(기존 문장 유지)을 남긴다.

- [ ] **Step 4: content 전체 테스트를 돌린다**

Run: `... -m pytest -o addopts= -q -p no:cacheprovider`
Expected: 전부 PASS(`test_speaking_rate_matches_default_voice_family` 는 Gemini 면 폴백 Neural2-C 와 짝을 보므로 그대로 통과해야 한다)

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/options.py services/content/popory_content/gemini_tts.py services/content/tests/test_options.py services/content/tests/test_gemini_tts.py
git commit -m "feat(tts): 남성 기본 음성을 Gemini 설계 음성으로 바꾸고 연출 지시를 짧은 고정 문구로 줄인다" -m "..." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: 설계 음성 만료 30일 전 경고

**Files:**
- Modify: `services/content/popory_content/options.py` — `DESIGNED_VOICE_EXPIRES`, `designed_voice_days_left()`
- Modify: `services/content/popory_content/worker.py` — `_log_voice_expiry()` 추가, 롱폼·쇼츠 분기의 `_log_scene_match(job_id, meta)` 바로 뒤에서 호출
- Modify: `services/healthcheck/popory_healthcheck/checks.py:164-169` — `_MARKERS` 에 항목 추가
- Test: `services/content/tests/test_options.py`, `services/content/tests/test_worker.py`, `services/healthcheck/tests/test_checks.py`

**Interfaces:**
- Consumes: Task 2 의 `VOICE["male"]`.
- Produces:
  - `options.DESIGNED_VOICE_EXPIRES: dict[str, datetime.date] = {"voice_s8vzho2m0lq6": datetime.date(2027, 11, 8)}`
  - `options.designed_voice_days_left(voice: str, today: datetime.date) -> int | None` — `voice`(전체 문자열 `모델/화자` 또는 화자만)의 화자가 표에 있으면 `(만료일 - today).days`, 없으면 `None`.
  - `worker.VOICE_EXPIRY_WARN_DAYS = 30`, `worker._log_voice_expiry(job_id: str, voice: str, today: datetime.date | None = None) -> None` — 남은 날이 30 이하이면 `append_log(LOGS_DIR, {"worker": "content", "status": "gemini_voice_expiry_failed", "job": job_id, "voice": voice, "expires": "2027-11-08", "days_left": n, "error": <안내>})`. 안내는 남은 날이 0 이상이면 `설계 음성 만료까지 {n}일 — services/content/tools/design_voice.py 로 새 음성을 만들고 options.VOICE·DESIGNED_VOICE_EXPIRES 를 바꾸세요`, 음수면 `설계 음성이 만료됨({expires}) — …같은 조치…`.
  - 헬스체크 `_MARKERS` 항목 `('"status": "gemini_voice_expiry_failed"', "설계 음성 만료 임박")`.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/test_options.py
def test_designed_voice_days_left():
    from datetime import date
    from popory_content.options import designed_voice_days_left
    assert designed_voice_days_left("gemini-3.8-flash-tts/voice_s8vzho2m0lq6", date(2027, 10, 9)) == 30
    assert designed_voice_days_left("voice_s8vzho2m0lq6", date(2027, 11, 9)) == -1
    assert designed_voice_days_left("gemini-3.8-flash-tts/Iapetus", date(2027, 10, 9)) is None
    assert designed_voice_days_left("ko-KR-Chirp3-HD-Aoede", date(2027, 10, 9)) is None

# tests/test_worker.py — LOGS_DIR 는 conftest 가 tmp_path/"logs" 로 바꿔 둔다. 그 폴더의 *.log 를 읽어 JSON 줄을 모은다.
def test_voice_expiry_silent_before_window(tmp_path):
    worker._log_voice_expiry("j1", "gemini-3.8-flash-tts/voice_s8vzho2m0lq6", today=date(2027, 10, 8))  # 31일
    assert _statuses(tmp_path) == []

def test_voice_expiry_logs_within_30_days(tmp_path):
    worker._log_voice_expiry("j1", "gemini-3.8-flash-tts/voice_s8vzho2m0lq6", today=date(2027, 10, 9))
    rec = _records(tmp_path)[0]
    assert rec["status"] == "gemini_voice_expiry_failed" and rec["days_left"] == 30 and rec["expires"] == "2027-11-08"
    assert "design_voice.py" in rec["error"]

def test_voice_expiry_logs_after_expiry(tmp_path):
    worker._log_voice_expiry("j1", "gemini-3.8-flash-tts/voice_s8vzho2m0lq6", today=date(2027, 11, 9))
    rec = _records(tmp_path)[0]
    assert rec["days_left"] == -1 and "만료됨" in rec["error"]

def test_voice_expiry_ignores_voices_without_expiry(tmp_path):
    for v in ("gemini-3.8-flash-tts/Iapetus", "ko-KR-Chirp3-HD-Aoede"):
        worker._log_voice_expiry("j1", v, today=date(2027, 11, 9))
    assert _statuses(tmp_path) == []

# services/healthcheck/tests/test_checks.py
def test_scan_log_markers_flags_designed_voice_expiry():
    status, msg = checks.scan_log_markers('{"status": "gemini_voice_expiry_failed"}\n')
    assert status == "warn" and "설계 음성 만료 임박 1건" in msg
```

(`_records`·`_statuses` 는 test_worker.py 안의 작은 도우미 — `tmp_path/"logs"` 의 로그 줄을 JSON 으로 읽는다. 이미 같은 일을 하는 도우미가 있으면 그것을 쓴다.)

- [ ] **Step 2: 실패를 확인한다**

Run: content `... -m pytest ... tests/test_options.py tests/test_worker.py -k "days_left or voice_expiry"`, healthcheck `... -m pytest ... tests/test_checks.py -k designed_voice_expiry`
Expected: 전부 FAIL(이름 없음·마커 없음)

- [ ] **Step 3: 구현한다** — 위 Interfaces 그대로. 워커 호출은 `VOICE[opts["voice"]]` 를 넘긴다. `today` 기본값은 KST 오늘(`log.KST` 가 있으면 그것).

- [ ] **Step 4: content·healthcheck 전체 테스트를 돌린다**

Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git commit -m "feat(tts): 설계 음성 만료 30일 전부터 영상 작업마다 경고를 남기고 헬스체크가 잡는다" -m "..." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: 재생성 도구와 문서

**Files:**
- Create: `services/content/tools/design_voice.py`
- Create: `services/content/tests/test_design_voice.py`
- Modify: `.claude/skills/popory-content-creation/SKILL.md` — TTS 절의 '기본 남성 음성' 항목

**Interfaces:**
- Produces: `PERSONA: str`(설계 문서의 페르소나 문구 그대로), `DISPLAY_NAME = "popory-narrator-v1"`, `build_request(persona: str = PERSONA, display_name: str = DISPLAY_NAME) -> dict`, `main(argv: list[str] | None = None) -> int`.
  - 기본(인자 없음): 보낼 요청 본문만 출력하고 0 반환(요청 없음).
  - `--yes`: `POST https://generativelanguage.googleapis.com/v1beta/voices`(헤더 `x-goog-api-key`, 키는 env `GEMINI_API_KEY`, 출력 금지) → voice ID·`expire_time` 출력, `sample_audio` 를 `~/Downloads/popory_voice_design/<id>.wav` 로 저장, 다음 조치(`options.VOICE`·`DESIGNED_VOICE_EXPIRES` 교체, `tools/voice_ab.py` 로 재비교) 안내.
  - `--list`: `GET …/v1beta/voices?type=prompted&language_code=ko-KR` → id·display_name·expire_time 한 줄씩.
  - HTTP 오류는 상태 코드와 본문 앞 300자를 출력하고 1 반환.

- [ ] **Step 1: 실패하는 테스트를 쓴다** — `test_compare_voices.py` 처럼 `importlib.util.spec_from_file_location` 으로 `tools/design_voice.py` 를 읽는다.

```python
def test_build_request_matches_current_voice():
    body = dv.build_request()
    v = body["voice"]
    assert body["store"] is True
    assert (v["model"], v["type"], v["gender"], v["language_code"], v["display_name"]) == (
        "gemini-3.8-flash-tts", "prompted", "male", "ko-KR", "popory-narrator-v1")
    assert v["prompted"]["input"].startswith("A calm, warm Korean man in his forties")

def test_dry_run_sends_nothing(monkeypatch, capsys):
    monkeypatch.setattr(dv.requests, "post", lambda *a, **k: pytest.fail("요청하면 안 된다"))
    assert dv.main([]) == 0
    assert "popory-narrator-v1" in capsys.readouterr().out

def test_create_saves_preview_and_prints_expiry(monkeypatch, tmp_path, capsys):
    # 가짜 post 가 {"id": "voice_new", "expire_time": "2028-11-08T00:00:00Z", "sample_audio": {"data": base64(b"RIFF....")}} 를 돌려주고,
    # 미리듣기 폴더를 tmp_path 로 바꾼 뒤 main(["--yes"]) == 0, tmp_path/"voice_new.wav" 존재, 출력에 "voice_new"·"2028-11-08" 포함.
    ...
```

- [ ] **Step 2: 실패 확인** — `tests/test_design_voice.py` 3 failed(파일 없음)
- [ ] **Step 3: 도구를 구현한다** — 첫 줄 한국어 역할 주석. 미리듣기 폴더는 모듈 상수(`PREVIEW_DIR`)로 두어 테스트가 바꿀 수 있게 한다.
- [ ] **Step 4: SKILL.md 를 고친다** — TTS 절 '기본 남성 음성' 항목을 설계 음성(2026-11-08~)으로 바꾸고, 실험 수치(장면 사이 폭 2.66→1.36반음, 테이크 간 2.1→1.1반음, 보정량 0.58→0.38반음, 밝기 폭은 그대로, 문단·연출 지시 교정은 효과 없음), 요청 본문 차이(`voiceConfig.voice`), 짧은 연출 지시와 그 근거(공식 문서), 만료 2027-11-08·경고·재생성 절차(`tools/design_voice.py --yes` → `voice_ab.py` 재비교 → `options.py` 두 값 교체 → 워커 `launchctl kill 9`), 다시 만들면 목소리가 달라질 수 있다는 주의를 적는다. Iapetus 이력 문장은 이력으로 남긴다.
- [ ] **Step 5: content 전체 테스트 PASS 확인 후 커밋**

```bash
git commit -m "feat(tts): 설계 음성을 다시 만드는 도구와 운영 문서" -m "..." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## 반영 절차(오케스트레이터)

1. 브랜치 전체 리뷰(Fable) → 지적 반영.
2. 실제 경로 검증(맥미니, 3요청) — 설계 문서 '검증' 기준.
3. PR → 머지 → 메인 체크아웃 `git pull` → `launchctl kill 9 gui/$(id -u)/com.popory.content-worker`(진행 중 잡 없음 확인 후) → runs 증가·PID 교체 확인.
4. 다음 18시 롱폼·쇼츠 작업 폴더 측정.
