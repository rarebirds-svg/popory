<!-- 헬스체크 텔레그램 알림 서비스 구현 계획. -->

# 헬스체크 → 텔레그램 알림 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** popory 상태(포털·API·브리핑 발송·로컬 워커·자원 한도·콘텐츠 루틴)를 주기 점검하고, 아침 10:00 종합 요약 1통, 저녁 20:00 이상 시에만 텔레그램으로 알린다.

**Architecture:** 신규 로컬 Python 서비스 `services/healthcheck/`. 점검은 공개 HTTP 프로브 + 로컬(launchctl·로그 파일)만 사용해 backend 변경 0. `checks.py`가 각 항목을 `(status, message)`로 평가하고, `report.py`가 보고 정책(아침 항상/저녁 이상시)과 직전 상태 비교 중복 억제를 담당하며, `telegram.py`가 Bot API로 발송한다. launchd 2개(아침·저녁).

**Tech Stack:** Python 3.11(requests, pytest, pytest-mock, responses) · launchd · Telegram Bot API.

## Global Constraints

- 신규 소스 파일 첫 줄에 한국어 한 줄 역할 주석 (CLAUDE.md 규칙 6). Python은 `# `.
- backend(Worker/D1/포털) 변경 0. 점검은 공개 HTTP GET + 로컬 명령/파일만.
- 한국어 출력은 마침표 종결, 콜론 종결 금지 (CLAUDE.md 규칙 5).
- 점검 결과 상태값은 세 가지 문자열. `"ok" | "warn" | "fail"`.
- 각 점검 함수는 예외를 자체 포착해 `("fail", "<사유>")` 로 환원한다(한 점검 크래시가 전체를 막지 않음).
- 보고 정책. 아침(`am`)은 정상이어도 종합 요약 1통. 저녁(`pm`)은 `fail`/`warn` 하나라도 있을 때만 발송.
- KST 기준 날짜 비교는 `datetime.now(timezone(timedelta(hours=9)))`.
- 텔레그램 메시지는 평문(parse_mode 미사용)으로 보낸다 — 마크다운 특수문자 이스케이프 회피.
- 점검 대상 URL. 포털 `https://poporyfamily.com`, API `https://api.poporyfamily.com`, 공개 브리핑 `https://poporyfamily.com/p/brief-realestate/`.
- launchd 잡 라벨. 아침 `com.popory.healthcheck-am`(10:00), 저녁 `com.popory.healthcheck-pm`(20:00).
- 로컬 워커 데몬 라벨. `com.popory.content-worker`, `com.popory.imagegen`.
- 워커 로그 경로. `/Users/daegong/projects/popory/services/content/logs/<YYYY-MM-DD>.log` (JSONL).

---

### Task 1: 서비스 스캐폴드 + 텔레그램 발송 `telegram.py`

패키지 골격과 Bot API 발송 함수. 가장 먼저 — 이후 태스크가 의존.

**Files:**
- Create: `services/healthcheck/pyproject.toml`
- Create: `services/healthcheck/popory_healthcheck/__init__.py`
- Create: `services/healthcheck/popory_healthcheck/telegram.py`
- Create: `services/healthcheck/tests/test_telegram.py`
- Create: `services/healthcheck/.gitignore`

**Interfaces:**
- Produces: `send_telegram(token: str, chat_id: str, text: str) -> None`. 실패 시 `TelegramError` raise. `https://api.telegram.org/bot<token>/sendMessage` 에 `{chat_id, text}` POST(timeout 10s). 2xx 아니면 raise.

- [ ] **Step 1: pyproject + 패키지 마커 + gitignore 작성**

```toml
# services/healthcheck 의존성·테스트 설정 (popory monorepo 안의 독립 Python 프로젝트)
[project]
name = "popory-healthcheck"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "requests>=2.32",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-mock>=3.12",
  "responses>=0.25",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["popory_healthcheck*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

`services/healthcheck/popory_healthcheck/__init__.py` — 빈 파일(패키지 마커, 규칙 6 예외).

```gitignore
# services/healthcheck/.gitignore
.venv/
secrets/
state/
logs/
*.egg-info/
__pycache__/
```

- [ ] **Step 2: 실패 테스트 작성**

```python
# services/healthcheck/tests/test_telegram.py
# 텔레그램 Bot API 발송 함수 단위 테스트.
import pytest
import responses
from popory_healthcheck.telegram import send_telegram, TelegramError


