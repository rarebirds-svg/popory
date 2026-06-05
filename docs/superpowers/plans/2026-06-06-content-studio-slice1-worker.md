# 컨텐츠 관리 Slice 1 · Phase C (로컬 워커) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mac 로컬에서 도는 워커가 포털 큐에서 컨텐츠 작업을 claim → claude CLI로 네이버 블로그 초안 생성(리서치·작성·SEO/저작권 자가검토) → 결과를 포털에 회신한다.

**Architecture:** `services/content/`(브리핑 미러 구조)의 Python 패키지 `popory_content`. ES256 서비스 키(area=`content-worker`)로 서명한 단명 JWT로 포털 API를 호출한다. 핵심 단순화 — 별도 LLM 리뷰어 패스를 두지 않고 **claude CLI 단일 호출**이 WebSearch/WebFetch 리서치 + 사용자 스타일 반영 작성 + SEO/저작권 자가검토를 수행하고 `<draft_markdown>`+`<meta_json>`을 낸다(스펙 §11이 구현시점 결정으로 남긴 부분).

**Tech Stack:** Python 3.11+, jwcrypto, requests, claude CLI(Claude Max OAuth), pytest + responses + pytest-mock.

**전제:** Phase A 라우트가 prod에 배포돼 `/api/content/jobs/claim`·`/api/content/jobs/:id/result`가 동작해야 한다. 브리핑 모듈(`services/brief/popory_brief/{jwt_signer,portal_client,log}.py`)을 참고/복사한다. 스펙: `docs/superpowers/specs/2026-06-05-content-studio-naver-design.md`.

---

## File Structure

| 파일 | 책임 | 신규/수정 |
|------|------|-----------|
| `services/content/pyproject.toml` | 패키지·의존성·pytest 설정 | 신규 |
| `services/content/popory_content/__init__.py` | 패키지 마커 | 신규 |
| `services/content/popory_content/jwt_signer.py` | 서비스 키 → 단명 JWT (sub=services-content) | 신규(브리핑 복사) |
| `services/content/popory_content/portal_client.py` | 포털 HTTP(get/post/patch) + exit code 매핑 | 신규(브리핑 복사 + patch) |
| `services/content/popory_content/log.py` | JSONL·KST 로그 | 신규(브리핑 복사) |
| `services/content/popory_content/contract.py` | claude 출력 `<draft_markdown>`/`<meta_json>` 파서 | 신규 |
| `services/content/popory_content/prompt.py` | system prompt + user message 빌더 | 신규 |
| `services/content/popory_content/generate.py` | claude CLI 호출 → (draft, meta) | 신규 |
| `services/content/popory_content/worker.py` | claim → generate → result 루프 | 신규 |
| `services/content/scripts/gen_service_key.py` | ES256 서비스 키 생성(1회) | 신규 |
| `services/content/run_worker.sh` | secrets source + 워커 루프 실행 | 신규 |
| `services/content/com.popory.content-worker.plist` | launchd 상주 데몬 정의 | 신규 |
| `services/content/tests/test_contract.py` | 파서 테스트 | 신규 |
| `services/content/tests/test_prompt.py` | 프롬프트 빌더 테스트 | 신규 |
| `services/content/tests/test_worker.py` | 워커 루프 테스트(mock) | 신규 |

---

## Task 1: 패키지 스캐폴드 + 공용 모듈 복사

**Files:**
- Create: `services/content/pyproject.toml`
- Create: `services/content/popory_content/__init__.py`
- Create: `services/content/popory_content/jwt_signer.py`
- Create: `services/content/popory_content/portal_client.py`
- Create: `services/content/popory_content/log.py`
- Create: `services/content/tests/__init__.py`

- [ ] **Step 1: pyproject.toml 작성**

`services/content/pyproject.toml`:

```toml
# services/content 의존성·테스트 설정 (popory monorepo 안의 독립 Python 프로젝트)
[project]
name = "popory-content"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "jwcrypto>=1.5.6",
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
include = ["popory_content*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 2: 패키지 마커 + 공용 모듈 복사**

`services/content/popory_content/__init__.py` — 빈 파일.

`services/content/popory_content/log.py` — `services/brief/popory_brief/log.py`를 그대로 복사(헤더 주석 포함, 내용 동일).

`services/content/popory_content/portal_client.py` — `services/brief/popory_brief/portal_client.py`를 복사하되 아래 두 곳을 수정한다.

`post` 시그니처에 기본값 추가(claim은 본문 없이 호출):
```python
    def post(self, path: str, *, json: Any = None) -> Any:
        return self._call("POST", path, body=json)
```
`get` 아래에 `patch` 추가:
```python
    def patch(self, path: str, *, json: Any) -> Any:
        return self._call("PATCH", path, body=json)
```

`services/content/popory_content/jwt_signer.py` — `services/brief/popory_brief/jwt_signer.py`를 복사하되 `sign_for_portal`의 sub·email을 content용으로 바꾼다:
```python
        "sub": "services-content",
        "email": "services-content@popory.local",
```
(파일 첫 줄 헤더 주석도 `# services/content 전용 ES256 키로 ...`로 수정.)

`services/content/tests/__init__.py` — 빈 파일.

- [ ] **Step 3: 설치 + import 확인**

Run:
```bash
cd services/content && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]" >/dev/null && python -c "import popory_content.jwt_signer, popory_content.portal_client, popory_content.log; print('ok')"
```
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add services/content/pyproject.toml services/content/popory_content/__init__.py services/content/popory_content/jwt_signer.py services/content/popory_content/portal_client.py services/content/popory_content/log.py services/content/tests/__init__.py
git commit -m "feat(content-worker): 패키지 스캐폴드 + 공용 모듈(jwt/portal/log)"
```

---

## Task 2: 출력 계약 파서 (contract.py)

**Files:**
- Create: `services/content/popory_content/contract.py`
- Create: `services/content/tests/test_contract.py`

- [ ] **Step 1: 실패 테스트 작성**

`services/content/tests/test_contract.py`:

```python
# claude 출력에서 draft_markdown·meta_json 추출을 검증.
import pytest
from popory_content.contract import parse_generation, ContractError


def test_parses_draft_and_meta():
    text = """헤더 잡담
<draft_markdown>
# 전세사기 예방
본문입니다.
</draft_markdown>
<meta_json>
{"title": "전세사기 예방", "tags": ["전세", "사기예방"], "seo": {"score": 82}, "copyright": {"ok": true}}
</meta_json>
끝말"""
    draft, meta = parse_generation(text)
    assert draft.startswith("# 전세사기 예방")
    assert meta["title"] == "전세사기 예방"
    assert meta["seo"]["score"] == 82
    assert meta["copyright"]["ok"] is True


def test_missing_tags_raises():
    with pytest.raises(ContractError):
        parse_generation("draft 없음")


def test_bad_json_raises():
    text = "<draft_markdown>x</draft_markdown><meta_json>{not json}</meta_json>"
    with pytest.raises(ContractError):
        parse_generation(text)
```

- [ ] **Step 2: 테스트 실행 → 실패**

Run: `cd services/content && . .venv/bin/activate && pytest tests/test_contract.py -q`
Expected: FAIL — `ModuleNotFoundError: popory_content.contract`.

- [ ] **Step 3: contract.py 구현**

`services/content/popory_content/contract.py`:

```python
# claude CLI 출력에서 draft_markdown·meta_json 두 XML 태그를 추출·파싱.
import json
import re
from typing import Any


class ContractError(Exception):
    """출력 계약 위반(태그 없음/JSON 파싱 실패)."""


def parse_generation(text: str) -> tuple[str, dict[str, Any]]:
    body_m = re.search(r"<draft_markdown>(.*?)</draft_markdown>", text, re.DOTALL)
    meta_m = re.search(r"<meta_json>\s*(\{.*?\})\s*</meta_json>", text, re.DOTALL)
    if not body_m or not meta_m:
        raise ContractError("draft_markdown/meta_json 태그를 찾지 못함")
    draft = body_m.group(1).strip()
    try:
        meta = json.loads(meta_m.group(1).strip())
    except json.JSONDecodeError as e:
        raise ContractError(f"meta_json 파싱 실패: {e}") from e
    return draft, meta
