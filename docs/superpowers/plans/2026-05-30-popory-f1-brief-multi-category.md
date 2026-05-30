<!-- F1 services/brief 멀티 카테고리 확장 implementation plan. -->
# F1 — services/brief 멀티 카테고리 확장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** services/brief를 단일 부동산 카테고리에서 디렉토리 스캔 기반 멀티 카테고리 시스템으로 전환. SKILL.md 파일 1개 추가만으로 신규 카테고리 운영 가능.

**Architecture:** `services/brief/categories/{slug}/SKILL.md` 디렉토리를 스캔해 활성 카테고리 목록을 결정. 카테고리는 `standalone`(개별 메일 1통) 또는 `bundled`(수신자별 합쳐 1통) 발송 모드. portal area는 `brief-{slug}` 형식으로 카테고리별 독립. 단일 launchd 09:00 KST cron 유지.

**Tech Stack:** Python 3.11+ (pytest, PyYAML), bash (launchd entry), claude CLI (본문 생성, Claude Max OAuth), Cloudflare D1 (portal 데이터)

**Reference spec:** [docs/superpowers/specs/2026-05-30-popory-f1-brief-multi-category-design.md](../specs/2026-05-30-popory-f1-brief-multi-category-design.md)

---

## File Map

**Create**
- `services/brief/popory_brief/categories.py` — SKILL.md 스캔·파싱·검증 모듈
- `services/brief/categories/realestate/SKILL.md` — 부동산 카테고리 정의 (기존 prompt 이전)
- `services/brief/build_bundles.py` — bundled 카테고리 수신자별 본문 빌더
- `services/brief/tests/test_categories.py` — categories.py 단위 테스트

**Modify**
- `services/brief/pyproject.toml` — PyYAML 의존성 추가
- `services/brief/generate_brief.py` — `--category {slug}` 필수 인자, SKILL.md system prompt 로드
- `services/brief/run_daily.sh` — 디렉토리 스캔 → 카테고리별 generate/publish → standalone/bundled 발송 분리. `--dry-run` 옵션

**Delete**
- `services/brief/popory_brief/briefing_prompt.py` — 내용은 realestate SKILL.md로 이전

**Unchanged (호환)**
- `services/brief/fetch_subscribers.py`, `services/brief/publish_to_portal.py`, `services/brief/send_gmail.py`
- `~/Library/LaunchAgents/com.popory.brief.plist`

---

## Task 1: popory_brief.categories 모듈 + 단위 테스트 (TDD)

**Files:**
- Create: `services/brief/popory_brief/categories.py`
- Create: `services/brief/tests/test_categories.py`
- Modify: `services/brief/pyproject.toml`

- [ ] **Step 1: pyproject.toml에 PyYAML dep 추가**

`services/brief/pyproject.toml`의 `dependencies` 리스트에 한 줄 추가.

```toml
dependencies = [
  "google-api-python-client>=2.130",
  "google-auth-oauthlib>=1.2",
  "jwcrypto>=1.5.6",
  "markdown-it-py>=3.0",
  "mdit-py-plugins>=0.4",
  "PyYAML>=6.0",
  "requests>=2.32",
  "linkify-it-py>=0.5",
]
```

- [ ] **Step 2: venv에 PyYAML 설치**

```bash
cd /Users/daegong/projects/popory/services/brief
.venv/bin/pip install "PyYAML>=6.0"
```

기대 출력. `Successfully installed PyYAML-6.x.x` 또는 이미 설치돼 있다는 메시지.

- [ ] **Step 3: 첫 실패 테스트 작성 (행복 경로)**

`services/brief/tests/test_categories.py` 생성. 첫 줄에 한국어 헤더 주석 포함 (CLAUDE.md 6번).

```python
# popory_brief.categories 단위 테스트.
"""SKILL.md 스캔·파싱·검증 + 카테고리 분류 동작 확인."""
from __future__ import annotations
from pathlib import Path
import textwrap
import pytest

from popory_brief import categories


def _write_skill(
    tmp_path: Path,
    dir_name: str,
    frontmatter_yaml: str | None = None,
    body: str = "system prompt body\n",
) -> Path:
    skill_dir = tmp_path / dir_name
    skill_dir.mkdir()
    fm = frontmatter_yaml if frontmatter_yaml is not None else textwrap.dedent(f"""\
        slug: {dir_name}
        name: {dir_name.title()}
        delivery_mode: standalone
        subject_template: "[{{name}}] {{date}}"
        sender_name: "{{name}} bot"
        enabled: true
        """)
    (skill_dir / "SKILL.md").write_text(f"---\n{fm}---\n\n{body}", encoding="utf-8")
    return skill_dir / "SKILL.md"


def test_scan_returns_category(tmp_path):
    _write_skill(tmp_path, "foo")
    cats = categories._scan(tmp_path)
    assert len(cats) == 1
    c = cats[0]
    assert c.slug == "foo"
    assert c.name == "Foo"
    assert c.delivery_mode == "standalone"
    assert c.area == "brief-foo"
    assert "system prompt body" in c.system_prompt
    assert c.enabled is True


def test_subject_and_sender_format(tmp_path):
    _write_skill(tmp_path, "foo")
    c = categories._scan(tmp_path)[0]
    assert c.subject("2026-05-31") == "[Foo] 2026-05-31"
    assert c.sender() == "Foo bot"
```

- [ ] **Step 4: 테스트 실행 → 실패 확인 (모듈 없음)**

```bash
cd /Users/daegong/projects/popory/services/brief
.venv/bin/pytest tests/test_categories.py -v
```

기대 출력. `ModuleNotFoundError: No module named 'popory_brief.categories'` 또는 ImportError.

- [ ] **Step 5: categories.py 최소 구현 (parse + scan + Category 데이터클래스)**

`services/brief/popory_brief/categories.py` 생성.