@responses.activate
def test_send_ok():
    responses.add(responses.POST, "https://api.telegram.org/botTOK/sendMessage", json={"ok": True}, status=200)
    send_telegram("TOK", "123", "안녕하세요.")  # 예외 없으면 통과
    assert responses.calls[0].request.body is not None


@responses.activate
def test_send_failure_raises():
    responses.add(responses.POST, "https://api.telegram.org/botTOK/sendMessage", json={"ok": False}, status=400)
    with pytest.raises(TelegramError):
        send_telegram("TOK", "123", "x")
```

- [ ] **Step 3: 테스트 실패 확인**

먼저 venv 생성. `cd services/healthcheck && python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.
Run: `.venv/bin/python -m pytest tests/test_telegram.py -q`
Expected: FAIL — `ModuleNotFoundError: popory_healthcheck.telegram`.

- [ ] **Step 4: `telegram.py` 구현**

```python
# 텔레그램 Bot API sendMessage 발송 헬퍼.
import requests


class TelegramError(Exception):
    pass


def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    except requests.RequestException as e:
        raise TelegramError(f"network: {e}") from e
    if resp.status_code >= 400 or not resp.json().get("ok", False):
        raise TelegramError(f"telegram {resp.status_code}: {resp.text[:200]}")
```

- [ ] **Step 5: 테스트 통과 확인 + 커밋**

Run: `.venv/bin/python -m pytest tests/test_telegram.py -q` → PASS (2).

```bash
git add services/healthcheck/pyproject.toml services/healthcheck/popory_healthcheck/__init__.py services/healthcheck/popory_healthcheck/telegram.py services/healthcheck/tests/test_telegram.py services/healthcheck/.gitignore
git commit -m "feat(healthcheck): 서비스 스캐폴드 + 텔레그램 발송 헬퍼"
```

---

### Task 2: 점검 함수 `checks.py`

각 점검을 `(status, message)` 로 평가. 외부 의존(HTTP·launchctl·파일)은 인자로 주입해 테스트 가능하게 한다.

**Files:**
- Create: `services/healthcheck/popory_healthcheck/checks.py`
- Test: `services/healthcheck/tests/test_checks.py`

**Interfaces:**
- Produces (모두 `tuple[str, str]` = (status, message) 반환, status ∈ {ok,warn,fail}):
  - `check_http(name: str, url: str, warn_ms: int = 3000) -> tuple[str, str]`
  - `check_brief_published(url: str, today: str) -> tuple[str, str]` — 페이지 HTML에 `today`(YYYY-MM-DD 또는 YYYY.MM.DD) 문자열이 있으면 ok, 없으면 warn.
  - `check_daemon(label: str) -> tuple[str, str]` — `launchctl print gui/<uid>/<label>` 성공이면 ok, 아니면 fail. 내부에서 `subprocess` 사용.
  - `check_log_freshness(log_path: str, max_age_sec: int) -> tuple[str, str]` — 파일 mtime 이 max_age 이내면 ok, 초과면 warn, 없으면 warn.
  - `scan_log_markers(log_text: str) -> tuple[str, str]` — 로그 본문에서 한도/실패 마커(`session limit`, `image_failed`, `"status": "failed"`, `claude_fail`) 출현 시 warn + 개수.
  - `check_content_routine(log_text: str) -> tuple[str, str]` — auto_create 로그에서 `"cli": "auto_create"` 의 최근 `status` 가 `ok`면 ok, `skipped`면 warn(대기열 빔), 없으면 warn.
- 각 함수는 내부에서 예외를 잡아 `("fail", str(e))` 로 환원.

- [ ] **Step 1: 실패 테스트 작성**