```

- [ ] **Step 4: 테스트 실행 → 통과**

Run: `cd services/content && . .venv/bin/activate && pytest tests/test_contract.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/content/popory_content/contract.py services/content/tests/test_contract.py
git commit -m "feat(content-worker): 출력 계약 파서"
```

---

## Task 3: 프롬프트 빌더 (prompt.py)

**Files:**
- Create: `services/content/popory_content/prompt.py`
- Create: `services/content/tests/test_prompt.py`

- [ ] **Step 1: 실패 테스트 작성**

`services/content/tests/test_prompt.py`:

```python
# system prompt 가 스타일 샘플·핵심 규칙을 담는지, user message 가 주제·출처를 담는지 검증.
from popory_content.prompt import build_system_prompt, build_user_message


def test_system_prompt_embeds_samples_and_rules():
    sp = build_system_prompt(["내 글 샘플 본문입니다."])
    assert "내 글 샘플 본문입니다." in sp
    assert "네이버" in sp           # 플랫폼 명시
    assert "저작권" in sp           # 저작권 규칙
    assert "draft_markdown" in sp   # 출력 계약 지시
    assert "meta_json" in sp


def test_system_prompt_without_samples():
    sp = build_system_prompt([])
    assert "draft_markdown" in sp   # 샘플 없어도 출력 계약은 유지


def test_user_message_has_topic_and_sources():
    um = build_user_message("전세사기 예방", [{"url": "https://law.go.kr/x", "note": "근거"}])
    assert "전세사기 예방" in um
    assert "https://law.go.kr/x" in um
```

- [ ] **Step 2: 테스트 실행 → 실패**

Run: `cd services/content && . .venv/bin/activate && pytest tests/test_prompt.py -q`
Expected: FAIL — 모듈 없음.

- [ ] **Step 3: prompt.py 구현**

`services/content/popory_content/prompt.py`:

```python
# claude CLI 에 줄 system prompt(작성 규칙 + 스타일) 와 user message(주제 + 출처) 를 조립.
from typing import Any

_BASE_RULES = """당신은 네이버 블로그용 장문 글을 쓰는 한국어 작성자입니다. 아래 절차와 규칙을 지키세요.

## 1. 리서치
- WebSearch·WebFetch 로 주제 관련 공신력 있는 자료(정부·기관·통계·신뢰 언론)를 우선 수집합니다.
- 사용자가 제공한 참고 링크가 있으면 반드시 검토해 반영합니다.
- 근거가 부족하면 추측으로 채우지 말고, 확인된 사실만 씁니다.

## 2. 작성 (네이버 블로그)
- 제목 + 소제목(##) 구조의 장문 글. 도입·본문·마무리.
- 자연스러운 한국어. 문장은 마침표로 끝냅니다(콜론 종결 금지).

## 3. SEO (네이버 검색)
- 핵심 키워드를 제목과 첫 문단에 자연스럽게 배치합니다.
- 소제목으로 구조를 잡고, 글 끝에 태그 후보를 5~10개 제시합니다.

## 4. 저작권
- 원문을 그대로 길게 베끼지 않습니다. 자신의 말로 바꿔 씁니다(패러프레이즈).
- 사실·수치·인용에는 출처를 표기합니다.

## 5. 출력 (반드시 마지막 응답에 두 태그를 정확히 포함)
<draft_markdown>
(완성된 네이버 블로그 글 markdown)
</draft_markdown>
<meta_json>
{"title": "...", "tags": ["..."], "sources": ["URL", ...], "seo": {"score": 0-100, "notes": "..."}, "copyright": {"ok": true/false, "notes": "..."}}
</meta_json>
"""

_STYLE_HEADER = "\n## 6. 사용자 글 스타일 (아래 샘플의 어조·문장 길이·표현을 따르세요)\n"


def build_system_prompt(style_samples: list[str]) -> str:
    sp = _BASE_RULES
    if style_samples:
        sp += _STYLE_HEADER
        for i, s in enumerate(style_samples, 1):
            sp += f"\n--- 샘플 {i} ---\n{s.strip()}\n"
    return sp