```python
# popory_brief.categories — SKILL.md 디렉토리 스캔과 카테고리 메타 로드.
"""
services/brief/categories/{slug}/SKILL.md 디렉토리를 스캔해 활성 카테고리 목록을 반환.

API.
    list_categories(root=ROOT) -> list[Category]      # enabled 만
    load_category(slug, root=ROOT) -> Category        # 단일 (enabled 무시)
    standalone_categories(root=ROOT) -> list[Category]
    bundled_categories(root=ROOT) -> list[Category]
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parent.parent / "categories"
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
VALID_MODES = {"standalone", "bundled"}
REQUIRED = ("slug", "name", "delivery_mode", "subject_template", "sender_name", "enabled")


@dataclass(frozen=True)
class Category:
    slug: str
    name: str
    delivery_mode: str
    subject_template: str
    sender_name: str
    enabled: bool
    system_prompt: str

    @property
    def area(self) -> str:
        return f"brief-{self.slug}"

    def subject(self, date: str) -> str:
        return self.subject_template.format(name=self.name, date=date)

    def sender(self) -> str:
        return self.sender_name.format(name=self.name)


def _parse_skill_md(path: Path) -> Category:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: frontmatter not found")
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        raise ValueError(f"{path}: frontmatter not closed")
    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip()
    missing = [k for k in REQUIRED if k not in meta]
    if missing:
        raise ValueError(f"{path}: missing fields: {missing}")
    if not SLUG_RE.match(str(meta["slug"])):
        raise ValueError(f"{path}: invalid slug {meta['slug']!r}")
    if meta["delivery_mode"] not in VALID_MODES:
        raise ValueError(f"{path}: invalid delivery_mode {meta['delivery_mode']!r}")
    return Category(
        slug=str(meta["slug"]),
        name=str(meta["name"]),
        delivery_mode=str(meta["delivery_mode"]),
        subject_template=str(meta["subject_template"]),
        sender_name=str(meta["sender_name"]),
        enabled=bool(meta["enabled"]),
        system_prompt=body,
    )


def _scan(root: Path = ROOT) -> list[Category]:
    if not root.exists():
        return []
    cats: list[Category] = []
    seen: set[str] = set()
    for skill_path in sorted(root.glob("*/SKILL.md")):
        cat = _parse_skill_md(skill_path)
        if cat.slug in seen:
            raise ValueError(f"duplicate slug {cat.slug!r}")
        seen.add(cat.slug)
        cats.append(cat)
    return cats


def list_categories(root: Path = ROOT) -> list[Category]:
    return [c for c in _scan(root) if c.enabled]


def load_category(slug: str, root: Path = ROOT) -> Category:
    for c in _scan(root):
        if c.slug == slug:
            return c
    raise KeyError(f"category {slug!r} not found")


def standalone_categories(root: Path = ROOT) -> list[Category]:
    return [c for c in list_categories(root) if c.delivery_mode == "standalone"]


def bundled_categories(root: Path = ROOT) -> list[Category]:
    return [c for c in list_categories(root) if c.delivery_mode == "bundled"]
```

- [ ] **Step 6: 테스트 실행 → 통과 확인**

```bash
.venv/bin/pytest tests/test_categories.py -v
```

기대 출력. `test_scan_returns_category PASSED` + `test_subject_and_sender_format PASSED` (2 passed).

- [ ] **Step 7: 검증 테스트 추가 (실패 케이스들)**

`tests/test_categories.py` 끝에 append.

```python
def test_missing_required_field_raises(tmp_path):
    fm = "slug: foo\nname: Foo\ndelivery_mode: standalone\nenabled: true\n"
    _write_skill(tmp_path, "foo", frontmatter_yaml=fm)
    with pytest.raises(ValueError, match="missing fields"):
        categories._scan(tmp_path)


def test_invalid_slug_raises(tmp_path):
    fm = textwrap.dedent("""\
        slug: "Bad_Slug"
        name: x
        delivery_mode: standalone
        subject_template: "x"
        sender_name: "x"
        enabled: true
        """)
    _write_skill(tmp_path, "anydir", frontmatter_yaml=fm)
    with pytest.raises(ValueError, match="invalid slug"):
        categories._scan(tmp_path)


def test_invalid_delivery_mode_raises(tmp_path):
    fm = textwrap.dedent("""\
        slug: foo
        name: Foo
        delivery_mode: weekly
        subject_template: "x"
        sender_name: "x"
        enabled: true
        """)
    _write_skill(tmp_path, "foo", frontmatter_yaml=fm)
    with pytest.raises(ValueError, match="invalid delivery_mode"):
        categories._scan(tmp_path)


def test_duplicate_slug_raises(tmp_path):
    _write_skill(tmp_path, "dir1", frontmatter_yaml=textwrap.dedent("""\
        slug: same
        name: A
        delivery_mode: standalone
        subject_template: "x"
        sender_name: "x"
        enabled: true
        """))
    _write_skill(tmp_path, "dir2", frontmatter_yaml=textwrap.dedent("""\
        slug: same
        name: B
        delivery_mode: bundled
        subject_template: "x"
        sender_name: "x"
        enabled: true
        """))
    with pytest.raises(ValueError, match="duplicate slug"):
        categories._scan(tmp_path)


def test_missing_frontmatter_raises(tmp_path):
    skill_dir = tmp_path / "foo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("no frontmatter here\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frontmatter not found"):
        categories._scan(tmp_path)
```

- [ ] **Step 8: 테스트 실행 → 검증 테스트 통과**

```bash
.venv/bin/pytest tests/test_categories.py -v
```

기대 출력. 7 passed (행복 2 + 검증 5).

- [ ] **Step 9: 분류 / 필터 테스트 추가**

`tests/test_categories.py` 끝에 append.