```python
# services/healthcheck/tests/test_checks.py
# 점검 함수들의 ok/warn/fail 분기 단위 테스트.
import responses
from popory_healthcheck import checks


@responses.activate
def test_http_ok():
    responses.add(responses.GET, "https://x.test/", status=200)
    status, _ = checks.check_http("포털", "https://x.test/")
    assert status == "ok"


@responses.activate
def test_http_fail_on_500():
    responses.add(responses.GET, "https://x.test/", status=500)
    status, _ = checks.check_http("API", "https://x.test/")
    assert status == "fail"


@responses.activate
def test_http_fail_on_network():
    # 등록 안 된 URL → ConnectionError → fail 환원
    status, _ = checks.check_http("API", "https://unreg.test/")
    assert status == "fail"


@responses.activate
def test_brief_published_ok_when_date_present():
    responses.add(responses.GET, "https://x.test/p/brief-realestate/", body="<li>2026-06-27 부동산</li>", status=200)
    status, _ = checks.check_brief_published("https://x.test/p/brief-realestate/", "2026-06-27")
    assert status == "ok"


@responses.activate
def test_brief_published_warn_when_absent():
    responses.add(responses.GET, "https://x.test/p/brief-realestate/", body="<li>2026-06-20 옛글</li>", status=200)
    status, _ = checks.check_brief_published("https://x.test/p/brief-realestate/", "2026-06-27")
    assert status == "warn"


def test_log_freshness_warn_when_missing(tmp_path):
    status, _ = checks.check_log_freshness(str(tmp_path / "none.log"), 600)
    assert status == "warn"


def test_log_freshness_ok_when_recent(tmp_path):
    p = tmp_path / "x.log"
    p.write_text("hi")
    status, _ = checks.check_log_freshness(str(p), 600)
    assert status == "ok"


def test_scan_markers_warn():
    status, msg = checks.scan_log_markers('{"status": "failed"}\nsession limit reached')
    assert status == "warn"
    assert "2" in msg or "건" in msg


def test_scan_markers_ok_when_clean():
    status, _ = checks.scan_log_markers('{"status": "ok"}')
    assert status == "ok"


def test_content_routine_ok():
    status, _ = checks.check_content_routine('{"cli": "auto_create", "status": "ok", "created": []}')
    assert status == "ok"


def test_content_routine_warn_when_skipped():
    status, _ = checks.check_content_routine('{"cli": "auto_create", "status": "skipped", "reason": "empty"}')
    assert status == "warn"


def test_content_routine_warn_when_absent():
    status, _ = checks.check_content_routine('{"cli": "worker", "status": "ok"}')
    assert status == "warn"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd services/healthcheck && .venv/bin/python -m pytest tests/test_checks.py -q`
Expected: FAIL — `ModuleNotFoundError: popory_healthcheck.checks`.

- [ ] **Step 3: `checks.py` 구현**