def build_user_message(topic: str, sources: list[dict[str, Any]]) -> str:
    lines = [f"주제: {topic}", "", "시스템 규칙의 절차를 따라 네이버 블로그 글을 작성하세요."]
    refs = [s for s in sources if s.get("url")]
    if refs:
        lines.append("")
        lines.append("참고 링크:")
        for s in refs:
            note = f" — {s['note']}" if s.get("note") else ""
            lines.append(f"- {s['url']}{note}")
    lines.append("")
    lines.append("마지막 응답에 <draft_markdown>...</draft_markdown> 과 <meta_json>...</meta_json> 두 태그를 정확히 포함하세요.")
    return "\n".join(lines)
```

- [ ] **Step 4: 테스트 실행 → 통과**

Run: `cd services/content && . .venv/bin/activate && pytest tests/test_prompt.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/content/popory_content/prompt.py services/content/tests/test_prompt.py
git commit -m "feat(content-worker): 프롬프트 빌더(작성 규칙·스타일·출처)"
```

---

## Task 4: claude CLI 생성 (generate.py)

**Files:**
- Create: `services/content/popory_content/generate.py`

> claude CLI 호출은 외부 의존이라 단위 테스트가 어렵다. 순수 로직(프롬프트·파서)은 Task 2·3에서 검증했고, 여기서는 통합 호출만 작성한 뒤 Task 7의 e2e smoke 로 검증한다.

- [ ] **Step 1: generate.py 구현**

`services/content/popory_content/generate.py`:

```python
# claude CLI(비대화형, Claude Max)로 네이버 블로그 초안을 생성하고 (draft, meta) 를 돌려준다.
import subprocess
from pathlib import Path
from typing import Any

from popory_content.contract import parse_generation, ContractError
from popory_content.prompt import build_system_prompt, build_user_message

CLAUDE_BIN = "/opt/homebrew/bin/claude"
DEFAULT_MODEL = "claude-sonnet-4-6"
TIMEOUT_SECONDS = 1200


class GenerateError(Exception):
    """생성 실패(CLI 부재/타임아웃/비제로 종료/계약 위반)."""


