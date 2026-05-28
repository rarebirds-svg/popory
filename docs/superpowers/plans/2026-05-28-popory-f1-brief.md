# popory F1 — services/brief 이전 + publish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Daily-brief 자산을 popory monorepo `services/brief/` 로 이전하고, routine이 매일 만든 Markdown 본문을 (a) 구독자 전원에게 메일 발송하고 (b) portal 공개 아카이브에 publish하는 분리된 CLI 파이프라인을 정착시킨다.

**Architecture:** Mac 로컬 Python(routine 호출) + Cloudflare Workers portal API. routine이 본문을 만들고, services/brief는 발송·publish 두 책임만 진다. 인증은 services/brief 전용 ES256 JWK로 자가 서명한 단명 JWT 하나로 통일하고, F0 `requireService` 미들웨어 흐름을 그대로 재사용한다. 메일/공개본은 같은 Markdown 단일 원본에서 분기된다.

**Tech Stack:** Python 3.11+ (pyproject.toml), `jwcrypto` (ES256), `markdown-it-py` + `mdit-py-plugins`, `google-api-python-client`, `requests`, `pytest`. Cloudflare Workers (Hono) + D1 + R2. Next.js 15 (RSC) + `react-markdown` + `remark-gfm` + `@tailwindcss/typography`. pnpm workspace + Turborepo.

**Spec:** `docs/superpowers/specs/2026-05-28-popory-f1-brief-design.md`

---

## File Structure

**Create:**
- `services/brief/.gitignore`
- `services/brief/.python-version`
- `services/brief/pyproject.toml`
- `services/brief/requirements.txt`
- `services/brief/README.md`
- `services/brief/popory_brief/__init__.py`
- `services/brief/popory_brief/log.py` — JSONL KST writer
- `services/brief/popory_brief/markdown.py` — Markdown→HTML envelope
- `services/brief/popory_brief/jwt_signer.py` — ES256 자가 서명
- `services/brief/popory_brief/portal_client.py` — HTTP + exit code 매핑
- `services/brief/popory_brief/scripts/__init__.py`
- `services/brief/popory_brief/scripts/keygen.py` — 1회성 키 생성 CLI
- `services/brief/tests/__init__.py`
- `services/brief/tests/test_log.py`
- `services/brief/tests/test_markdown.py`
- `services/brief/tests/test_jwt_signer.py`
- `services/brief/tests/test_portal_client.py`
- `services/brief/send_gmail.py` — daily-brief 이전 + `--md` 플래그
- `services/brief/auth_setup.py` — daily-brief 이전
- `services/brief/fetch_subscribers.py` — NEW
- `services/brief/publish_to_portal.py` — NEW
- `infra/migrations/0002_signing_keys_private_nullable.sql`
- `packages/types/src/area_subscribers.ts`
- `packages/types/src/area_subscribers.test.ts`
- `workers/api/src/routes/areas_subscribers.ts`
- `workers/api/src/routes/areas_subscribers.test.ts`

**Modify:**
- `.gitignore` — `services/*/secrets/`, `services/*/logs/`, `services/*/.venv/` 추가.
- `packages/types/src/index.ts` — `area_subscribers` re-export.
- `workers/api/src/app.ts` — `mountAreasSubscribers` 호출 추가.
- `apps/portal/package.json` — `react-markdown`, `remark-gfm`, `@tailwindcss/typography` 추가.
- `apps/portal/tailwind.config.ts` — typography plugin + `popory` typography 변형.
- `apps/portal/src/app/p/[area]/[id]/page.tsx` — `<article>` 본문 부분을 `ReactMarkdown` 으로 교체.

---

## Tasks

### Task 1: services/brief 디렉토리·.gitignore·pyproject 셋업

**Files:**
- Create: `services/brief/.gitignore`
- Create: `services/brief/.python-version`
- Create: `services/brief/pyproject.toml`
- Create: `services/brief/requirements.txt`
- Modify: `.gitignore` (popory 루트)

- [ ] **Step 1: 디렉토리 생성**

```bash
mkdir -p services/brief/popory_brief/scripts services/brief/tests services/brief/logs services/brief/secrets
```

- [ ] **Step 2: services/brief/.gitignore 작성**

Create `services/brief/.gitignore`:

```
# venv·캐시
.venv/
__pycache__/
*.pyc
.pytest_cache/

# 비밀: Mac 로컬 한정. 절대 커밋 금지.
secrets/

# 일자별 로그: 메타만 들어가지만 운영 정보라 커밋 안 함.
logs/
```

- [ ] **Step 3: services/brief/.python-version 작성**

Create `services/brief/.python-version`:

```
3.11
```

- [ ] **Step 4: services/brief/pyproject.toml 작성**

Create `services/brief/pyproject.toml`:

```toml
# services/brief 의존성·테스트 설정 (popory monorepo 안의 독립 Python 프로젝트)
[project]
name = "popory-brief"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "google-api-python-client>=2.130",
  "google-auth-oauthlib>=1.2",
  "jwcrypto>=1.5.6",
  "markdown-it-py>=3.0",
  "mdit-py-plugins>=0.4",
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
include = ["popory_brief*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 5: services/brief/requirements.txt 작성**

Create `services/brief/requirements.txt`:

```
# pyproject.toml과 동기. CI 또는 venv 재현용.
google-api-python-client>=2.130
google-auth-oauthlib>=1.2
jwcrypto>=1.5.6
markdown-it-py>=3.0
mdit-py-plugins>=0.4
requests>=2.32
pytest>=8.0
pytest-mock>=3.12
responses>=0.25
```

- [ ] **Step 6: popory 루트 .gitignore에 services/* 패턴 추가**

Modify `.gitignore` — `.DS_Store` 라인 뒤에 다음 블록 추가:

```
# services/* (Python 워크로드)
services/*/.venv/
services/*/secrets/
services/*/logs/
services/*/__pycache__/
services/*/.pytest_cache/
```

- [ ] **Step 7: 빈 패키지 마커 생성**

```bash
touch services/brief/popory_brief/__init__.py
touch services/brief/popory_brief/scripts/__init__.py
touch services/brief/tests/__init__.py
```

- [ ] **Step 8: 커밋**

```bash
git add services/brief/.gitignore services/brief/.python-version \
        services/brief/pyproject.toml services/brief/requirements.txt \
        services/brief/popory_brief/__init__.py \
        services/brief/popory_brief/scripts/__init__.py \
        services/brief/tests/__init__.py \
        .gitignore
git commit -m "chore(brief): services/brief 디렉토리·의존성 골격"
```

---

### Task 2: .venv 생성 + 의존성 설치 + pytest smoke

**Files:**
- Run-only (no commit; `.venv/`는 git ignore).

- [ ] **Step 1: venv 생성·활성화**

```bash
cd services/brief
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
```

Expected: `pip` 23+ 출력.

- [ ] **Step 2: 의존성 설치**

```bash
.venv/bin/pip install -e ".[dev]"
```

Expected: 모든 패키지가 충돌 없이 설치. 마지막 줄에 `Successfully installed ...`.

- [ ] **Step 3: pytest smoke (테스트 없어도 0개 통과)**

```bash
.venv/bin/pytest -q
```

Expected: `no tests ran in ...`s 또는 `0 passed`. exit code 5 (no tests collected)는 허용하지만 setup 자체가 깨지면 안 됨. 셋업 검증 목적.

> 이 task는 디스크 상태만 만들고 끝낸다. 커밋 없음.

---

### Task 3: popory_brief/log.py + tests

**Files:**
- Create: `services/brief/popory_brief/log.py`
- Test: `services/brief/tests/test_log.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `services/brief/tests/test_log.py`:

```python
# popory_brief.log: JSONL · KST · 본문 미포함 보장
import json
from pathlib import Path

from popory_brief.log import append_log


def test_append_log_writes_one_jsonl_line(tmp_path: Path):
    append_log(tmp_path, {"cli": "send_gmail", "status": "ok", "to": "a@b.com"})
    files = list(tmp_path.glob("*.log"))
    assert len(files) == 1
    line = files[0].read_text(encoding="utf-8").strip()
    rec = json.loads(line)
    assert rec["cli"] == "send_gmail"
    assert rec["status"] == "ok"
    assert rec["to"] == "a@b.com"
    assert "ts" in rec and rec["ts"].endswith("+09:00")  # KST


def test_append_log_filename_is_kst_date(tmp_path: Path):
    append_log(tmp_path, {"cli": "x", "status": "ok"})
    fname = next(tmp_path.glob("*.log")).name
    # YYYY-MM-DD.log 형식
    assert len(fname) == len("YYYY-MM-DD.log")
    assert fname[4] == "-" and fname[7] == "-"


def test_append_log_appends_subsequent_lines(tmp_path: Path):
    append_log(tmp_path, {"cli": "a", "status": "ok"})
    append_log(tmp_path, {"cli": "b", "status": "ok"})
    line_count = sum(1 for _ in next(tmp_path.glob("*.log")).open())
    assert line_count == 2
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
.venv/bin/pytest tests/test_log.py -v
```

Expected: FAIL — `ImportError: cannot import name 'append_log' from 'popory_brief.log'` (모듈 부재).

- [ ] **Step 3: 구현**

Create `services/brief/popory_brief/log.py`:

```python
# JSONL · KST · 메타만 적는 단일 로그 writer (모든 CLI 공용)
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))


def append_log(logs_dir: Path, record: dict) -> None:
    """KST 일자 파일에 한 줄 JSONL append. record에 ts를 자동 채운다."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(KST)
    record = {"ts": now.isoformat(timespec="seconds"), **record}
    fname = logs_dir / f"{now.strftime('%Y-%m-%d')}.log"
    with fname.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_log.py -v
```

Expected: 3 passed.

- [ ] **Step 5: 커밋**

```bash
git add services/brief/popory_brief/log.py services/brief/tests/test_log.py
git commit -m "feat(brief): JSONL KST 로그 writer (popory_brief.log)"
```

---

### Task 4: popory_brief/markdown.py + tests

**Files:**
- Create: `services/brief/popory_brief/markdown.py`
- Test: `services/brief/tests/test_markdown.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `services/brief/tests/test_markdown.py`:

```python
# popory_brief.markdown: Markdown → 메일용 HTML envelope
from popory_brief.markdown import markdown_to_email_html


def test_paragraph_and_link():
    html = markdown_to_email_html("안녕하세요. [예시](https://example.com)")
    assert "<p>" in html
    assert 'href="https://example.com"' in html
    assert "<!doctype html>" in html.lower()
    assert "<style>" in html  # envelope CSS 블록 포함


def test_table_renders_with_gfm():
    src = "| a | b |\n|---|---|\n| 1 | 2 |\n"
    html = markdown_to_email_html(src)
    assert "<table" in html
    assert "<th>a</th>" in html
    assert "<td>1</td>" in html


def test_code_fence_renders():
    src = "```python\nprint('x')\n```\n"
    html = markdown_to_email_html(src)
    assert "<pre>" in html
    assert "print(" in html


def test_h1_in_input_is_preserved_but_caller_should_avoid():
    # 본문 컨벤션은 H1 미사용. 코드는 거부하지 않고 그대로 변환만 한다.
    html = markdown_to_email_html("# title\n\n본문\n")
    assert "<h1>title</h1>" in html
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
.venv/bin/pytest tests/test_markdown.py -v
```

Expected: FAIL — 모듈 부재.

- [ ] **Step 3: 구현**

Create `services/brief/popory_brief/markdown.py`:

```python
# Markdown(GFM) → 메일 클라이언트가 안전히 렌더하는 self-contained HTML envelope
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

_ENVELOPE_HEAD = """<!doctype html><html lang="ko"><meta charset="utf-8">
<style>
  body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;
       max-width:680px;margin:24px auto;padding:0 16px;color:#111;
       line-height:1.65;font-size:15px;}
  h2,h3{margin-top:1.5em;}
  pre{background:#f6f8fa;padding:12px;border-radius:6px;overflow:auto;}
  blockquote{border-left:4px solid #d0d7de;color:#444;padding-left:12px;margin:0;}
  table{border-collapse:collapse;}
  th,td{border:1px solid #d0d7de;padding:6px 10px;}
  a{color:#0a66c2;}
</style>
<body>
"""
_ENVELOPE_FOOT = "</body></html>"


def _make_md() -> MarkdownIt:
    md = MarkdownIt("gfm-like", {"linkify": True, "html": False, "typographer": False})
    md.enable("table")
    md.enable("strikethrough")
    md.use(tasklists_plugin)
    return md


def markdown_to_email_html(src: str) -> str:
    """Markdown 본문을 메일 발송용 self-contained HTML로 변환."""
    body = _make_md().render(src)
    return _ENVELOPE_HEAD + body + _ENVELOPE_FOOT
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_markdown.py -v
```

Expected: 4 passed.

- [ ] **Step 5: 커밋**

```bash
git add services/brief/popory_brief/markdown.py services/brief/tests/test_markdown.py
git commit -m "feat(brief): Markdown→메일 HTML envelope 변환"
```

---

### Task 5: popory_brief/jwt_signer.py + tests

**Files:**
- Create: `services/brief/popory_brief/jwt_signer.py`
- Test: `services/brief/tests/test_jwt_signer.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `services/brief/tests/test_jwt_signer.py`:

```python
# popory_brief.jwt_signer: jwcrypto 기반 ES256 자가 서명 + portal verify와 동일 형태 검증
import json
from pathlib import Path

from jwcrypto import jwk, jwt

from popory_brief.jwt_signer import sign_for_portal, KeyMaterial


def _gen_keyfile(tmp_path: Path) -> Path:
    key = jwk.JWK.generate(kty="EC", crv="P-256")
    public = json.loads(key.export_public())
    public["kid"] = "test-kid-1"
    public["alg"] = "ES256"
    public["use"] = "sig"
    private_pem = key.export_to_pem(private_key=True, password=None).decode("ascii")
    keyfile = tmp_path / "key.json"
    keyfile.write_text(json.dumps({
        "kid": "test-kid-1",
        "public_jwk": public,
        "private_pem": private_pem,
    }))
    return keyfile


def test_sign_emits_valid_es256_with_kid(tmp_path: Path):
    keyfile = _gen_keyfile(tmp_path)
    material = KeyMaterial.load(keyfile)
    token = sign_for_portal(material, area="brief", ttl_seconds=60)
    # portal verify와 동일하게 — kid로 public 찾고 검증
    public = jwk.JWK.from_json(json.dumps(material.public_jwk))
    verified = jwt.JWT(jwt=token, key=public, check_claims={
        "iss": "popory-portal",
        "aud": "popory-portal",
    })
    claims = json.loads(verified.claims)
    assert claims["sub"] == "services-brief"
    assert claims["area"] == "brief"
    assert claims["email"] == "services-brief@popory.local"
    assert "exp" in claims and "iat" in claims


def test_sign_includes_kid_in_header(tmp_path: Path):
    keyfile = _gen_keyfile(tmp_path)
    material = KeyMaterial.load(keyfile)
    token = sign_for_portal(material, area="brief")
    header_b64 = token.split(".")[0]
    # base64url decode without padding fix
    import base64
    pad = "=" * (-len(header_b64) % 4)
    header = json.loads(base64.urlsafe_b64decode(header_b64 + pad))
    assert header["alg"] == "ES256"
    assert header["kid"] == "test-kid-1"
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
.venv/bin/pytest tests/test_jwt_signer.py -v
```

Expected: FAIL — 모듈 부재.

- [ ] **Step 3: 구현**

Create `services/brief/popory_brief/jwt_signer.py`:

```python
# services/brief 전용 ES256 키로 portal-호환 단명 JWT를 자가 서명한다.
# iss/aud는 F0 AreaTokenClaimsSchema 강제값(popory-portal)을 따른다.
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jwcrypto import jwk, jwt


@dataclass(frozen=True)
class KeyMaterial:
    kid: str
    public_jwk: dict[str, Any]
    private_pem: str

    @classmethod
    def load(cls, path: Path) -> "KeyMaterial":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            kid=data["kid"],
            public_jwk=data["public_jwk"],
            private_pem=data["private_pem"],
        )


def sign_for_portal(material: KeyMaterial, *, area: str, ttl_seconds: int = 60) -> str:
    """단명 ES256 JWT 한 장 발급. portal verify가 통과하는 형태."""
    now = int(time.time())
    claims = {
        "iss": "popory-portal",
        "aud": "popory-portal",
        "sub": "services-brief",
        "email": "services-brief@popory.local",
        "area": area,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    key = jwk.JWK.from_pem(material.private_pem.encode("ascii"))
    token = jwt.JWT(
        header={"alg": "ES256", "kid": material.kid, "typ": "JWT"},
        claims=claims,
    )
    token.make_signed_token(key)
    return token.serialize()
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_jwt_signer.py -v
```

Expected: 2 passed.

- [ ] **Step 5: 커밋**

```bash
git add services/brief/popory_brief/jwt_signer.py services/brief/tests/test_jwt_signer.py
git commit -m "feat(brief): ES256 자가 서명 JWT (popory_brief.jwt_signer)"
```

---

### Task 6: popory_brief/scripts/keygen.py

**Files:**
- Create: `services/brief/popory_brief/scripts/keygen.py`

> keygen은 1회성 운영 도구. 자체 테스트는 두지 않고 동작 확인만 한다.

- [ ] **Step 1: 구현**

Create `services/brief/popory_brief/scripts/keygen.py`:

```python
# 1회성: services/brief 전용 ES256 키페어를 만들어 한 파일에 저장한다.
# 사용법.
#   .venv/bin/python -m popory_brief.scripts.keygen --kid services-brief-2026-05 \
#       --out secrets/brief_signing_key.json
# 산출.
#   { "kid": "...", "public_jwk": {...}, "private_pem": "..." }
# public_jwk는 portal D1 signing_keys에 INSERT 한다.
import argparse
import json
from pathlib import Path

from jwcrypto import jwk


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--kid", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    key = jwk.JWK.generate(kty="EC", crv="P-256")
    public = json.loads(key.export_public())
    public["kid"] = args.kid
    public["alg"] = "ES256"
    public["use"] = "sig"
    private_pem = key.export_to_pem(private_key=True, password=None).decode("ascii")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "kid": args.kid,
        "public_jwk": public,
        "private_pem": private_pem,
    }, ensure_ascii=False, indent=2))
    print(json.dumps({"status": "ok", "kid": args.kid, "out": str(out_path),
                      "public_jwk": public}, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 동작 확인 (산출물은 커밋 안 함)**

```bash
.venv/bin/python -m popory_brief.scripts.keygen \
    --kid services-brief-test \
    --out /tmp/_keygen_test.json
cat /tmp/_keygen_test.json | python -c "import json,sys; d=json.load(sys.stdin); assert d['public_jwk']['crv']=='P-256'; print('OK')"
rm /tmp/_keygen_test.json
```

Expected: `OK` 출력.

- [ ] **Step 3: 커밋**

```bash
git add services/brief/popory_brief/scripts/keygen.py
git commit -m "feat(brief): services/brief 전용 ES256 keygen 1회성 CLI"
```

---

### Task 7: popory_brief/portal_client.py + tests

**Files:**
- Create: `services/brief/popory_brief/portal_client.py`
- Test: `services/brief/tests/test_portal_client.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `services/brief/tests/test_portal_client.py`:

```python
# popory_brief.portal_client: requests 래퍼 + exit code 매핑
import pytest
import responses

from popory_brief.portal_client import PortalClient, PortalError


@responses.activate
def test_get_success():
    responses.add(responses.GET, "https://api.popory.test/api/x",
                  json={"items": []}, status=200)
    c = PortalClient(base_url="https://api.popory.test", token_provider=lambda: "tok")
    body = c.get("/api/x")
    assert body == {"items": []}
    assert responses.calls[0].request.headers["Authorization"] == "Bearer tok"


@responses.activate
def test_get_401_maps_to_exit3():
    responses.add(responses.GET, "https://api.popory.test/api/x", status=401)
    c = PortalClient(base_url="https://api.popory.test", token_provider=lambda: "tok")
    with pytest.raises(PortalError) as ei:
        c.get("/api/x")
    assert ei.value.exit_code == 3


@responses.activate
def test_post_400_maps_to_exit4():
    responses.add(responses.POST, "https://api.popory.test/api/y",
                  json={"err": "bad"}, status=400)
    c = PortalClient(base_url="https://api.popory.test", token_provider=lambda: "tok")
    with pytest.raises(PortalError) as ei:
        c.post("/api/y", json={"a": 1})
    assert ei.value.exit_code == 4


@responses.activate
def test_post_500_retries_then_maps_to_exit5():
    responses.add(responses.POST, "https://api.popory.test/api/z", status=503)
    responses.add(responses.POST, "https://api.popory.test/api/z", status=503)
    c = PortalClient(base_url="https://api.popory.test", token_provider=lambda: "tok")
    with pytest.raises(PortalError) as ei:
        c.post("/api/z", json={})
    assert ei.value.exit_code == 5
    # 두 번 호출 (원호출 + 재시도 1회)
    assert len(responses.calls) == 2
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
.venv/bin/pytest tests/test_portal_client.py -v
```

Expected: FAIL — 모듈 부재.

- [ ] **Step 3: 구현**

Create `services/brief/popory_brief/portal_client.py`:

```python
# portal API HTTP 호출 헬퍼. Bearer 자동 부착 + 응답 → CLI exit code 매핑.
import time
from typing import Any, Callable

import requests


class PortalError(Exception):
    """exit_code 속성을 갖는 호출 실패."""
    def __init__(self, message: str, exit_code: int):
        super().__init__(message)
        self.exit_code = exit_code


class PortalClient:
    def __init__(self, *, base_url: str, token_provider: Callable[[], str], timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.token_provider = token_provider
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token_provider()}",
            "Content-Type": "application/json",
        }

    def get(self, path: str) -> Any:
        return self._call("GET", path, body=None)

    def post(self, path: str, *, json: Any) -> Any:
        return self._call("POST", path, body=json)

    def _call(self, method: str, path: str, *, body: Any) -> Any:
        url = f"{self.base_url}{path}"
        attempts = 2  # 원호출 + 5xx 재시도 1회
        last_status: int | None = None
        last_text = ""
        for i in range(attempts):
            try:
                resp = requests.request(method, url, headers=self._headers(),
                                        json=body, timeout=self.timeout)
            except requests.RequestException as e:
                if i + 1 < attempts:
                    time.sleep(2)
                    continue
                raise PortalError(f"network: {e}", exit_code=5) from e
            last_status, last_text = resp.status_code, resp.text
            if resp.status_code < 400:
                return resp.json() if resp.content else {}
            if resp.status_code in (401, 403):
                raise PortalError(f"auth {resp.status_code}: {resp.text}", exit_code=3)
            if 400 <= resp.status_code < 500:
                raise PortalError(f"client {resp.status_code}: {resp.text}", exit_code=4)
            if i + 1 < attempts:
                time.sleep(2)
                continue
        raise PortalError(f"server {last_status} after retry: {last_text}", exit_code=5)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_portal_client.py -v
```

Expected: 4 passed.

- [ ] **Step 5: 커밋**

```bash
git add services/brief/popory_brief/portal_client.py services/brief/tests/test_portal_client.py
git commit -m "feat(brief): portal HTTP 클라이언트 + exit code 매핑"
```

---

### Task 8: send_gmail.py 이전 + --md 플래그

**Files:**
- Create: `services/brief/send_gmail.py`
- Test: `services/brief/tests/test_send_gmail_md_flag.py`

> 발송 자체(Gmail API 호출)는 mock 테스트만 둔다. --md 플래그가 본문을 Markdown→HTML로 변환해서 message에 실리는지가 핵심 검증.

- [ ] **Step 1: 실패하는 테스트 작성**

Create `services/brief/tests/test_send_gmail_md_flag.py`:

```python
# send_gmail.py --md: body-file이 Markdown으로 해석되어 HTML envelope이 메시지에 실린다
import base64

from send_gmail import build_message_md_or_text


def test_md_flag_wraps_in_html_envelope():
    msg_dict = build_message_md_or_text(
        sender="me@a.com", to="you@b.com", subject="제목",
        body="안녕하세요.\n\n- 항목 1\n- 항목 2\n", md=True,
    )
    raw = base64.urlsafe_b64decode(msg_dict["raw"]).decode("utf-8")
    assert "Content-Type: text/html" in raw
    assert "<!doctype html>" in raw.lower()
    assert "<li>항목 1</li>" in raw


def test_md_flag_off_keeps_plain():
    msg_dict = build_message_md_or_text(
        sender=None, to="you@b.com", subject="제목",
        body="raw line\n", md=False,
    )
    raw = base64.urlsafe_b64decode(msg_dict["raw"]).decode("utf-8")
    assert "Content-Type: text/plain" in raw
    assert "raw line" in raw
```

`conftest.py`로 services/brief 루트를 import 경로에 추가.

Create `services/brief/tests/conftest.py`:

```python
# tests에서 send_gmail / fetch_subscribers / publish_to_portal 같은 루트 CLI 모듈을 import 하기 위함.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
.venv/bin/pytest tests/test_send_gmail_md_flag.py -v
```

Expected: FAIL — `send_gmail` 모듈 부재.

- [ ] **Step 3: send_gmail.py 작성 (daily-brief에서 이전 + --md)**

Create `services/brief/send_gmail.py`:

```python
# Gmail API로 부동산 브리핑 메일을 1통 발송하는 CLI 스크립트 (popory monorepo · services/brief)
"""
사용법.
    python send_gmail.py --to <email> --subject <s> --body-file <path>
                        [--md | --html] [--from <email>]

성공 시 stdout JSON 한 줄. {"status":"ok","message_id":"...","to":"...","ts":"..."}
실패 시 stderr에 사유, 비제로 exit code.

Exit codes.
    0 = 성공
    2 = token.json 없음 → auth_setup.py 먼저 실행
    3 = 토큰 갱신 실패 (refresh token 폐기) → auth_setup.py 재실행
    4 = Gmail API 4xx — 재시도 안 함
    5 = Gmail API 5xx / 네트워크 (1회 재시도 후) / 기타
"""
import argparse
import base64
import json
import sys
import time
from email.message import EmailMessage
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from popory_brief.log import append_log, KST
from popory_brief.markdown import markdown_to_email_html
from datetime import datetime

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
SCRIPT_DIR = Path(__file__).resolve().parent
TOKEN_FILE = SCRIPT_DIR / "secrets" / "token.json"
LOGS_DIR = SCRIPT_DIR / "logs"


def load_credentials() -> Credentials:
    if not TOKEN_FILE.exists():
        print(f"error: token.json not found at {TOKEN_FILE}. Run auth_setup.py first.",
              file=sys.stderr)
        sys.exit(2)
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())
        except Exception as e:
            print(f"error: token refresh failed ({e}). Re-run auth_setup.py.", file=sys.stderr)
            sys.exit(3)
    if not creds.valid:
        print("error: credentials invalid. Re-run auth_setup.py.", file=sys.stderr)
        sys.exit(3)
    return creds


def build_message_md_or_text(*, sender: str | None, to: str, subject: str,
                             body: str, md: bool, html: bool = False) -> dict:
    msg = EmailMessage()
    if md:
        rendered = markdown_to_email_html(body)
        msg.set_content(rendered, subtype="html", charset="utf-8")
    elif html:
        msg.set_content(body, subtype="html", charset="utf-8")
    else:
        msg.set_content(body, subtype="plain", charset="utf-8")
    msg["To"] = to
    if sender:
        msg["From"] = sender
    msg["Subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return {"raw": raw}


def send_with_retry(service, message: dict, retries: int = 1) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return service.users().messages().send(userId="me", body=message).execute()
        except HttpError as e:
            last_error = e
            status = getattr(e.resp, "status", None) if hasattr(e, "resp") else None
            if isinstance(status, int) and 400 <= status < 500:
                raise
            if attempt < retries:
                time.sleep(2)
            else:
                raise
    if last_error:
        raise last_error
    raise RuntimeError("send loop exited without result")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--to", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--body-file", required=True)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--md", action="store_true", help="body-file을 Markdown으로 해석")
    group.add_argument("--html", action="store_true", help="body-file을 HTML로 해석")
    p.add_argument("--from", dest="sender", default=None)
    args = p.parse_args()

    body = Path(args.body_file).read_text(encoding="utf-8")
    creds = load_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    message = build_message_md_or_text(
        sender=args.sender, to=args.to, subject=args.subject,
        body=body, md=args.md, html=args.html,
    )

    try:
        result = send_with_retry(service, message)
    except HttpError as e:
        status = getattr(e.resp, "status", "?") if hasattr(e, "resp") else "?"
        body_text = e.content.decode("utf-8", errors="replace") if hasattr(e, "content") else str(e)
        if isinstance(status, int) and 400 <= status < 500:
            print(f"error: Gmail API {status}: {body_text}", file=sys.stderr)
            sys.exit(4)
        print(f"error: Gmail API {status} after retry: {body_text}", file=sys.stderr)
        sys.exit(5)
    except Exception as e:
        print(f"error: unexpected: {e}", file=sys.stderr)
        sys.exit(5)

    ts = datetime.now(KST).isoformat(timespec="seconds")
    append_log(LOGS_DIR, {
        "cli": "send_gmail", "status": "ok",
        "message_id": result.get("id"), "to": args.to,
        "subject": args.subject, "md": bool(args.md), "html": bool(args.html),
    })
    print(json.dumps(
        {"status": "ok", "message_id": result.get("id"), "to": args.to, "ts": ts},
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
```

> 주의. 기존 daily-brief는 `token.json`을 스크립트 디렉토리 루트에 두지만, 새 services/brief는 `secrets/token.json` 경로다. Phase A에서 keygen·OAuth 토큰을 모두 secrets/ 아래로 정착시킨다.

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_send_gmail_md_flag.py -v
```

Expected: 2 passed.

- [ ] **Step 5: 커밋**

```bash
git add services/brief/send_gmail.py \
        services/brief/tests/test_send_gmail_md_flag.py \
        services/brief/tests/conftest.py
git commit -m "feat(brief): send_gmail.py 이전 + --md 플래그로 Markdown 본문 지원"
```

---

### Task 9: auth_setup.py 이전

**Files:**
- Create: `services/brief/auth_setup.py`

> 인터랙티브 OAuth는 단위 테스트 안 함.

- [ ] **Step 1: auth_setup.py 작성 (daily-brief에서 이전 + 경로 변경)**

Create `services/brief/auth_setup.py`:

```python
# Gmail API OAuth 2.0 인증을 1회 실행해 secrets/token.json을 생성하는 스크립트
"""
사용법.
    python auth_setup.py

브라우저가 열리며(또는 URL 출력) Google 계정 동의 화면이 나타난다.
secrets/credentials.json을 사용해 secrets/token.json (refresh token 포함)을 생성한다.
이후 send_gmail.py가 이 토큰을 자동 갱신하며 사용한다.
"""
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
SCRIPT_DIR = Path(__file__).resolve().parent
SECRETS_DIR = SCRIPT_DIR / "secrets"
CREDENTIALS_FILE = SECRETS_DIR / "credentials.json"
TOKEN_FILE = SECRETS_DIR / "token.json"


def main() -> None:
    if not CREDENTIALS_FILE.exists():
        raise SystemExit(
            f"credentials.json not found at {CREDENTIALS_FILE}.\n"
            "Google Cloud Console에서 OAuth Desktop client JSON을 다운로드해 "
            "이 경로에 저장한 뒤 다시 실행하세요."
        )

    SECRETS_DIR.mkdir(parents=True, exist_ok=True)

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if creds and creds.valid:
            print(f"token.json already valid: {TOKEN_FILE}")
            return
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())
            print(f"token refreshed: {TOKEN_FILE}")
            return

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(
        port=0,
        open_browser=False,
        authorization_prompt_message=(
            "\n>>> 이 URL을 브라우저에 직접 붙여넣어 인증하세요.\n>>> {url}\n"
        ),
        success_message="인증이 완료되었습니다. 이 창을 닫아도 됩니다.",
    )
    TOKEN_FILE.write_text(creds.to_json())
    print(f"token saved: {TOKEN_FILE}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 임포트만 확인**

```bash
.venv/bin/python -c "import auth_setup; print('OK')"
```

> CWD를 `services/brief/`로 두고 실행. Expected: `OK`.

- [ ] **Step 3: 커밋**

```bash
git add services/brief/auth_setup.py
git commit -m "feat(brief): auth_setup.py 이전 (secrets/ 경로 사용)"
```

---

### Task 10: fetch_subscribers.py + tests

**Files:**
- Create: `services/brief/fetch_subscribers.py`
- Test: `services/brief/tests/test_fetch_subscribers.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `services/brief/tests/test_fetch_subscribers.py`:

```python
# fetch_subscribers.py: portal에 service-auth GET → stdout JSON
import json
import subprocess
import sys
from pathlib import Path

import responses

BRIEF_DIR = Path(__file__).resolve().parent.parent
PYTHON = BRIEF_DIR / ".venv" / "bin" / "python"


def _make_key_env(tmp_path: Path) -> dict[str, str]:
    # 테스트용 키페어를 만들고 환경변수로 fetch_subscribers에 주입
    from jwcrypto import jwk
    key = jwk.JWK.generate(kty="EC", crv="P-256")
    public = json.loads(key.export_public())
    public["kid"] = "test-kid"; public["alg"] = "ES256"; public["use"] = "sig"
    pem = key.export_to_pem(private_key=True, password=None).decode("ascii")
    keyfile = tmp_path / "key.json"
    keyfile.write_text(json.dumps({"kid": "test-kid", "public_jwk": public, "private_pem": pem}))
    return {
        "POPORY_BRIEF_KEY_FILE": str(keyfile),
        "POPORY_PORTAL_API_BASE": "https://api.popory.test",
        "PATH": "/usr/bin:/bin",  # subprocess 안전망
    }


@responses.activate
def test_cli_prints_subscribers_json(tmp_path: Path, monkeypatch):
    responses.add(
        responses.GET,
        "https://api.popory.test/api/areas/brief/subscribers",
        json={"subscribers": [{"email": "a@x", "display_name": "A"}]},
        status=200,
    )
    # subprocess 안에서 responses mock이 동작하지 않으므로 직접 import 해서 main 호출
    sys.path.insert(0, str(BRIEF_DIR))
    from importlib import reload
    import fetch_subscribers
    reload(fetch_subscribers)

    env = _make_key_env(tmp_path)
    monkeypatch.setenv("POPORY_BRIEF_KEY_FILE", env["POPORY_BRIEF_KEY_FILE"])
    monkeypatch.setenv("POPORY_PORTAL_API_BASE", env["POPORY_PORTAL_API_BASE"])

    out = fetch_subscribers.fetch(area="brief")
    assert out == {"subscribers": [{"email": "a@x", "display_name": "A"}]}
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
.venv/bin/pytest tests/test_fetch_subscribers.py -v
```

Expected: FAIL — 모듈 부재.

- [ ] **Step 3: 구현**

Create `services/brief/fetch_subscribers.py`:

```python
# brief 영역 구독자 목록을 portal에서 가져와 stdout JSON으로 출력하는 CLI
"""
사용법.
    python fetch_subscribers.py --area brief

성공 시 stdout. {"subscribers":[{"email":"...","display_name":"..."}]}
실패 시 비제로 exit code (2/3/4/5 — popory_brief.portal_client 매핑).

환경변수.
    POPORY_BRIEF_KEY_FILE   ES256 키 파일 경로 (services/brief/secrets/brief_signing_key.json)
    POPORY_PORTAL_API_BASE  포털 API base (예: https://api.poporyfamily.com)
"""
import argparse
import json
import os
import sys
from pathlib import Path

from popory_brief.jwt_signer import KeyMaterial, sign_for_portal
from popory_brief.portal_client import PortalClient, PortalError
from popory_brief.log import append_log

LOGS_DIR = Path(__file__).resolve().parent / "logs"


def _key_path() -> Path:
    p = os.environ.get("POPORY_BRIEF_KEY_FILE")
    if not p:
        print("error: POPORY_BRIEF_KEY_FILE 미설정", file=sys.stderr)
        sys.exit(2)
    if not Path(p).exists():
        print(f"error: key file not found: {p}", file=sys.stderr)
        sys.exit(2)
    return Path(p)


def _portal_base() -> str:
    v = os.environ.get("POPORY_PORTAL_API_BASE")
    if not v:
        print("error: POPORY_PORTAL_API_BASE 미설정", file=sys.stderr)
        sys.exit(2)
    return v


def fetch(*, area: str) -> dict:
    material = KeyMaterial.load(_key_path())
    client = PortalClient(
        base_url=_portal_base(),
        token_provider=lambda: sign_for_portal(material, area=area),
    )
    return client.get(f"/api/areas/{area}/subscribers")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--area", default="brief")
    args = p.parse_args()
    try:
        body = fetch(area=args.area)
    except PortalError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(e.exit_code)
    count = len(body.get("subscribers", []))
    append_log(LOGS_DIR, {"cli": "fetch_subscribers", "status": "ok",
                          "area": args.area, "count": count})
    print(json.dumps(body, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_fetch_subscribers.py -v
```

Expected: 1 passed.

- [ ] **Step 5: 커밋**

```bash
git add services/brief/fetch_subscribers.py services/brief/tests/test_fetch_subscribers.py
git commit -m "feat(brief): fetch_subscribers CLI (portal service-auth GET)"
```

---

### Task 11: publish_to_portal.py + tests

**Files:**
- Create: `services/brief/publish_to_portal.py`
- Test: `services/brief/tests/test_publish_to_portal.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `services/brief/tests/test_publish_to_portal.py`:

```python
# publish_to_portal: meta.json + body.md를 portal POST 페이로드로 매핑
import json
from pathlib import Path

import responses

BRIEF_DIR = Path(__file__).resolve().parent.parent


def _setup_env(monkeypatch, tmp_path: Path):
    from jwcrypto import jwk
    key = jwk.JWK.generate(kty="EC", crv="P-256")
    pub = json.loads(key.export_public())
    pub["kid"] = "test-kid"; pub["alg"] = "ES256"; pub["use"] = "sig"
    pem = key.export_to_pem(private_key=True, password=None).decode("ascii")
    keyfile = tmp_path / "key.json"
    keyfile.write_text(json.dumps({"kid": "test-kid", "public_jwk": pub, "private_pem": pem}))
    monkeypatch.setenv("POPORY_BRIEF_KEY_FILE", str(keyfile))
    monkeypatch.setenv("POPORY_PORTAL_API_BASE", "https://api.popory.test")


@responses.activate
def test_publish_maps_meta_and_body(monkeypatch, tmp_path: Path):
    _setup_env(monkeypatch, tmp_path)
    body_path = tmp_path / "body.md"
    body_path.write_text("# skip\n\n안녕\n", encoding="utf-8")
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(json.dumps({
        "title": "오늘", "summary": "요약",
        "tags": ["t1", "t2"], "published_at": 1748400000,
    }), encoding="utf-8")

    captured = {}
    def _capture(request):
        captured["json"] = json.loads(request.body)
        return (201, {}, json.dumps({"id": "01HXY"}))

    responses.add_callback(
        responses.POST,
        "https://api.popory.test/api/published_items",
        callback=_capture,
        content_type="application/json",
    )

    import sys
    sys.path.insert(0, str(BRIEF_DIR))
    from importlib import reload
    import publish_to_portal
    reload(publish_to_portal)

    result = publish_to_portal.publish(area="brief", meta_file=meta_path, body_file=body_path)
    assert result == {"id": "01HXY"}
    sent = captured["json"]
    assert sent["area"] == "brief"
    assert sent["title"] == "오늘"
    assert sent["summary"] == "요약"
    assert sent["tags"] == ["t1", "t2"]
    assert sent["published_at"] == 1748400000
    assert sent["body"].startswith("# skip")
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
.venv/bin/pytest tests/test_publish_to_portal.py -v
```

Expected: FAIL — 모듈 부재.

- [ ] **Step 3: 구현**

Create `services/brief/publish_to_portal.py`:

```python
# 그날의 brief 본문을 portal에 publish 하는 CLI (하루 1회 호출)
"""
사용법.
    python publish_to_portal.py --area brief \
        --meta-file /tmp/brief_YYYY-MM-DD.meta.json \
        --body-file /tmp/brief_YYYY-MM-DD.md

성공 시 stdout. {"status":"ok","id":"<ulid>","title":"...","ts":"..."}
실패 시 비제로 exit code (2/3/4/5).

환경변수.
    POPORY_BRIEF_KEY_FILE   ES256 키 파일
    POPORY_PORTAL_API_BASE  포털 API base
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from popory_brief.jwt_signer import KeyMaterial, sign_for_portal
from popory_brief.portal_client import PortalClient, PortalError
from popory_brief.log import append_log, KST

LOGS_DIR = Path(__file__).resolve().parent / "logs"


def _key_path() -> Path:
    p = os.environ.get("POPORY_BRIEF_KEY_FILE")
    if not p or not Path(p).exists():
        print(f"error: POPORY_BRIEF_KEY_FILE 미설정 또는 파일 없음: {p}", file=sys.stderr)
        sys.exit(2)
    return Path(p)


def _portal_base() -> str:
    v = os.environ.get("POPORY_PORTAL_API_BASE")
    if not v:
        print("error: POPORY_PORTAL_API_BASE 미설정", file=sys.stderr)
        sys.exit(2)
    return v


def publish(*, area: str, meta_file: Path, body_file: Path) -> dict:
    meta = json.loads(Path(meta_file).read_text(encoding="utf-8"))
    body = Path(body_file).read_text(encoding="utf-8")
    payload = {
        "area": area,
        "title": meta["title"],
        "body": body,
        "published_at": int(meta["published_at"]),
    }
    if meta.get("summary"):
        payload["summary"] = meta["summary"]
    if meta.get("tags"):
        payload["tags"] = list(meta["tags"])

    material = KeyMaterial.load(_key_path())
    client = PortalClient(
        base_url=_portal_base(),
        token_provider=lambda: sign_for_portal(material, area=area),
    )
    return client.post("/api/published_items", json=payload)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--area", default="brief")
    p.add_argument("--meta-file", required=True)
    p.add_argument("--body-file", required=True)
    args = p.parse_args()
    try:
        body = publish(area=args.area,
                       meta_file=Path(args.meta_file),
                       body_file=Path(args.body_file))
    except PortalError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(e.exit_code)
    ts = datetime.now(KST).isoformat(timespec="seconds")
    append_log(LOGS_DIR, {
        "cli": "publish_to_portal", "status": "ok",
        "area": args.area, "id": body.get("id"),
    })
    print(json.dumps({"status": "ok", "id": body.get("id"),
                      "area": args.area, "ts": ts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_publish_to_portal.py -v
```

Expected: 1 passed.

- [ ] **Step 5: 커밋**

```bash
git add services/brief/publish_to_portal.py services/brief/tests/test_publish_to_portal.py
git commit -m "feat(brief): publish_to_portal CLI (meta+body → POST /api/published_items)"
```

---

### Task 12: portal D1 migration 0002 — signing_keys.private_jwk NULLABLE

**Files:**
- Create: `infra/migrations/0002_signing_keys_private_nullable.sql`

> 데이터 마이그레이션이라 별도 vitest 추가하지 않는다. 기존 23 vitest가 깨지지 않는지로 회귀를 본다.

- [ ] **Step 1: 마이그레이션 SQL 작성**

Create `infra/migrations/0002_signing_keys_private_nullable.sql`:

```sql
-- signing_keys.private_jwk를 NULLABLE로 완화한다. 외부 영역(services/brief 등)의
-- public-only 키를 dummy 빈 문자열 없이 등록할 수 있게 하기 위함이다.
-- D1은 ALTER COLUMN을 지원하지 않으므로 rename+rebuild 패턴을 쓴다.
ALTER TABLE signing_keys RENAME TO signing_keys_old;

CREATE TABLE signing_keys (
  kid          TEXT PRIMARY KEY,
  alg          TEXT NOT NULL DEFAULT 'ES256',
  public_jwk   TEXT NOT NULL,
  private_jwk  TEXT,
  status       TEXT NOT NULL CHECK (status IN ('active', 'grace', 'retired')),
  created_at   INTEGER NOT NULL,
  retired_at   INTEGER
);

INSERT INTO signing_keys (kid, alg, public_jwk, private_jwk, status, created_at, retired_at)
  SELECT kid, alg, public_jwk, private_jwk, status, created_at, retired_at FROM signing_keys_old;

DROP TABLE signing_keys_old;
CREATE INDEX idx_signing_keys_status ON signing_keys(status);
```

- [ ] **Step 2: 로컬 D1에서 적용 dry-run**

```bash
cd /Users/daegong/projects/popory
pnpm exec wrangler d1 migrations apply popory --local
```

Expected: `Applied 0002_signing_keys_private_nullable.sql`.

- [ ] **Step 3: workers/api 기존 vitest 회귀 확인**

```bash
pnpm --filter @popory/workers-api test
```

Expected: 기존 23 이상 vitest 전체 PASS.

- [ ] **Step 4: 커밋**

```bash
git add infra/migrations/0002_signing_keys_private_nullable.sql
git commit -m "chore(d1): signing_keys.private_jwk NULLABLE 마이그레이션 (외부 영역 키 등록용)"
```

---

### Task 13: packages/types — AreaSubscribersResponse

**Files:**
- Create: `packages/types/src/area_subscribers.ts`
- Create: `packages/types/src/area_subscribers.test.ts`
- Modify: `packages/types/src/index.ts`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `packages/types/src/area_subscribers.test.ts`:

```ts
// AreaSubscribersResponse zod 스키마: email 필수, display_name nullable
import { describe, it, expect } from "vitest";
import { AreaSubscribersResponseSchema } from "./area_subscribers";

describe("AreaSubscribersResponseSchema", () => {
  it("정상 응답 파싱", () => {
    const ok = AreaSubscribersResponseSchema.parse({
      subscribers: [
        { email: "a@x", display_name: "A" },
        { email: "b@x", display_name: null },
      ],
    });
    expect(ok.subscribers).toHaveLength(2);
  });

  it("subscribers 누락 시 거절", () => {
    expect(() => AreaSubscribersResponseSchema.parse({})).toThrow();
  });

  it("email 누락 시 거절", () => {
    expect(() =>
      AreaSubscribersResponseSchema.parse({ subscribers: [{ display_name: "x" }] }),
    ).toThrow();
  });
});
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
pnpm --filter @popory/types test -- area_subscribers
```

Expected: FAIL — `area_subscribers` 모듈 부재.

- [ ] **Step 3: 스키마 구현**

Create `packages/types/src/area_subscribers.ts`:

```ts
// 영역 구독자 조회 응답 스키마. routine이 fetch_subscribers로 받는 JSON 모양.
import { z } from "zod";

export const AreaSubscriberSchema = z.object({
  email: z.string().email(),
  display_name: z.string().nullable(),
});
export type AreaSubscriber = z.infer<typeof AreaSubscriberSchema>;

export const AreaSubscribersResponseSchema = z.object({
  subscribers: z.array(AreaSubscriberSchema),
});
export type AreaSubscribersResponse = z.infer<typeof AreaSubscribersResponseSchema>;
```

- [ ] **Step 4: index.ts에 re-export 추가**

Read current `packages/types/src/index.ts` first, then append:

```ts
export * from "./area_subscribers";
```

(기존 export 줄들 아래에 한 줄 추가.)

- [ ] **Step 5: 테스트 통과 + typecheck**

```bash
pnpm --filter @popory/types test
pnpm --filter @popory/types typecheck
```

Expected: 모든 테스트 PASS, typecheck 0 errors.

- [ ] **Step 6: 커밋**

```bash
git add packages/types/src/area_subscribers.ts \
        packages/types/src/area_subscribers.test.ts \
        packages/types/src/index.ts
git commit -m "feat(types): AreaSubscribersResponse 스키마 추가"
```

---

### Task 14: workers/api — GET /api/areas/:area/subscribers

**Files:**
- Create: `workers/api/src/routes/areas_subscribers.ts`
- Create: `workers/api/src/routes/areas_subscribers.test.ts`
- Modify: `workers/api/src/app.ts`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `workers/api/src/routes/areas_subscribers.test.ts`:

```ts
// GET /api/areas/:area/subscribers — service-auth + area 일치 가드 + join 결과
import { describe, it, expect, beforeEach } from "vitest";
import { env, SELF } from "cloudflare:test";
import { ensureActiveKey } from "../db/signing_keys";
import { signAreaToken } from "@popory/auth";

async function makeServiceToken(area: string): Promise<string> {
  const { kid, privateJwk } = await ensureActiveKey(env.DB);
  return await signAreaToken({
    privateJwk,
    kid,
    claims: {
      sub: "services-brief",
      email: "services-brief@popory.local",
      area,
      aud: "popory-portal",
    },
  });
}

describe("GET /api/areas/:area/subscribers", () => {
  beforeEach(async () => {
    await env.DB.exec("DELETE FROM area_subscriptions");
    await env.DB.exec("DELETE FROM users");
    await env.DB.prepare(
      `INSERT INTO users (sub, email, display_name, role, created_at)
       VALUES ('u1','a@x','A','member',1),('u2','b@x',NULL,'member',2)`,
    ).run();
    await env.DB.prepare(
      `INSERT INTO area_subscriptions (sub, area, enabled_at)
       VALUES ('u1','brief',1),('u2','brief',2),('u1','content',3)`,
    ).run();
  });

  it("auth 없으면 401", async () => {
    const res = await SELF.fetch("https://example.com/api/areas/brief/subscribers");
    expect(res.status).toBe(401);
  });

  it("area mismatch 시 403", async () => {
    const token = await makeServiceToken("content");
    const res = await SELF.fetch("https://example.com/api/areas/brief/subscribers", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status).toBe(403);
  });

  it("정상 호출 시 area 구독자만 반환", async () => {
    const token = await makeServiceToken("brief");
    const res = await SELF.fetch("https://example.com/api/areas/brief/subscribers", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status).toBe(200);
    const body = await res.json<{ subscribers: { email: string; display_name: string | null }[] }>();
    expect(body.subscribers).toHaveLength(2);
    expect(body.subscribers.map((s) => s.email).sort()).toEqual(["a@x", "b@x"]);
    const a = body.subscribers.find((s) => s.email === "a@x")!;
    expect(a.display_name).toBe("A");
    const b = body.subscribers.find((s) => s.email === "b@x")!;
    expect(b.display_name).toBeNull();
  });
});
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
pnpm --filter @popory/workers-api test -- areas_subscribers
```

Expected: FAIL — route 미등록 (404 또는 컴파일 에러).

- [ ] **Step 3: 라우트 구현**

Create `workers/api/src/routes/areas_subscribers.ts`:

```ts
// 영역 구독자 목록을 조회한다. service-auth 전용.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import type { AppVars } from "../middleware/session";

type Vars = AppVars & ServiceVars;

export function mountAreasSubscribers(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.get("/api/areas/:area/subscribers", requireService, async (c) => {
    const area = c.req.param("area");
    const svc = c.get("service")!;
    if (svc.area !== area) return c.text("area mismatch", 403);
    const { results } = await c.env.DB.prepare(
      `SELECT u.email, u.display_name
         FROM area_subscriptions s
         JOIN users u ON u.sub = s.sub
        WHERE s.area = ?
        ORDER BY u.email`,
    ).bind(area).all<{ email: string; display_name: string | null }>();
    return c.json({ subscribers: results });
  });
}
```

- [ ] **Step 4: app.ts에 mount 추가**

Read `workers/api/src/app.ts` first. Add import near top:

```ts
import { mountAreasSubscribers } from "./routes/areas_subscribers";
```

Then add `mountAreasSubscribers(app);` next to the other `mount*` calls (same file).

- [ ] **Step 5: 테스트 통과 + 회귀 확인**

```bash
pnpm --filter @popory/workers-api test
```

Expected: 신규 3개 + 기존 23 이상 모두 PASS.

- [ ] **Step 6: 커밋**

```bash
git add workers/api/src/routes/areas_subscribers.ts \
        workers/api/src/routes/areas_subscribers.test.ts \
        workers/api/src/app.ts
git commit -m "feat(api): GET /api/areas/:area/subscribers (service-auth)"
```

---

### Task 15: apps/portal — Markdown 렌더 + typography plugin

**Files:**
- Modify: `apps/portal/package.json`
- Modify: `apps/portal/tailwind.config.ts`
- Modify: `apps/portal/src/app/p/[area]/[id]/page.tsx`

- [ ] **Step 1: 의존성 추가**

```bash
cd /Users/daegong/projects/popory
pnpm --filter @popory/portal add react-markdown remark-gfm
pnpm --filter @popory/portal add -D @tailwindcss/typography
```

Expected: package.json에 세 패키지 항목 추가. lockfile 갱신.

- [ ] **Step 2: tailwind.config.ts에 typography plugin + popory 변형 추가**

Replace `apps/portal/tailwind.config.ts` 전체:

```ts
// 포털 Tailwind 설정. popory 토큰을 CSS 변수로 받고, prose-popory 변형을 정의한다.
import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        popory: {
          bg: "var(--popory-bg)",
          fg: "var(--popory-fg)",
          muted: "var(--popory-muted)",
          accent: "var(--popory-accent)",
          card: "var(--popory-card)",
          border: "var(--popory-border)",
        },
      },
      typography: {
        popory: {
          css: {
            "--tw-prose-body": "var(--popory-fg)",
            "--tw-prose-headings": "var(--popory-fg)",
            "--tw-prose-links": "var(--popory-accent)",
            "--tw-prose-quotes": "var(--popory-muted)",
            "--tw-prose-bullets": "var(--popory-muted)",
            "--tw-prose-counters": "var(--popory-muted)",
            "--tw-prose-hr": "var(--popory-border)",
            "--tw-prose-th-borders": "var(--popory-border)",
            "--tw-prose-td-borders": "var(--popory-border)",
            "--tw-prose-code": "var(--popory-fg)",
            "--tw-prose-pre-bg": "var(--popory-card)",
          },
        },
      },
    },
  },
  plugins: [typography],
};
export default config;
```

- [ ] **Step 3: /p/[area]/[id]/page.tsx 본문 부분 교체**

Replace `apps/portal/src/app/p/[area]/[id]/page.tsx` 전체:

```tsx
// 단일 publish 본문 (Markdown 렌더).
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { API_BASE } from "@/lib/env";

export default async function ItemPage({ params }: { params: Promise<{ area: string; id: string }> }) {
  const { id } = await params;
  const res = await fetch(`${API_BASE}/api/published_items/${id}`, { cache: "no-store" });
  if (!res.ok) return <main className="p-12">없는 글입니다.</main>;
  const item = (await res.json()) as { title: string; summary: string | null; body: string };
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-2xl font-semibold">{item.title}</h1>
      {item.summary && <p className="text-popory-muted mt-2">{item.summary}</p>}
      <article className="prose prose-popory mt-8">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ node, ...p }) => <a {...p} target="_blank" rel="noopener noreferrer" />,
          }}
        >
          {item.body}
        </ReactMarkdown>
      </article>
    </main>
  );
}
```

- [ ] **Step 4: 빌드·typecheck 확인**

```bash
pnpm --filter @popory/portal typecheck
pnpm --filter @popory/portal build
```

Expected: 두 명령 모두 0 errors. `.next/` 생성.

- [ ] **Step 5: 브라우저 확인 (선택)**

```bash
pnpm --filter @popory/portal dev
```

`/p/brief/<id>`(테스트 데이터)를 열어 Markdown이 prose 스타일로 렌더되는지 눈으로 확인.

- [ ] **Step 6: 커밋**

```bash
git add apps/portal/package.json apps/portal/tailwind.config.ts \
        apps/portal/src/app/p/[area]/[id]/page.tsx pnpm-lock.yaml
git commit -m "feat(portal): /p/:area/:id Markdown 렌더링 (@tailwindcss/typography 도입)"
```

---

### Task 16: services/brief/README.md — 운영 가이드

**Files:**
- Create: `services/brief/README.md`

> 운영자가 1회 따라하는 셋업 + 일상 운영 + 키 회전·롤백 절차를 한 문서에. 코드 없음, 가이드만.

- [ ] **Step 1: README 작성**

Create `services/brief/README.md`:

````markdown
<!-- services/brief: routine과 portal 사이의 메일 발송·publish 다리. 운영 가이드. -->
# services/brief

routine이 만든 부동산 이슈 브리핑 Markdown을 받아 (a) 구독자에게 메일 발송하고 (b) portal 공개 아카이브에 publish 한다. daily-brief 자산을 monorepo 안으로 흡수한 결과물.

설계. `../../docs/superpowers/specs/2026-05-28-popory-f1-brief-design.md`
플랜. `../../docs/superpowers/plans/2026-05-28-popory-f1-brief.md`

## 1. 1회 셋업

```bash
cd services/brief

# 1.1 venv + deps
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 1.2 Google OAuth client → secrets/credentials.json 으로 저장
#     (Google Cloud Console > Credentials > Desktop client JSON 다운로드)

# 1.3 Gmail refresh token 발급 (URL이 출력되면 브라우저에 붙여넣어 동의)
.venv/bin/python auth_setup.py

# 1.4 services/brief ES256 키 생성
.venv/bin/python -m popory_brief.scripts.keygen \
  --kid services-brief-2026-05 \
  --out secrets/brief_signing_key.json

# 1.5 portal D1에 public key 등록 (1회)
#     1.4 출력의 public_jwk 전체 JSON을 그대로 SQL VALUES에 붙여넣는다.
cd ../..
pnpm exec wrangler d1 execute popory \
  --remote --command "INSERT INTO signing_keys
    (kid, alg, public_jwk, private_jwk, status, created_at)
    VALUES ('services-brief-2026-05', 'ES256',
            '<여기에 public_jwk JSON 전체>', NULL,
            'active', strftime('%s','now'))"
```

## 2. 환경변수

routine 호출 시 다음 두 변수가 필요하다 (`secrets/portal_endpoints.env` 에 저장 후 source).

```
POPORY_BRIEF_KEY_FILE=/Users/daegong/projects/popory/services/brief/secrets/brief_signing_key.json
POPORY_PORTAL_API_BASE=https://api.poporyfamily.com
```

## 3. routine 호출 시퀀스

```bash
BRIEF_DIR=/Users/daegong/projects/popory/services/brief
DATE=$(TZ=Asia/Seoul date +%Y-%m-%d)
BODY=/tmp/brief_${DATE}.md
META=/tmp/brief_${DATE}.meta.json

source ${BRIEF_DIR}/secrets/portal_endpoints.env

# 1) 수신인 조회
SUBSCRIBERS=$(${BRIEF_DIR}/.venv/bin/python ${BRIEF_DIR}/fetch_subscribers.py --area brief)

# 2) 사용자별 발송
echo "$SUBSCRIBERS" | jq -r '.subscribers[].email' | while read EMAIL; do
  ${BRIEF_DIR}/.venv/bin/python ${BRIEF_DIR}/send_gmail.py \
    --to "$EMAIL" \
    --from "부동산 이슈 브리핑 <rarebirds@gmail.com>" \
    --subject "$(jq -r .title $META)" \
    --body-file "$BODY" --md
done

# 3) 발송 끝난 뒤 publish 1회
${BRIEF_DIR}/.venv/bin/python ${BRIEF_DIR}/publish_to_portal.py \
  --area brief --meta-file "$META" --body-file "$BODY"
```

## 4. Exit code 규약

| code | 의미 | 회복 |
|------|------|------|
| 0 | 성공 | — |
| 2 | 설정 누락 (token.json·signing_key.json·env 없음) | setup 재실행 |
| 3 | 인증 실패 (Gmail refresh / portal 401·403) | 키·토큰 재발급 |
| 4 | 외부 API 4xx | 입력 점검 — 재시도 안 함 |
| 5 | 외부 API 5xx / 네트워크 (1회 재시도 후) | 사후 점검 |

routine 분기.

```
fetch_subscribers     exit ≠ 0  →  routine 중단.
send_gmail (1명)      exit ≠ 0  →  해당 수신자 skip, 다음 진행.
send_gmail 전원 실패            →  publish 호출 안 함.
publish_to_portal     exit ≠ 0  →  메일은 이미 갔으므로 로그만 남기고 종료.
```

## 5. 일자별 로그

`logs/YYYY-MM-DD.log` (JSONL, KST). 모든 CLI가 append. 본문·메일 본문은 절대 저장하지 않는다(메타만).

## 6. 키 회전

```bash
# 1) 새 키 생성
.venv/bin/python -m popory_brief.scripts.keygen \
  --kid services-brief-2027-XX \
  --out secrets/brief_signing_key.json.new

# 2) portal D1에 새 키 active, 기존 키 grace
pnpm exec wrangler d1 execute popory --remote --command "
  UPDATE signing_keys SET status='grace' WHERE kid='services-brief-2026-05';
  INSERT INTO signing_keys (kid, alg, public_jwk, private_jwk, status, created_at)
    VALUES ('services-brief-2027-XX','ES256','<새 public_jwk>',NULL,'active',strftime('%s','now'));
"

# 3) 새 키 파일 교체
mv secrets/brief_signing_key.json secrets/brief_signing_key.json.bak
mv secrets/brief_signing_key.json.new secrets/brief_signing_key.json

# 4) 며칠 후 grace 키 retire
pnpm exec wrangler d1 execute popory --remote --command "
  UPDATE signing_keys SET status='retired', retired_at=strftime('%s','now')
   WHERE kid='services-brief-2026-05';
"
```

## 7. 키 유출 즉시 차단

```bash
pnpm exec wrangler d1 execute popory --remote --command "
  UPDATE signing_keys SET status='retired', retired_at=strftime('%s','now')
   WHERE kid='services-brief-2026-05';
"
```

이후 §6 1~3 단계로 새 키 발급·교체.

## 8. 이전·cutover 진행 단계

- Phase A. 새 코드 정착·키 등록·curl 단위 점검.
- Phase B. routine은 기존 daily-brief send_gmail 그대로 사용 + publish만 새 코드. 7일 dry-run.
- Phase C. routine을 §3 시퀀스로 교체. 7일 운영.
- Phase D. `/Users/daegong/projects/daily-brief/`를 `daily-brief-archived-YYYYMMDD.tar.gz`로 묶고 원본 디렉토리 삭제.

세부 절차·롤백은 spec §7 참조.

## 9. 보안

- `secrets/` 디렉토리는 git 이중 ignore. 절대 커밋 금지.
- `gmail.send` 단일 scope · 읽기 권한 없음.
- 로그에 본문·메일 본문 저장 안 함. 메타만(수신인 email·message_id·publish id).
- ES256 private key는 Mac 로컬에만 존재.

## 10. 테스트

```bash
cd services/brief
.venv/bin/pytest -v
```
````

- [ ] **Step 2: 커밋**

```bash
git add services/brief/README.md
git commit -m "docs(brief): services/brief 운영 가이드 (셋업·routine·키 회전·롤백)"
```

---

## Final Verification

모든 task가 끝난 뒤 한 번에 확인한다.

- [ ] **Step 1: Python 테스트 전체**

```bash
cd /Users/daegong/projects/popory/services/brief
.venv/bin/pytest -v
```

Expected: log/markdown/jwt_signer/portal_client/send_gmail_md_flag/fetch_subscribers/publish_to_portal 모든 테스트 PASS.

- [ ] **Step 2: TypeScript typecheck + 테스트 전체**

```bash
cd /Users/daegong/projects/popory
pnpm -r typecheck
pnpm -r test
```

Expected: 6/6 패키지 typecheck 0 errors. workers/api/portal 모든 vitest PASS (F0 23 + F1 추가).

- [ ] **Step 3: Phase A 통합 검증 (수동)**

spec §7 Phase A의 curl 단위 점검을 실제 prod portal로 한 번 실행하고, 생성된 published_item을 admin에서 삭제. 본 plan에 포함된 코드 작업이 모두 끝난 시점에 운영자(사람)가 수행한다.

---

## Spec coverage 자가 점검

| Spec 섹션 | 구현 Task |
|----------|-----------|
| §1 검증 기준 1 (메일 + publish + 비로그인) | Task 8, 11, 15 |
| §1 검증 기준 2 (독립 재시도) | Task 7, 8, 10, 11 (exit code 규약) |
| §1 검증 기준 4 (회귀 없음) | Task 12, 14 (vitest 회귀 확인) |
| §3 디렉토리 구조 | Task 1 |
| §4 ES256 키페어 + 자가 서명 | Task 5, 6, 16 §1 |
| §5.1 마이그레이션 0002 | Task 12 |
| §5.2 GET /api/areas/:area/subscribers | Task 13, 14 |
| §5.4 Markdown 렌더링 | Task 15 |
| §6 routine 호출 시퀀스 | Task 16 README §3 |
| §7 Phase 진행 | Task 16 README §8 + Final Verification §3 |
| §8.2 메일 HTML envelope | Task 4 |
| §8.3 publish payload 매핑 | Task 11 |
| §9.1 Exit code 통일 | Task 7 + Task 16 README §4 |
| §9.3 services/brief 로그 | Task 3, 8, 10, 11 |
| §9.5 admin overview 헬스 표시 | **(plan 미포함 — spec §9.5에서 F1 범위 안이지만 portal admin UI 변경은 plan 밖에 두었다. cutover 후 별도 task)** |

§9.5 admin overview의 "마지막 publish 시각" 표시는 운영자가 publish 결과만 보면 충분하다는 판단으로 별도 task에서 다룬다(plan 외 follow-up). 다른 모든 spec 요구사항은 Task 매핑이 있다.