```python
# popory 상태 점검 함수 모음 — 각자 (status, message) 반환, 예외는 fail로 환원.
import os
import re
import subprocess
import time

import requests


def check_http(name: str, url: str, warn_ms: int = 3000) -> tuple[str, str]:
    try:
        t0 = time.monotonic()
        resp = requests.get(url, timeout=10, allow_redirects=True)
        ms = int((time.monotonic() - t0) * 1000)
    except requests.RequestException as e:
        return ("fail", f"{name} 연결 실패 — {e}")
    if resp.status_code >= 400:
        return ("fail", f"{name} HTTP {resp.status_code}")
    if ms > warn_ms:
        return ("warn", f"{name} 느림 — {ms}ms")
    return ("ok", f"{name} 정상 — {resp.status_code}, {ms}ms")


def check_brief_published(url: str, today: str) -> tuple[str, str]:
    try:
        resp = requests.get(url, timeout=10)
    except requests.RequestException as e:
        return ("fail", f"브리핑 페이지 연결 실패 — {e}")
    if resp.status_code >= 400:
        return ("fail", f"브리핑 페이지 HTTP {resp.status_code}")
    dotted = today.replace("-", ".")
    if today in resp.text or dotted in resp.text:
        return ("ok", f"오늘자 브리핑 배포됨 — {today}")
    return ("warn", f"오늘자 브리핑 미확인 — {today}")


def check_daemon(label: str) -> tuple[str, str]:
    try:
        uid = os.getuid()
        r = subprocess.run(
            ["launchctl", "print", f"gui/{uid}/{label}"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as e:
        return ("fail", f"{label} 점검 실패 — {e}")
    if r.returncode != 0:
        return ("fail", f"{label} 미등록/중지")
    return ("ok", f"{label} 가동 중")


def check_log_freshness(log_path: str, max_age_sec: int) -> tuple[str, str]:
    try:
        mtime = os.path.getmtime(log_path)
    except OSError:
        return ("warn", f"로그 없음 — {os.path.basename(log_path)}")
    age = int(time.time() - mtime)
    if age > max_age_sec:
        return ("warn", f"로그 정체 — {age // 60}분 전")
    return ("ok", f"로그 신선 — {age // 60}분 전")


_MARKERS = ("session limit", "image_failed", '"status": "failed"', "claude_fail")


def scan_log_markers(log_text: str) -> tuple[str, str]:
    hits = sum(log_text.count(m) for m in _MARKERS)
    if hits > 0:
        return ("warn", f"한도/실패 마커 {hits}건")
    return ("ok", "한도/실패 마커 없음")


def check_content_routine(log_text: str) -> tuple[str, str]:
    last = None
    for line in log_text.splitlines():
        if '"cli": "auto_create"' in line:
            last = line
    if last is None:
        return ("warn", "자동 생성 기록 없음")
    if '"status": "ok"' in last:
        return ("ok", "자동 생성 정상")
    if '"status": "skipped"' in last:
        return ("warn", "자동 생성 skip — 추천 대기열 빔")
    return ("warn", "자동 생성 실패 기록")
```

- [ ] **Step 4: 테스트 통과 확인 + 커밋**

Run: `cd services/healthcheck && .venv/bin/python -m pytest tests/test_checks.py -q` → PASS.

```bash
git add services/healthcheck/popory_healthcheck/checks.py services/healthcheck/tests/test_checks.py
git commit -m "feat(healthcheck): 점검 함수 모음 — HTTP·브리핑·데몬·로그·루틴"
```

---

### Task 3: 보고 정책 + 중복 억제 `report.py`

점검 모음을 실행해 메시지를 조립하고, 모드별 발송 여부와 직전 상태 비교를 결정.

**Files:**
- Create: `services/healthcheck/popory_healthcheck/report.py`
- Test: `services/healthcheck/tests/test_report.py`

**Interfaces:**
- Consumes: `checks` 결과 형태 `list[tuple[str, str, str]]` = (항목명, status, message).
- Produces:
  - `format_report(results: list[tuple[str, str, str]], header: str) -> str` — `✅/⚠️/❌ 항목 — 메시지` 줄 + 헤더.
  - `overall(results) -> str` — 전체 status(fail>warn>ok 우선순위).
  - `should_send(mode: str, results, prev: dict | None) -> bool` — am이면 항상 True. pm이면 이상(warn/fail)이 하나라도 있고, 직전과 "동일 이상 집합"이 아닐 때만 True(완전 동일하면 False로 도배 억제). 이상이 없으면 False.
  - `state_signature(results) -> dict` — `{항목명: status}` (state 저장·비교용).

- [ ] **Step 1: 실패 테스트 작성**