def generate(
    *,
    topic: str,
    sources: list[dict[str, Any]],
    style_samples: list[str],
    model: str = DEFAULT_MODEL,
    job_id: str = "adhoc",
) -> tuple[str, dict[str, Any]]:
    if not Path(CLAUDE_BIN).exists():
        raise GenerateError(f"claude CLI not found at {CLAUDE_BIN}")

    sys_prompt = build_system_prompt(style_samples)
    user_msg = build_user_message(topic, sources)
    sys_path = Path(f"/tmp/content_system_{job_id}.txt")
    sys_path.write_text(sys_prompt, encoding="utf-8")

    cmd = [
        CLAUDE_BIN,
        "--print",
        "--model", model,
        "--allowed-tools", "WebSearch", "WebFetch",
        "--system-prompt-file", str(sys_path),
        "--output-format", "text",
    ]
    try:
        result = subprocess.run(
            cmd, input=user_msg, capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        raise GenerateError(f"claude CLI timeout after {TIMEOUT_SECONDS}s") from e
    finally:
        sys_path.unlink(missing_ok=True)

    if result.returncode != 0:
        raise GenerateError(f"claude CLI exit {result.returncode}: {result.stderr[-500:]}")

    try:
        return parse_generation(result.stdout)
    except ContractError as e:
        raise GenerateError(str(e)) from e
```

- [ ] **Step 2: import 확인**

Run: `cd services/content && . .venv/bin/activate && python -c "from popory_content.generate import generate, GenerateError; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add services/content/popory_content/generate.py
git commit -m "feat(content-worker): claude CLI 생성 모듈"
```

---

## Task 5: 워커 루프 (worker.py)

**Files:**
- Create: `services/content/popory_content/worker.py`
- Create: `services/content/tests/test_worker.py`

- [ ] **Step 1: 실패 테스트 작성 (mock client + monkeypatch generate)**

`services/content/tests/test_worker.py`:

```python
# 워커가 claim→generate→result 를 올바른 상태로 호출하는지 검증.
from popory_content import worker


class FakeClient:
    def __init__(self, claim_response):
        self._claim = claim_response
        self.patched = []

    def post(self, path, *, json=None):
        assert path == "/api/content/jobs/claim"
        return self._claim

    def patch(self, path, *, json):
        self.patched.append((path, json))
        return {"ok": True}


def test_no_job_returns_false():
    client = FakeClient({})  # 204 → {}
    assert worker.run_once(client) is False


def test_success_posts_review(monkeypatch):
    monkeypatch.setattr(worker, "generate", lambda **kw: ("# 글", {"seo": {"score": 80}}))
    client = FakeClient({"job": {"id": "j1", "topic": "t"}, "sources": [], "style_samples": []})
    assert worker.run_once(client) is True
    path, body = client.patched[0]
    assert path == "/api/content/jobs/j1/result"
    assert body["status"] == "review"
    assert body["draft"] == "# 글"
    assert body["meta"]["seo"]["score"] == 80


def test_failure_posts_failed(monkeypatch):
    def boom(**kw):
        raise worker.GenerateError("ng")
    monkeypatch.setattr(worker, "generate", boom)
    client = FakeClient({"job": {"id": "j2", "topic": "t"}, "sources": [], "style_samples": []})
    assert worker.run_once(client) is True
    path, body = client.patched[0]
    assert path == "/api/content/jobs/j2/result"
    assert body["status"] == "failed"
    assert "ng" in body["error"]
```

- [ ] **Step 2: 테스트 실행 → 실패**

Run: `cd services/content && . .venv/bin/activate && pytest tests/test_worker.py -q`
Expected: FAIL — 모듈/속성 없음.

- [ ] **Step 3: worker.py 구현**

`services/content/popory_content/worker.py`:

```python
# 포털 큐에서 컨텐츠 작업을 claim → claude 생성 → 결과 회신. __main__ 은 무한 poll 루프.
import os
import sys
import time
from pathlib import Path

from popory_content.generate import generate, GenerateError
from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.log import append_log, KST

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
WORKER_AREA = "content-worker"
POLL_INTERVAL_SECONDS = 20


def run_once(client) -> bool:
    """큐에서 한 건 처리. 처리했으면 True, 큐가 비었으면 False."""
    data = client.post("/api/content/jobs/claim", json=None)
    if not data:
        return False
    job = data["job"]
    sources = data.get("sources", [])
    samples = data.get("style_samples", [])
    job_id = job["id"]
    try:
        draft, meta = generate(topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id)
        client.patch(f"/api/content/jobs/{job_id}/result", json={"status": "review", "draft": draft, "meta": meta})
        append_log(LOGS_DIR, {"worker": "content", "status": "review", "job": job_id})
    except (GenerateError, Exception) as e:  # noqa: BLE001 — 어떤 실패든 작업을 failed 로 회신
        client.patch(f"/api/content/jobs/{job_id}/result", json={"status": "failed", "error": str(e)[:2000]})
        append_log(LOGS_DIR, {"worker": "content", "status": "failed", "job": job_id, "error": str(e)[:300]})
    return True


def _build_client() -> PortalClient:
    key_file = os.environ.get("POPORY_CONTENT_KEY_FILE")
    base = os.environ.get("POPORY_PORTAL_API_BASE")
    if not key_file or not Path(key_file).exists():
        print(f"error: POPORY_CONTENT_KEY_FILE 미설정/없음: {key_file}", file=sys.stderr)
        sys.exit(2)
    if not base:
        print("error: POPORY_PORTAL_API_BASE 미설정", file=sys.stderr)
        sys.exit(2)
    material = KeyMaterial.load(Path(key_file))
    return PortalClient(base_url=base, token_provider=lambda: sign_for_portal(material, area=WORKER_AREA))


def main() -> None:
    client = _build_client()
    append_log(LOGS_DIR, {"worker": "content", "status": "start"})
    while True:
        try:
            processed = run_once(client)
        except PortalError as e:
            append_log(LOGS_DIR, {"worker": "content", "status": "portal_error", "error": str(e)[:300]})
            processed = False
        if not processed:
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 실행 → 통과**

Run: `cd services/content && . .venv/bin/activate && pytest tests/test_worker.py -q`
Expected: PASS.

- [ ] **Step 5: 전체 테스트 회귀**

Run: `cd services/content && . .venv/bin/activate && pytest -q`
Expected: contract·prompt·worker 전부 PASS.

- [ ] **Step 6: Commit**

```bash
git add services/content/popory_content/worker.py services/content/tests/test_worker.py
git commit -m "feat(content-worker): claim→생성→회신 워커 루프"
```

---

## Task 6: 서비스 키 생성 스크립트 + 실행 래퍼 + launchd

**Files:**
- Create: `services/content/scripts/gen_service_key.py`
- Create: `services/content/run_worker.sh`
- Create: `services/content/com.popory.content-worker.plist`
- Create: `services/content/secrets/.gitignore`

- [ ] **Step 1: 서비스 키 생성 스크립트**

`services/content/scripts/gen_service_key.py`:

```python
# ES256 서비스 키 1회 생성 — keyfile(JSON) 저장 + D1 등록용 public_jwk 출력.
import json
import sys
from datetime import date
from pathlib import Path

from jwcrypto import jwk


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("secrets/content_service_key.json")
    kid = f"services-content-{date.today().isoformat()}"
    key = jwk.JWK.generate(kty="EC", crv="P-256")
    public_jwk = json.loads(key.export_public())
    public_jwk.update({"kid": kid, "alg": "ES256", "use": "sig"})
    private_pem = key.export_to_pem(private_key=True, password=None).decode("ascii")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"kid": kid, "public_jwk": public_jwk, "private_pem": private_pem}, ensure_ascii=False, indent=2), encoding="utf-8")
    out.chmod(0o600)
    print(f"keyfile: {out}")
    print("아래 public_jwk 를 portal D1 signing_keys 에 status='grace' 로 INSERT 하세요:")
    print(json.dumps(public_jwk, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행 래퍼 + secrets gitignore**

`services/content/secrets/.gitignore`:
```
*
!.gitignore
```

`services/content/run_worker.sh`:
```bash
#!/bin/bash
# launchd 가 상주 실행하는 컨텐츠 워커 entry. secrets source 후 poll 루프 시작.
set -euo pipefail
CONTENT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${CONTENT_DIR}/.venv/bin/python"

# secrets (POPORY_CONTENT_KEY_FILE, POPORY_PORTAL_API_BASE) 를 export
# shellcheck disable=SC1091
source "${CONTENT_DIR}/secrets/env.sh"

exec "${VENV_PY}" -m popory_content.worker
```

`services/content/secrets/env.sh` 는 git에 올리지 않는다(.gitignore 처리). 내용 예시(운영자가 로컬에 작성):
```bash
export POPORY_CONTENT_KEY_FILE="/Users/daegong/projects/popory/services/content/secrets/content_service_key.json"
export POPORY_PORTAL_API_BASE="https://api.poporyfamily.com"
```

- [ ] **Step 3: launchd plist**

`services/content/com.popory.content-worker.plist`:
```xml
<!-- 컨텐츠 워커를 상주 실행하는 launchd 정의. 종료 시 자동 재시작. -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.popory.content-worker</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/daegong/projects/popory/services/content/run_worker.sh</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/Users/daegong/projects/popory/services/content/logs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>/Users/daegong/projects/popory/services/content/logs/launchd.err.log</string>
</dict>
</plist>
```

- [ ] **Step 4: 실행 권한 + Commit**

```bash
chmod +x services/content/run_worker.sh
git add services/content/scripts/gen_service_key.py services/content/run_worker.sh services/content/com.popory.content-worker.plist services/content/secrets/.gitignore
git commit -m "feat(content-worker): 서비스 키 생성·실행 래퍼·launchd 정의"
```

---

## Task 7: 서비스 키 등록 + e2e smoke

**Files:** 없음 (운영 작업)

- [ ] **Step 1: 서비스 키 생성**

Run:
```bash
cd services/content && . .venv/bin/activate && python scripts/gen_service_key.py secrets/content_service_key.json
```
Expected: `keyfile: secrets/content_service_key.json` + public_jwk JSON 출력.

- [ ] **Step 2: prod D1 signing_keys 에 public_jwk 등록 (status='grace')**

Step 1이 출력한 public_jwk 와 kid 로 INSERT. (DB 이름은 `infra/wrangler/api.toml`의 `[[d1_databases]]` 확인.)

Run:
```bash
pnpm --filter @popory/api exec wrangler d1 execute <D1_DB_NAME> --remote --config ../../infra/wrangler/api.toml \
  --command "INSERT INTO signing_keys (kid, alg, public_jwk, private_jwk, status, created_at) VALUES ('<KID>', 'ES256', '<PUBLIC_JWK_JSON>', NULL, 'grace', strftime('%s','now'))"
```
Expected: 1 row written. `status='grace'` 이므로 포털 검증 JWKS(`loadJwks`는 active+grace)에는 포함되지만, 포털 자체 서명(`loadActivePrivate`는 active만)에는 간섭하지 않는다. `private_jwk` 는 NULL(0002 마이그레이션으로 nullable).

- [ ] **Step 3: secrets/env.sh 작성 + launchd 로드**

운영자가 `services/content/secrets/env.sh`를 Task 6 Step 2 예시대로 작성한 뒤:
```bash
mkdir -p services/content/logs
cp services/content/com.popory.content-worker.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.popory.content-worker.plist
```
Expected: 에러 없이 로드. `launchctl list | grep content-worker` 로 확인.

- [ ] **Step 4: e2e smoke**

포털 `/content` 에서 새 작업 생성 → 워커가 20초 내 claim → 수 분 후 작업 상태가 `review` 로 바뀌고 초안이 표시되는지 확인. 실패 시:
- `services/content/logs/<오늘>.log` 와 `logs/launchd.err.log` 의 실제 에러 라인을 읽는다(추측 금지).
- 인증 실패(401/403)면 키 등록(kid·area)·`POPORY_PORTAL_API_BASE` 를 점검.

- [ ] **Step 5: 완료 보고**

Slice 1 전체(Phase A 백엔드 + Phase B 포털 + Phase C 워커) 통합 완료. "주제 입력 → 리서치·검토된 네이버 블로그 초안" 이 끝까지 동작.

---

## Self-Review (작성자 체크)

**Spec coverage:**
- §5 실행 모델(Worker 큐 + 로컬 Mac 워커 poll + claude CLI) → Task 5 워커 + Task 4 생성. ✅
- §6 파이프라인 리서치·스타일 조건화·작성·SEO/저작권 검토·출력 → Task 3 프롬프트(리서치·SEO·저작권 규칙 + 스타일 샘플) + Task 4 생성 + Task 2 파서. (별도 리뷰어 패스 대신 단일 호출 자가검토 — 의도된 단순화, 본문에 명시) ✅
- §4 워커 인증 ES256 서비스 JWT(signing_keys, area=content-worker) → Task 1 jwt_signer + Task 7 키 등록. ✅
- §9 에러 처리(생성 실패 → failed 회신, 포털 오류 → 로그 후 계속) → Task 5 run_once/main. ✅
- §10 Python pytest(파서·프롬프트·워커) → Task 2·3·5. ✅
- 근거 부족 시 날조 금지 → Task 3 프롬프트 규칙. ✅

**Placeholder scan:** 모든 코드·명령 실제 내용 포함. `<D1_DB_NAME>`·`<KID>`·`<PUBLIC_JWK_JSON>` 는 직전 단계 산출물을 대입하는 운영 플레이스홀더로, 출처를 명시했다(추측 아님). ✅

**Type consistency:** `run_once(client)` 가 쓰는 클라이언트 인터페이스(`post(path, json=None)`·`patch(path, json=...)`)가 Task 1의 portal_client 수정과 일치. claim 응답 키(`job`·`sources`·`style_samples`)·result 바디(`status`·`draft`·`meta`·`error`)가 Phase A 라우트와 일치. `KeyMaterial.load`·`sign_for_portal(material, area=...)` 시그니처가 복사 모듈과 일치. 키파일 포맷(`kid`·`public_jwk`·`private_pem`)이 `gen_service_key.py` 출력과 `KeyMaterial.load` 기대값에 일치. ✅
```