```python
def test_enabled_filter(tmp_path):
    _write_skill(tmp_path, "active")
    _write_skill(tmp_path, "inactive", frontmatter_yaml=textwrap.dedent("""\
        slug: inactive
        name: Inactive
        delivery_mode: standalone
        subject_template: "x"
        sender_name: "x"
        enabled: false
        """))
    cats = categories.list_categories(tmp_path)
    assert [c.slug for c in cats] == ["active"]


def test_standalone_and_bundled_filters(tmp_path):
    _write_skill(tmp_path, "alpha", frontmatter_yaml=textwrap.dedent("""\
        slug: alpha
        name: Alpha
        delivery_mode: standalone
        subject_template: "x"
        sender_name: "x"
        enabled: true
        """))
    _write_skill(tmp_path, "beta", frontmatter_yaml=textwrap.dedent("""\
        slug: beta
        name: Beta
        delivery_mode: bundled
        subject_template: "x"
        sender_name: "x"
        enabled: true
        """))
    assert [c.slug for c in categories.standalone_categories(tmp_path)] == ["alpha"]
    assert [c.slug for c in categories.bundled_categories(tmp_path)] == ["beta"]


def test_load_category_by_slug(tmp_path):
    _write_skill(tmp_path, "foo")
    c = categories.load_category("foo", tmp_path)
    assert c.name == "Foo"


def test_load_category_unknown_raises(tmp_path):
    with pytest.raises(KeyError, match="missing"):
        categories.load_category("missing", tmp_path)
```

- [ ] **Step 10: 테스트 실행 → 전부 통과 확인**

```bash
.venv/bin/pytest tests/test_categories.py -v
```

기대 출력. 11 passed.

- [ ] **Step 11: 회귀 확인 — 기존 테스트 전부 통과**

```bash
.venv/bin/pytest -v
```

기대 출력. 기존 테스트 + 새 테스트 모두 PASS (categories 신규 모듈은 기존 코드와 분리되어 회귀 없음).

- [ ] **Step 12: commit**

```bash
cd /Users/daegong/projects/popory
git add services/brief/popory_brief/categories.py \
        services/brief/tests/test_categories.py \
        services/brief/pyproject.toml
git commit -m "$(cat <<'EOF'
feat(brief): SKILL.md 기반 멀티 카테고리 스캔 모듈 추가

popory_brief.categories. categories/{slug}/SKILL.md 디렉토리를 스캔해 frontmatter를 파싱하고 standalone/bundled로 분류. PyYAML 의존성 추가. 11개 단위 테스트.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: realestate SKILL.md 작성 + briefing_prompt.py 삭제

**Files:**
- Create: `services/brief/categories/realestate/SKILL.md`
- Delete: `services/brief/popory_brief/briefing_prompt.py`

- [ ] **Step 1: realestate 디렉토리 + SKILL.md 생성**

`services/brief/categories/realestate/SKILL.md` 신규 작성. frontmatter는 SKILL.md 표준 형식이라 한국어 헤더 주석 생략 (CLAUDE.md 6번 데이터·픽스처 예외 적용 — 파서가 `---\n` 시작 가정).

frontmatter 본문은 아래 6필드 고정. body 부분은 **기존 `services/brief/popory_brief/briefing_prompt.py` 의 `SYSTEM_PROMPT` 문자열 본문(""" ... """ 안쪽)을 그대로 복사** (Korean prompt 본문 87줄).

```markdown
---
slug: realestate
name: 부동산
delivery_mode: standalone
subject_template: "[{name} 이슈 브리핑] {date}"
sender_name: "{name} 이슈 브리핑"
enabled: true
---

당신은 한국 부동산 이슈 데일리 브리핑 작성자입니다. 매일 정해진 시각에 자동 실행되어 실행일 KST 00:00 이후 발행된 부동산 관련 뉴스를 수집·정리해 1페이지 핵심 요약을 작성합니다. 5분 안에 읽고 의사결정에 쓸 수 있어야 합니다. **사실과 출처 우선, 분석·전망 최소화.**

## 1. 수집 절차
(... 기존 briefing_prompt.py SYSTEM_PROMPT 본문을 줄바꿈·들여쓰기 포함 그대로 복사 — 마지막 `## 6. 출력 형식 자가 점검` 까지)
```

복사 출처. `services/brief/popory_brief/briefing_prompt.py:3-87`.

- [ ] **Step 2: smoke 테스트 — load_category로 정상 로드 확인**

```bash
cd /Users/daegong/projects/popory/services/brief
.venv/bin/python -c "from popory_brief.categories import load_category; c = load_category('realestate'); print(c.slug, c.name, c.delivery_mode, c.area); print('prompt len:', len(c.system_prompt))"
```

기대 출력. `realestate 부동산 standalone brief-realestate` 그리고 `prompt len: ` 뒤 3000 이상의 숫자 (원본 본문 길이가 ~3000~4000자).

- [ ] **Step 3: briefing_prompt.py 사용처가 generate_brief.py 한 곳뿐인지 재확인**

```bash
grep -rn "briefing_prompt" /Users/daegong/projects/popory/services/brief --include="*.py" | grep -v __pycache__
```

기대 출력. `generate_brief.py:23: from popory_brief.briefing_prompt import SYSTEM_PROMPT` 한 줄만. (Task 3에서 이 import 제거 예정)

- [ ] **Step 4: briefing_prompt.py 삭제**

```bash
cd /Users/daegong/projects/popory
git rm services/brief/popory_brief/briefing_prompt.py
```

(generate_brief.py가 아직 이 모듈을 import 중이라 다음 Task 3 전에는 `python generate_brief.py`를 호출하면 ImportError. 단위 테스트는 영향 없음.)

- [ ] **Step 5: 기존 테스트 + 새 카테고리 테스트 통과 확인**

```bash
cd /Users/daegong/projects/popory/services/brief
.venv/bin/pytest -v
```

기대 출력. 모두 PASS. briefing_prompt를 import하는 테스트는 없음.

- [ ] **Step 6: commit**

```bash
cd /Users/daegong/projects/popory
git add services/brief/categories/realestate/SKILL.md
git commit -m "$(cat <<'EOF'
refactor(brief): 부동산 prompt를 categories/realestate/SKILL.md로 이전