```python
# services/healthcheck/tests/test_report.py
# 보고 포맷·전체상태·발송정책·중복억제 단위 테스트.
from popory_healthcheck import report

OK = [("포털", "ok", "정상"), ("API", "ok", "정상")]
WARN = [("포털", "ok", "정상"), ("API", "warn", "느림")]


def test_overall_priority():
    assert report.overall(OK) == "ok"
    assert report.overall(WARN) == "warn"
    assert report.overall([("x", "fail", "")]) == "fail"


def test_format_has_emoji_and_header():
    out = report.format_report(OK, "아침 점검")
    assert "아침 점검" in out
    assert "✅" in out


def test_am_always_sends():
    assert report.should_send("am", OK, None) is True


def test_pm_silent_when_all_ok():
    assert report.should_send("pm", OK, None) is False


def test_pm_sends_on_new_anomaly():
    assert report.should_send("pm", WARN, None) is True


def test_pm_suppresses_identical_anomaly():
    prev = report.state_signature(WARN)
    assert report.should_send("pm", WARN, prev) is False


def test_pm_sends_when_anomaly_changes():
    prev = report.state_signature(WARN)
    worse = [("포털", "fail", "다운"), ("API", "warn", "느림")]
    assert report.should_send("pm", worse, prev) is True
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd services/healthcheck && .venv/bin/python -m pytest tests/test_report.py -q`
Expected: FAIL — `ModuleNotFoundError: popory_healthcheck.report`.

- [ ] **Step 3: `report.py` 구현**

```python
# 점검 결과 → 텔레그램 메시지 조립 + 모드별 발송 정책·중복 억제.
_EMOJI = {"ok": "✅", "warn": "⚠️", "fail": "❌"}
_RANK = {"ok": 0, "warn": 1, "fail": 2}


def overall(results: list[tuple[str, str, str]]) -> str:
    worst = "ok"
    for _, status, _msg in results:
        if _RANK[status] > _RANK[worst]:
            worst = status
    return worst


def format_report(results: list[tuple[str, str, str]], header: str) -> str:
    lines = [f"[popory 점검] {header} — 전체 {_EMOJI[overall(results)]}"]
    for name, status, msg in results:
        lines.append(f"{_EMOJI[status]} {name} — {msg}")
    return "\n".join(lines)


def state_signature(results: list[tuple[str, str, str]]) -> dict:
    return {name: status for name, status, _ in results}


def _has_anomaly(results) -> bool:
    return any(status in ("warn", "fail") for _, status, _ in results)


def should_send(mode: str, results, prev: dict | None) -> bool:
    if mode == "am":
        return True
    # pm — 이상 있을 때만, 직전과 완전 동일하면 억제.
    if not _has_anomaly(results):
        return False
    if prev is not None and state_signature(results) == prev:
        return False
    return True
```

- [ ] **Step 4: 테스트 통과 확인 + 커밋**

Run: `cd services/healthcheck && .venv/bin/python -m pytest tests/test_report.py -q` → PASS.

```bash
git add services/healthcheck/popory_healthcheck/report.py services/healthcheck/tests/test_report.py
git commit -m "feat(healthcheck): 보고 포맷 + 모드별 발송 정책·중복 억제"
```

---

### Task 4: 엔트리 `run.py` + 실행 스크립트 + plist

전체를 묶는 엔트리. 점검 실행 → 정책 판단 → 발송 → 상태 저장. launchd 2개.

**Files:**
- Create: `services/healthcheck/popory_healthcheck/run.py`
- Create: `services/healthcheck/run_check.sh`
- Create: `services/healthcheck/com.popory.healthcheck-am.plist`
- Create: `services/healthcheck/com.popory.healthcheck-pm.plist`
- Test: `services/healthcheck/tests/test_run.py`

**Interfaces:**
- Consumes: `checks.*`, `report.*`, `telegram.send_telegram`. 환경변수 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- Produces: `gather() -> list[tuple[str, str, str]]` — 전 항목 점검 실행(테스트는 monkeypatch). `run(mode: str) -> int` — 엔트리. `main()` — argv `--mode=am|pm` 파싱.

- [ ] **Step 1: 실패 테스트 작성**

```python
# services/healthcheck/tests/test_run.py
# 엔트리 run 의 발송/억제/상태저장 흐름 테스트(점검·발송 monkeypatch).
import json
from popory_healthcheck import run as runmod


def _stub_gather(results):
    return lambda: results


def test_am_sends_and_saves(tmp_path, monkeypatch):
    results = [("포털", "ok", "정상")]
    sent = {}
    monkeypatch.setattr(runmod, "gather", _stub_gather(results))
    monkeypatch.setattr(runmod, "send_telegram", lambda t, c, text: sent.update(text=text))
    monkeypatch.setattr(runmod, "STATE_FILE", str(tmp_path / "last.json"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "C")
    rc = runmod.run("am")
    assert rc == 0
    assert "포털" in sent["text"]
    assert json.load(open(tmp_path / "last.json"))["포털"] == "ok"


def test_pm_silent_when_ok(tmp_path, monkeypatch):
    results = [("포털", "ok", "정상")]
    sent = {}
    monkeypatch.setattr(runmod, "gather", _stub_gather(results))
    monkeypatch.setattr(runmod, "send_telegram", lambda t, c, text: sent.update(text=text))
    monkeypatch.setattr(runmod, "STATE_FILE", str(tmp_path / "last.json"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "C")
    rc = runmod.run("pm")
    assert rc == 0
    assert "text" not in sent  # 발송 안 함
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd services/healthcheck && .venv/bin/python -m pytest tests/test_run.py -q`
Expected: FAIL — `ModuleNotFoundError: popory_healthcheck.run`.

- [ ] **Step 3: `run.py` 구현**

```python
# 헬스체크 엔트리 — 점검 실행 → 모드별 발송 판단 → 텔레그램 발송 → 상태 저장.
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from popory_healthcheck import checks, report
from popory_healthcheck.telegram import send_telegram, TelegramError

KST = timezone(timedelta(hours=9))
PORTAL = "https://poporyfamily.com"
API = "https://api.poporyfamily.com"
BRIEF = "https://poporyfamily.com/p/brief-realestate/"
WORKER_LOG_DIR = "/Users/daegong/projects/popory/services/content/logs"
STATE_FILE = str(Path(__file__).resolve().parent.parent / "state" / "last.json")


def _today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _worker_log_text() -> str:
    p = Path(WORKER_LOG_DIR) / f"{_today()}.log"
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def gather() -> list[tuple[str, str, str]]:
    log_text = _worker_log_text()
    log_path = str(Path(WORKER_LOG_DIR) / f"{_today()}.log")
    out = []
    out.append(("포털", *checks.check_http("포털", PORTAL)))
    out.append(("API", *checks.check_http("API", API)))
    out.append(("브리핑", *checks.check_brief_published(BRIEF, _today())))
    out.append(("워커데몬", *checks.check_daemon("com.popory.content-worker")))
    out.append(("이미지데몬", *checks.check_daemon("com.popory.imagegen")))
    out.append(("워커로그", *checks.check_log_freshness(log_path, 24 * 3600)))
    out.append(("자원한도", *checks.scan_log_markers(log_text)))
    out.append(("콘텐츠루틴", *checks.check_content_routine(log_text)))
    return out


def _load_prev() -> dict | None:
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_state(results) -> None:
    Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
    json.dump(report.state_signature(results), open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False)


def run(mode: str) -> int:
    results = gather()
    prev = _load_prev()
    if report.should_send(mode, results, prev):
        header = "아침 점검" if mode == "am" else "저녁 점검"
        text = report.format_report(results, header)
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        try:
            send_telegram(token, chat_id, text)
        except TelegramError as e:
            print(f"telegram send failed: {e}", file=sys.stderr)
            return 1
    _save_state(results)
    return 0


def main() -> int:
    mode = "am"
    for a in sys.argv[1:]:
        if a.startswith("--mode="):
            mode = a.split("=", 1)[1]
    if mode not in ("am", "pm"):
        print("usage: run --mode=am|pm", file=sys.stderr)
        return 2
    return run(mode)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/healthcheck && .venv/bin/python -m pytest tests/test_run.py -q` → PASS (2).
이어 전체. `cd services/healthcheck && .venv/bin/python -m pytest -q` → 전체 PASS.

- [ ] **Step 5: 실행 스크립트 + plist 작성**