기존 popory_brief.briefing_prompt 모듈 제거. system prompt 본문은 SKILL.md frontmatter(slug=realestate, delivery_mode=standalone, subject/sender 템플릿) 뒤 body에 그대로 옮김.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: generate_brief.py에 --category 인자

**Files:**
- Modify: `services/brief/generate_brief.py`

- [ ] **Step 1: generate_brief.py 전체 재작성**

기존 파일 헤더 주석(첫 줄 한국어)은 유지. `briefing_prompt` import 제거, `categories.load_category` import. `--category` 필수 인자 추가. 출력 파일명에 `{slug}` 포함. 로그에 `category` 필드 추가.

`services/brief/generate_brief.py` 전체.

```python
# claude CLI(비대화형, Claude Max 구독)로 카테고리별 브리핑 본문·메타 생성. Anthropic API key 불필요.
"""
사용법.
    python generate_brief.py --category {slug} [--date YYYY-MM-DD] [--model claude-sonnet-4-6]

성공 시 stdout JSON 한 줄.
    {"status":"ok","category":"...","date":"...","body_file":"...","meta_file":"..."}

실패 시 비제로 exit code (2/4/5).

요구사항.
    /opt/homebrew/bin/claude (Claude Code CLI). Claude Max OAuth는 keychain에서 자동 로드.
    services/brief/categories/{slug}/SKILL.md 존재.
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

from popory_brief.categories import load_category
from popory_brief.log import append_log, KST

LOGS_DIR = Path(__file__).resolve().parent / "logs"
CLAUDE_BIN = "/opt/homebrew/bin/claude"
DEFAULT_MODEL = "claude-sonnet-4-6"
TIMEOUT_SECONDS = 600


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--category", required=True, help="categories/{slug}/SKILL.md 의 slug")
    p.add_argument("--date", default=None, help="기준 KST 일자 (YYYY-MM-DD). 생략 시 오늘")
    p.add_argument("--model", default=DEFAULT_MODEL)
    args = p.parse_args()

    if not Path(CLAUDE_BIN).exists():
        print(f"error: claude CLI not found at {CLAUDE_BIN}", file=sys.stderr)
        sys.exit(2)

    try:
        category = load_category(args.category)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)

    if args.date:
        date_obj = datetime.datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=KST)
    else:
        date_obj = datetime.datetime.now(KST)
    date_str = date_obj.strftime("%Y-%m-%d")
    published_at = int(date_obj.timestamp())

    sys_prompt_path = Path(f"/tmp/brief_system_{category.slug}_{date_str}.txt")
    sys_prompt_path.write_text(category.system_prompt, encoding="utf-8")

    user_msg = (
        f"오늘은 {date_str} (KST)입니다. 시스템 매뉴얼의 절차를 따라 오늘의 {category.name} 이슈 브리핑을 작성하세요. "
        f"WebSearch 도구로 그날 발행된 보도자료·뉴스를 적극 수집한 뒤, "
        f"마지막 응답에 <body_markdown>...</body_markdown> 과 <meta_json>...</meta_json> 두 태그를 정확히 포함하세요. "
        f"meta_json의 published_at은 {published_at}을 그대로 사용하세요."
    )

    cmd = [
        CLAUDE_BIN,
        "--print",
        "--model", args.model,
        "--allowed-tools", "WebSearch", "WebFetch",
        "--system-prompt-file", str(sys_prompt_path),
        "--output-format", "text",
    ]

    try:
        result = subprocess.run(
            cmd,
            input=user_msg,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        print(f"error: claude CLI timeout after {TIMEOUT_SECONDS}s", file=sys.stderr)
        sys.exit(5)
    finally:
        sys_prompt_path.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"error: claude CLI exit {result.returncode}", file=sys.stderr)
        print(f"--- stderr (last 800 chars) ---\n{result.stderr[-800:]}", file=sys.stderr)
        sys.exit(5)

    final_text = result.stdout

    body_m = re.search(r"<body_markdown>(.*?)</body_markdown>", final_text, re.DOTALL)
    meta_m = re.search(r"<meta_json>\s*(\{.*?\})\s*</meta_json>", final_text, re.DOTALL)
    if not body_m or not meta_m:
        print("error: claude 응답에서 body_markdown/meta_json 태그를 찾지 못함", file=sys.stderr)
        print("--- response last 1000 chars ---\n" + final_text[-1000:], file=sys.stderr)
        sys.exit(4)

    body = body_m.group(1).strip()
    try:
        meta = json.loads(meta_m.group(1).strip())
    except json.JSONDecodeError as e:
        print(f"error: meta_json 파싱 실패: {e}", file=sys.stderr)
        print(meta_m.group(1), file=sys.stderr)
        sys.exit(4)

    body_path = Path(f"/tmp/brief_{category.slug}_{date_str}.md")
    meta_path = Path(f"/tmp/brief_{category.slug}_{date_str}.meta.json")
    body_path.write_text(body, encoding="utf-8")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    append_log(LOGS_DIR, {
        "cli": "generate_brief", "status": "ok",
        "category": category.slug, "date": date_str,
        "body_chars": len(body), "title": meta.get("title"),
    })

    print(json.dumps({
        "status": "ok",
        "category": category.slug,
        "date": date_str,
        "body_file": str(body_path),
        "meta_file": str(meta_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: argparse 동작 확인 (claude CLI 호출 없이)**

```bash
cd /Users/daegong/projects/popory/services/brief
.venv/bin/python generate_brief.py --help
```

기대 출력. `--category` 필수 인자가 usage에 표시.

- [ ] **Step 3: 잘못된 카테고리 시 exit 2 확인**

```bash
.venv/bin/python generate_brief.py --category nonexistent 2>&1
echo "exit=$?"
```

기대 출력. `error: ... 'nonexistent' not found` + `exit=2`.

- [ ] **Step 4: 기존 회귀 테스트 통과 확인**

```bash
.venv/bin/pytest -v
```

기대 출력. 모두 PASS.

- [ ] **Step 5: commit**

```bash
cd /Users/daegong/projects/popory
git add services/brief/generate_brief.py services/brief/popory_brief/briefing_prompt.py
git commit -m "$(cat <<'EOF'
feat(brief): generate_brief.py에 --category 인자