```bash
# services/healthcheck/run_check.sh
#!/bin/bash
# launchd 가 호출하는 헬스체크 entry. secrets source 후 모드별 1회 실행. 인자 am|pm.
set -euo pipefail
HC_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${HC_DIR}/.venv/bin/python"
MODE="${1:-am}"

# shellcheck disable=SC1091
source "${HC_DIR}/secrets/env.sh"

exec "${VENV_PY}" -m popory_healthcheck.run "--mode=${MODE}"
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- 헬스체크 아침 종합 점검을 매일 10:00 KST 실행하는 launchd 정의. -->
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.popory.healthcheck-am</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/daegong/projects/popory/services/healthcheck/run_check.sh</string>
    <string>am</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/daegong/projects/popory/services/healthcheck</string>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/Users/daegong/projects/popory/services/healthcheck/logs/launchd-am.stdout.log</string>
  <key>StandardErrorPath</key><string>/Users/daegong/projects/popory/services/healthcheck/logs/launchd-am.stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>LANG</key><string>ko_KR.UTF-8</string><key>LC_ALL</key><string>ko_KR.UTF-8</string>
  </dict>
  <key>RunAtLoad</key><false/>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
```

저녁 plist 는 위와 동일하되 `Label`=`com.popory.healthcheck-pm`, 인자 `am`→`pm`, `Hour`=`20`, 로그 파일명 `launchd-pm.*`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- 헬스체크 저녁 점검(이상시에만 발송)을 매일 20:00 KST 실행하는 launchd 정의. -->
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.popory.healthcheck-pm</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/daegong/projects/popory/services/healthcheck/run_check.sh</string>
    <string>pm</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/daegong/projects/popory/services/healthcheck</string>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>20</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/Users/daegong/projects/popory/services/healthcheck/logs/launchd-pm.stdout.log</string>
  <key>StandardErrorPath</key><string>/Users/daegong/projects/popory/services/healthcheck/logs/launchd-pm.stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>LANG</key><string>ko_KR.UTF-8</string><key>LC_ALL</key><string>ko_KR.UTF-8</string>
  </dict>
  <key>RunAtLoad</key><false/>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
```

`chmod +x services/healthcheck/run_check.sh`.

- [ ] **Step 6: 커밋**

```bash
chmod +x services/healthcheck/run_check.sh
git add services/healthcheck/popory_healthcheck/run.py services/healthcheck/tests/test_run.py services/healthcheck/run_check.sh services/healthcheck/com.popory.healthcheck-am.plist services/healthcheck/com.popory.healthcheck-pm.plist
git commit -m "feat(healthcheck): 엔트리 run + 실행 스크립트 + launchd plist 2개"
```

---

## 배포·셋업 단계 (구현 후 1회, 사용자/에이전트)

- [ ] secrets 디렉토리·env. `mkdir -p services/healthcheck/secrets && chmod 700 services/healthcheck/secrets`. `services/healthcheck/secrets/env.sh` 작성(chmod 600).

```bash
# services/healthcheck/secrets/env.sh — 헬스체크 텔레그램 자격(커밋 금지)
export TELEGRAM_BOT_TOKEN="<기존 claude-tg 봇 토큰>"
export TELEGRAM_CHAT_ID="<본인 chat_id>"
```

- [ ] chat_id 확보(1회). 텔레그램에서 해당 봇에게 아무 메시지나 보낸 뒤 `curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | python3 -c "import sys,json;print(json.load(sys.stdin)['result'][-1]['message']['chat']['id'])"` 로 추출해 env.sh 에 기입.
- [ ] 단발 스모크. `cd services/healthcheck && source secrets/env.sh && .venv/bin/python -m popory_healthcheck.run --mode=am`. 텔레그램에 종합 요약 1통 도착 확인.
- [ ] plist 설치. `cp services/healthcheck/com.popory.healthcheck-am.plist services/healthcheck/com.popory.healthcheck-pm.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.popory.healthcheck-am.plist ~/Library/LaunchAgents/com.popory.healthcheck-pm.plist`.

## 롤백

`launchctl unload ~/Library/LaunchAgents/com.popory.healthcheck-am.plist ~/Library/LaunchAgents/com.popory.healthcheck-pm.plist`. 읽기·알림 전용이라 외부 영향 없음.