popory_brief.briefing_prompt 단일 import를 popory_brief.categories.load_category로 대체. system prompt와 메일 메타(name 등)는 SKILL.md frontmatter에서 로드. 출력 파일명에 {slug} 포함.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: build_bundles.py 신규 (bundled 카테고리 묶음 빌더)

**Files:**
- Create: `services/brief/build_bundles.py`

- [ ] **Step 1: build_bundles.py 작성**

`services/brief/build_bundles.py`. 첫 줄 한국어 헤더 (CLAUDE.md 6번).

```python
# bundled 카테고리들을 수신자별 본문으로 묶어 JSONL로 출력하는 헬퍼.
"""
사용법.
    python build_bundles.py --slugs s1,s2,s3 --date 2026-05-31 [--gen-failed s4,s5]

흐름.
    각 bundled slug 별 fetch_subscribers → 본문 파일 읽기 → 수신자 union → 수신자별로
    구독한 bundled 카테고리만 ## name 헤더로 합쳐 /tmp/bundle_{email_hash}_{date}.md 작성.

stdout JSONL (수신자 1명당 1줄).
    {"email":"...", "body_file":"/tmp/bundle_..."}

stderr는 사람 읽기용 로그. 실패한 수신자는 skip + stderr 기록 후 다음 진행.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from popory_brief.categories import load_category

BRIEF_DIR = Path(__file__).resolve().parent


def fetch_subscribers(slug: str) -> list[str]:
    result = subprocess.run(
        [sys.executable, str(BRIEF_DIR / "fetch_subscribers.py"), "--area", f"brief-{slug}"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(
            f"fetch_subscribers --area brief-{slug} exit {result.returncode}: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"fetch_subscribers --area brief-{slug} bad json: {e}", file=sys.stderr)
        return []
    return [s["email"] for s in data.get("subscribers", [])]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--slugs", required=True, help="comma-separated bundled category slugs")
    p.add_argument("--date", required=True)
    p.add_argument("--gen-failed", default="", help="comma-separated slugs that failed generate")
    args = p.parse_args()

    slugs = [s for s in args.slugs.split(",") if s]
    failed = {s for s in args.gen_failed.split(",") if s}

    subs_by_slug: dict[str, set[str]] = {}
    body_by_slug: dict[str, str] = {}
    name_by_slug: dict[str, str] = {}

    for slug in slugs:
        try:
            cat = load_category(slug)
        except KeyError as e:
            print(f"skip slug={slug}: {e}", file=sys.stderr)
            continue
        name_by_slug[slug] = cat.name
        if slug in failed:
            continue
        subs_by_slug[slug] = set(fetch_subscribers(slug))
        body_path = Path(f"/tmp/brief_{slug}_{args.date}.md")
        if not body_path.exists():
            print(f"skip slug={slug}: body file missing {body_path}", file=sys.stderr)
            failed.add(slug)
            continue
        body_by_slug[slug] = body_path.read_text(encoding="utf-8")

    all_emails = sorted({e for subs in subs_by_slug.values() for e in subs})

    for email in all_emails:
        sections = []
        for slug in slugs:
            if slug not in body_by_slug:
                continue
            if email not in subs_by_slug.get(slug, set()):
                continue
            sections.append(f"## {name_by_slug[slug]}\n\n{body_by_slug[slug]}")
        if not sections:
            continue
        bundle_md = "\n\n".join(sections)
        if failed:
            failed_names = ", ".join(sorted(name_by_slug.get(s, s) for s in failed))
            bundle_md += f"\n\n---\n\n> 일부 카테고리 본문 생성 실패: {failed_names}\n"
        email_hash = hashlib.sha1(email.encode()).hexdigest()[:12]
        body_path = Path(f"/tmp/bundle_{email_hash}_{args.date}.md")
        body_path.write_text(bundle_md, encoding="utf-8")
        print(json.dumps({"email": email, "body_file": str(body_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: --help 동작 확인**

```bash
cd /Users/daegong/projects/popory/services/brief
.venv/bin/python build_bundles.py --help
```

기대 출력. usage 표시 + `--slugs`, `--date`, `--gen-failed` 인자.

- [ ] **Step 3: 빈 slugs로 호출 시 stdout 비어 있음 확인**

```bash
.venv/bin/python build_bundles.py --slugs "" --date 2026-05-31
echo "exit=$?"
```

기대 출력. 빈 stdout, `exit=0`.

- [ ] **Step 4: 회귀 테스트 통과 확인**

```bash
.venv/bin/pytest -v
```

기대 출력. 모두 PASS.

- [ ] **Step 5: commit**

```bash
cd /Users/daegong/projects/popory
git add services/brief/build_bundles.py
git commit -m "$(cat <<'EOF'
feat(brief): build_bundles.py 신규 — bundled 카테고리 수신자별 본문 빌더

bundled slug 목록을 받아 카테고리별 fetch_subscribers + 본문 파일 → 수신자 union → 구독한 카테고리만 ## 헤더로 합쳐 /tmp/bundle_<hash>_<date>.md 작성. stdout은 JSONL.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: run_daily.sh 재작성 (멀티 카테고리 + --dry-run)

**Files:**
- Modify: `services/brief/run_daily.sh`

- [ ] **Step 1: run_daily.sh 전체 재작성**

`services/brief/run_daily.sh` 전체 교체. 첫 줄 한국어 헤더 유지.

```bash
#!/bin/bash
# 매일 KST 09:00 launchd가 호출하는 entry script. 활성 카테고리 전부 generate·publish·발송.

set -u  # 미정의 변수 사용 시 즉시 실패. set -e는 안 씀 — 각 단계 결과를 개별 분기.

BRIEF_DIR=/Users/daegong/projects/popory/services/brief
VENV_PY=${BRIEF_DIR}/.venv/bin/python
DATE=$(TZ=Asia/Seoul date +%Y-%m-%d)
LOG_FILE=${BRIEF_DIR}/logs/${DATE}.log

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
fi

mkdir -p "${BRIEF_DIR}/logs"

log() {
  echo "{\"ts\":\"$(TZ=Asia/Seoul date +%Y-%m-%dT%H:%M:%S+09:00)\",\"cli\":\"run_daily\",\"msg\":$1}" >> "${LOG_FILE}"
}

log "\"start dry_run=${DRY_RUN}\""

# 1) secrets 환경변수 source
if [ ! -f "${BRIEF_DIR}/secrets/portal_endpoints.env" ]; then
  log "\"missing portal_endpoints.env\""
  exit 2
fi
set -a
# shellcheck disable=SC1091
source "${BRIEF_DIR}/secrets/portal_endpoints.env"
set +a

# 2) 활성 카테고리 목록 ("slug mode" 한 줄씩)
CATEGORIES=$("${VENV_PY}" -c "from popory_brief import categories
for c in categories.list_categories():
    print(c.slug, c.delivery_mode)" 2>&1)
SCAN_EXIT=$?
if [ ${SCAN_EXIT} -ne 0 ]; then
  log "\"abort: categories scan failed exit=${SCAN_EXIT}\""
  echo "${CATEGORIES}" >> "${LOG_FILE}"
  exit ${SCAN_EXIT}
fi
if [ -z "${CATEGORIES}" ]; then
  log "\"no enabled categories\""
  exit 0
fi
log "\"categories_count=$(echo "${CATEGORIES}" | grep -c .)\""

# 3) 카테고리별 generate + publish
declare -a STANDALONE_SLUGS=()
declare -a BUNDLED_SLUGS=()
GEN_FAIL_SLUGS=""
GEN_OK_COUNT=0

while IFS=' ' read -r SLUG MODE; do
  [ -z "${SLUG}" ] && continue
  GEN_OUT=$("${VENV_PY}" "${BRIEF_DIR}/generate_brief.py" --category "${SLUG}" 2>&1)
  GEN_EXIT=$?
  echo "${GEN_OUT}" >> "${LOG_FILE}"
  if [ ${GEN_EXIT} -ne 0 ]; then
    log "\"generate fail category=${SLUG} exit=${GEN_EXIT}\""
    GEN_FAIL_SLUGS="${GEN_FAIL_SLUGS}${SLUG},"
    continue
  fi
  GEN_OK_COUNT=$((GEN_OK_COUNT + 1))
  log "\"generate ok category=${SLUG}\""
  if [ "${MODE}" = "standalone" ]; then
    STANDALONE_SLUGS+=("${SLUG}")
  elif [ "${MODE}" = "bundled" ]; then
    BUNDLED_SLUGS+=("${SLUG}")
  fi

  # publish (dry-run 시 skip)
  if [ ${DRY_RUN} -eq 0 ]; then
    BODY_FILE=/tmp/brief_${SLUG}_${DATE}.md
    META_FILE=/tmp/brief_${SLUG}_${DATE}.meta.json
    PUB_OUT=$("${VENV_PY}" "${BRIEF_DIR}/publish_to_portal.py" \
      --area "brief-${SLUG}" --meta-file "${META_FILE}" --body-file "${BODY_FILE}" 2>&1)
    PUB_EXIT=$?
    echo "${PUB_OUT}" >> "${LOG_FILE}"
    log "\"publish exit=${PUB_EXIT} category=${SLUG}\""
  else
    log "\"DRY publish category=${SLUG}\""
  fi
done <<< "${CATEGORIES}"

if [ ${GEN_OK_COUNT} -eq 0 ]; then
  log "\"abort: all categories generate failed\""
  exit 5
fi

# 4) standalone 카테고리 발송 (카테고리별 1통씩)
for SLUG in "${STANDALONE_SLUGS[@]}"; do
  CAT_META=$("${VENV_PY}" -c "from popory_brief.categories import load_category
c = load_category('${SLUG}')
print(c.subject('${DATE}'))
print(c.sender())")
  SUBJECT=$(echo "${CAT_META}" | sed -n '1p')
  SENDER_NAME=$(echo "${CAT_META}" | sed -n '2p')
  FROM_ADDR="${SENDER_NAME} <poporyfamily@gmail.com>"

  SUBS_OUT=$("${VENV_PY}" "${BRIEF_DIR}/fetch_subscribers.py" --area "brief-${SLUG}" 2>&1)
  SUBS_EXIT=$?
  echo "${SUBS_OUT}" >> "${LOG_FILE}"
  if [ ${SUBS_EXIT} -ne 0 ]; then
    log "\"fetch_subscribers fail category=${SLUG} exit=${SUBS_EXIT}\""
    continue
  fi
  EMAILS=$(echo "${SUBS_OUT}" | /usr/bin/jq -r '.subscribers[].email' 2>/dev/null)
  if [ -z "${EMAILS}" ]; then
    log "\"no subscribers category=${SLUG}\""
    continue
  fi
  BODY_FILE=/tmp/brief_${SLUG}_${DATE}.md
  while IFS= read -r EMAIL; do
    [ -z "${EMAIL}" ] && continue
    if [ ${DRY_RUN} -eq 1 ]; then
      log "\"DRY standalone to=${EMAIL} category=${SLUG} subject=${SUBJECT}\""
      continue
    fi
    SEND_OUT=$("${VENV_PY}" "${BRIEF_DIR}/send_gmail.py" \
      --to "${EMAIL}" --from "${FROM_ADDR}" \
      --subject "${SUBJECT}" --body-file "${BODY_FILE}" --md 2>&1)
    SEND_EXIT=$?
    if [ ${SEND_EXIT} -eq 0 ]; then
      log "\"sent standalone to=${EMAIL} category=${SLUG}\""
    else
      log "\"send fail to=${EMAIL} category=${SLUG} exit=${SEND_EXIT}\""
      echo "${SEND_OUT}" >> "${LOG_FILE}"
    fi
  done <<< "${EMAILS}"
done

# 5) bundled 카테고리 묶음 발송 (수신자별 1통)
if [ ${#BUNDLED_SLUGS[@]} -gt 0 ]; then
  BUNDLED_SLUGS_CSV=$(IFS=,; echo "${BUNDLED_SLUGS[*]}")
  GEN_FAIL_CSV="${GEN_FAIL_SLUGS%,}"
  BUNDLE_PLAN=$("${VENV_PY}" "${BRIEF_DIR}/build_bundles.py" \
    --slugs "${BUNDLED_SLUGS_CSV}" --date "${DATE}" --gen-failed "${GEN_FAIL_CSV}" 2>>"${LOG_FILE}")
  PLAN_EXIT=$?
  if [ ${PLAN_EXIT} -ne 0 ]; then
    log "\"bundle build fail exit=${PLAN_EXIT}\""
  elif [ -z "${BUNDLE_PLAN}" ]; then
    log "\"no bundled subscribers\""
  else
    SUBJECT="[이슈 브리핑] ${DATE}"
    FROM_ADDR="이슈 브리핑 <poporyfamily@gmail.com>"
    echo "${BUNDLE_PLAN}" | while IFS= read -r LINE; do
      [ -z "${LINE}" ] && continue
      EMAIL=$(echo "${LINE}" | /usr/bin/jq -r '.email')
      BODY_FILE=$(echo "${LINE}" | /usr/bin/jq -r '.body_file')
      if [ ${DRY_RUN} -eq 1 ]; then
        log "\"DRY bundled to=${EMAIL} subject=${SUBJECT}\""
        continue
      fi
      SEND_OUT=$("${VENV_PY}" "${BRIEF_DIR}/send_gmail.py" \
        --to "${EMAIL}" --from "${FROM_ADDR}" \
        --subject "${SUBJECT}" --body-file "${BODY_FILE}" --md 2>&1)
      SEND_EXIT=$?
      if [ ${SEND_EXIT} -eq 0 ]; then
        log "\"sent bundled to=${EMAIL}\""
      else
        log "\"send fail to=${EMAIL} category=__bundle exit=${SEND_EXIT}\""
        echo "${SEND_OUT}" >> "${LOG_FILE}"
      fi
    done
  fi
fi

# 6) 최종 요약 + 임시 파일 정리
log "\"done dry_run=${DRY_RUN} generated_ok=${GEN_OK_COUNT} failed=${GEN_FAIL_CSV:-none}\""
find /tmp -maxdepth 1 -name 'brief_*.md' -mtime +7 -delete 2>/dev/null
find /tmp -maxdepth 1 -name 'brief_*.meta.json' -mtime +7 -delete 2>/dev/null
find /tmp -maxdepth 1 -name 'bundle_*.md' -mtime +7 -delete 2>/dev/null

exit 0
```

- [ ] **Step 2: chmod 확인 (이미 +x이어야 함)**

```bash
ls -l /Users/daegong/projects/popory/services/brief/run_daily.sh
```

기대 출력. `-rwxr-xr-x ...` (실행 권한). 없으면 `chmod +x ...`.

- [ ] **Step 3: dry-run 실행 → 카테고리 스캔·generate(실제)·publish skip·발송 skip 흐름 확인**

```bash
cd /Users/daegong/projects/popory/services/brief
bash run_daily.sh --dry-run
echo "exit=$?"
```

소요 시간. realestate 1개라 ~2분 (claude CLI generate).

기대 출력. `exit=0`. 로그 파일에 다음 키 라인 확인.

```bash
cat /Users/daegong/projects/popory/services/brief/logs/$(TZ=Asia/Seoul date +%Y-%m-%d).log
```

확인 항목.
- `"start dry_run=1"`
- `"categories_count=1"`
- `"generate ok category=realestate"`
- `"DRY publish category=realestate"`
- `"no subscribers category=realestate"` (Task 6 마이그레이션 전이라 brief-realestate area 구독자 0명. DRY standalone 라인은 마이그레이션 후 Task 7에서 확인)
- `"done dry_run=1 generated_ok=1 ..."`

(이 시점에는 publish가 skip되었으므로 portal `/p/brief-realestate/`에 새 항목은 안 들어감. dry-run 본문 파일 `/tmp/brief_realestate_<date>.md`만 생성. 실제 발송 흐름은 Task 7 풀 검증에서 검증.)

- [ ] **Step 4: 회귀 테스트 통과 확인**

```bash
.venv/bin/pytest -v
```

기대 출력. 모두 PASS.

- [ ] **Step 5: commit**

```bash
cd /Users/daegong/projects/popory
git add services/brief/run_daily.sh
git commit -m "$(cat <<'EOF'
feat(brief): run_daily.sh 멀티 카테고리 전환 + --dry-run

categories.list_categories() 스캔으로 활성 카테고리 순회. standalone은 카테고리당 1통, bundled는 build_bundles.py로 수신자별 묶음 1통. publish는 카테고리별 brief-{slug} area. --dry-run은 publish·발송만 skip.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: prod D1 마이그레이션 (1회성)

**Files:** (코드 수정 없음 — wrangler CLI로 직접 실행)

이 task는 Task 1~5 코드가 모두 merge·push된 다음에 실행한다. 마이그레이션 SQL을 prod D1에 적용해 기존 `area='brief'` 데이터를 `area='brief-realestate'`로 옮긴다.

- [ ] **Step 0: 코드 origin 동기화 (마이그레이션 전 push)**

```bash
cd /Users/daegong/projects/popory
git push origin main
```

기대 출력. Task 1~5 commit 5개가 origin/main에 동기화.

- [ ] **Step 1: 영향 row 사전 확인**

```bash
cd /Users/daegong/projects/popory
pnpm --filter @popory/portal exec wrangler d1 execute popory-portal --remote --command \
  "SELECT 'subs' AS table_name, COUNT(*) AS rows FROM area_subscriptions WHERE area='brief'
   UNION ALL
   SELECT 'pub', COUNT(*) FROM published_items WHERE area='brief';"
```

기대 출력. `subs`행 = 1, `pub`행 = 1 (또는 향후 누적 시 그 수). 0이면 이미 마이그레이션 완료 또는 데이터 없음 — 사용자에게 확인 후 진행.

- [ ] **Step 2: UPDATE 실행**

```bash
pnpm --filter @popory/portal exec wrangler d1 execute popory-portal --remote --command \
  "UPDATE area_subscriptions SET area='brief-realestate' WHERE area='brief';
   UPDATE published_items SET area='brief-realestate' WHERE area='brief';"
```

기대 출력. `Executed 2 commands` + `changes` 수가 Step 1 결과와 일치.

- [ ] **Step 3: 마이그레이션 검증**

```bash
pnpm --filter @popory/portal exec wrangler d1 execute popory-portal --remote --command \
  "SELECT 'old_subs' AS t, COUNT(*) AS r FROM area_subscriptions WHERE area='brief'
   UNION ALL SELECT 'old_pub', COUNT(*) FROM published_items WHERE area='brief'
   UNION ALL SELECT 'new_subs', COUNT(*) FROM area_subscriptions WHERE area='brief-realestate'
   UNION ALL SELECT 'new_pub', COUNT(*) FROM published_items WHERE area='brief-realestate';"
```

기대 출력. `old_subs=0, old_pub=0, new_subs=1, new_pub=1`.

- [ ] **Step 4: portal에서 새 URL 응답 확인**

```bash
curl -s "https://api.poporyfamily.com/api/published_items?area=brief-realestate&limit=5" | python3 -m json.tool | head -20
```

기대 출력. items 배열에 기존 publish id(`352089882720495788ccee081f5065a8` — 5/30 부동산)가 area=brief-realestate로 노출.

---

## Task 7: end-to-end 풀 검증

**Files:** (코드 수정 없음 — 검증만)

- [ ] **Step 1: 실제 풀 실행 (publish + 발송 포함)**

```bash
cd /Users/daegong/projects/popory/services/brief
bash run_daily.sh
echo "exit=$?"
```

기대. `exit=0`. 소요 ~2분.

- [ ] **Step 2: log 검사 — 각 단계 ok**

```bash
cat /Users/daegong/projects/popory/services/brief/logs/$(TZ=Asia/Seoul date +%Y-%m-%d).log | grep run_daily
```

기대 라인.
- `"start dry_run=0"`
- `"categories_count=1"`
- `"generate ok category=realestate"`
- `"publish exit=0 category=realestate"`
- `"sent standalone to=poporyfamily@gmail.com category=realestate"`
- `"done dry_run=0 generated_ok=1 ..."`

- [ ] **Step 3: portal 새 항목 노출 확인**

```bash
curl -s "https://api.poporyfamily.com/api/published_items?area=brief-realestate&limit=3" | python3 -m json.tool
```

기대. 가장 최근 항목의 `published_at`이 방금 실행한 시각, title이 "[부동산 이슈 브리핑] {today}".

- [ ] **Step 4: portal page 응답 확인**

```bash
NEW_ID=$(curl -s "https://api.poporyfamily.com/api/published_items?area=brief-realestate&limit=1" | python3 -c "import sys,json; print(json.load(sys.stdin)['items'][0]['id'])")
curl -s -o /dev/null -w "%{http_code}\n" "https://poporyfamily.com/p/brief-realestate/${NEW_ID}"
```

기대 출력. `200`.

- [ ] **Step 5: 메일 수신 확인**

poporyfamily@gmail.com 받은편지함에서 "[부동산 이슈 브리핑] {today}" 메일 1통 도착 확인 (사용자 작업).

- [ ] **Step 6: 완료 보고**

```bash
cd /Users/daegong/projects/popory
git log --oneline -10
```

기대. Task 1~5 commit 5개가 origin/main에 이미 동기화 (Task 6 step 0에서 push 완료). 작업 종료.

---

## 카테고리 신설 운영 가이드 (구현 완료 후 참고)

본 plan을 실행하면 부동산(realestate) 1개 카테고리만 활성화된다. 향후 다른 카테고리(반부패·기업집단·Sanction·공정위 등) 추가 시 절차.

1. `services/brief/categories/{slug}/SKILL.md` 작성 (frontmatter 6필드 + system prompt 본문)
   - `delivery_mode: bundled` 권장 (부동산만 standalone)
   - 예. `services/brief/categories/anticorruption/SKILL.md`
2. (선택) 로컬 검증. `bash run_daily.sh --dry-run`. 새 카테고리 generate가 성공하는지 확인
3. portal D1에 첫 구독자 INSERT (admin SQL). 예.
   ```sql
   INSERT INTO area_subscriptions (sub, area) VALUES ('<user_sub>', 'brief-anticorruption');
   ```
   또는 portal UI를 통해 구독.
4. 다음 09:00 KST 자동 실행에서 첫 발송. 코드 수정·재배포 불필요.

비활성화는 frontmatter `enabled: false` 변경 후 commit. 디렉토리 삭제도 가능하지만 frontmatter 토글이 권장 (이력·복구 용이).
