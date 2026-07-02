# 오늘의 인생 문장 — 유튜브 게시물 자동 생성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매일 auto_create가 뽑는 책 주제에서 한 문장을 추출해 유튜브 커뮤니티 게시물 초안을 자동 생성한다(생성만, 수동 게시).

**Architecture:** 새 platform 타입 `youtube-post`를 기존 콘텐츠 파이프라인(auto_create → content_jobs → worker → portal review)에 추가한다. 영상·R2를 쓰지 않는 텍스트 생성물이라 naver-blog 경로(`generate()` → `_report(draft, meta, "review")`)를 미러링한다. 유튜브 Data API에 커뮤니티 게시물 작성 엔드포인트가 없어 자동 게시는 불가하며, 사용자가 포털 draft를 복사해 수동 게시한다.

**Tech Stack:** Python 3.11(services/content, pytest), TypeScript zod(packages/types, vitest), Next.js(apps/portal). claude CLI + Claude Max.

## Global Constraints

- 신규 소스 파일은 첫 줄에 역할을 설명하는 한국어 한 줄 주석을 넣는다(Python `#`, TS `//`). 마침표로 끝내고 콜론 종결 금지.
- 한국어 문장은 마침표·물음표·느낌표로 끝낸다(콜론 종결 금지).
- 유튜브 콘텐츠에 구독·좋아요·팔로우 유도 문구 금지.
- 게시물 태그명 정확히. `<post_markdown>...</post_markdown>` + `<post_meta>...</post_meta>`.
- 해시태그 정확히. `#오늘의문장 #인생문장 #책추천 #포포리책방`.
- 허위 인용 금지 — 실제 문구 미확인 시 저자 귀속 없이 사색 문장으로 쓰고 `quote_verified=false`.
- 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## 파일 구조

- Create `services/content/popory_content/youtube_post_contract.py` — 두 태그 파서.
- Create `services/content/popory_content/youtube_post_prompt.py` — system/user 프롬프트 빌더.
- Create `services/content/tests/test_youtube_post_contract.py`, `tests/test_youtube_post_prompt.py`.
- Modify `services/content/popory_content/generate.py` — `generate_youtube_post()` 추가.
- Modify `services/content/popory_content/worker.py` — `youtube-post` 분기.
- Modify `services/content/popory_content/auto_create.py` — platforms에 youtube-post 추가.
- Modify `services/content/tests/test_worker.py`, `tests/test_auto_create.py`, `tests/test_generate.py`(없으면 생성).
- Modify `packages/types/src/content_job.ts` — platform enum 3곳에 youtube-post 추가.
- Modify `packages/types/src/content_job.test.ts` — enum 허용 테스트.
- Modify `apps/portal/src/app/(authed)/content/status/StatusPanel.tsx` — 라벨 맵에 게시물 추가.

포털 상세(`content/[id]/page.tsx:189`)는 youtube/shorts/instagram이 아닌 platform을 DraftEditor(텍스트+복사)로 렌더하므로 youtube-post는 자동 표시된다. page.tsx 수정 불필요.

---

### Task 1: 게시물 출력 계약 파서 (youtube_post_contract.py)

**Files:**
- Create: `services/content/popory_content/youtube_post_contract.py`
- Test: `services/content/tests/test_youtube_post_contract.py`

**Interfaces:**
- Consumes: `popory_content.contract.ContractError`
- Produces: `parse_youtube_post(text: str) -> tuple[str, dict[str, Any]]` — 두 태그 추출, post_markdown 문자열·post_meta dict 반환. 태그 없음/빈 본문/JSON 오류 시 `ContractError`.

- [ ] **Step 1: 실패 테스트 작성**

Create `services/content/tests/test_youtube_post_contract.py`:
```python
# 게시물 출력 계약(post_markdown·post_meta) 파서 검증.
import pytest

from popory_content.youtube_post_contract import parse_youtube_post
from popory_content.contract import ContractError


def test_parse_ok():
    text = (
        'intro <post_markdown>"한 문장이다."\n\n— 『책제목』 저자\n\n'
        '오늘도 한 줄에 기대어.\n\n#오늘의문장 #인생문장 #책추천 #포포리책방</post_markdown> '
        '<post_meta>{"quote_verified": true, "book": "책제목", "author": "저자"}</post_meta> tail'
    )
    post, meta = parse_youtube_post(text)
    assert '"한 문장이다."' in post
    assert "#포포리책방" in post
    assert meta["quote_verified"] is True
    assert meta["book"] == "책제목"


def test_missing_tags_raises():
    with pytest.raises(ContractError):
        parse_youtube_post("태그가 없다.")


def test_empty_body_raises():
    with pytest.raises(ContractError):
        parse_youtube_post('<post_markdown>   </post_markdown><post_meta>{}</post_meta>')


def test_bad_meta_json_raises():
    with pytest.raises(ContractError):
        parse_youtube_post('<post_markdown>x</post_markdown><post_meta>{nope}</post_meta>')
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_youtube_post_contract.py -q`
Expected: FAIL (`ModuleNotFoundError: popory_content.youtube_post_contract`).

- [ ] **Step 3: 파서 구현**

Create `services/content/popory_content/youtube_post_contract.py`:
```python
# claude 출력에서 post_markdown·post_meta 두 태그를 추출·파싱하는 게시물 계약.
import json
import re
from typing import Any

from popory_content.contract import ContractError


def parse_youtube_post(text: str) -> tuple[str, dict[str, Any]]:
    body_m = re.search(r"<post_markdown>(.*?)</post_markdown>", text, re.DOTALL)
    meta_m = re.search(r"<post_meta>\s*(\{.*?\})\s*</post_meta>", text, re.DOTALL)
    if not body_m or not meta_m:
        raise ContractError("post_markdown/post_meta 태그를 찾지 못함")
    post = body_m.group(1).strip()
    if not post:
        raise ContractError("post_markdown 이 비어있음")
    try:
        meta = json.loads(meta_m.group(1).strip())
    except json.JSONDecodeError as e:
        raise ContractError(f"post_meta 파싱 실패: {e}") from e
    return post, meta
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_youtube_post_contract.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/youtube_post_contract.py services/content/tests/test_youtube_post_contract.py
git commit -m "feat(content): 게시물 출력 계약 파서(post_markdown·post_meta)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: 게시물 프롬프트 빌더 (youtube_post_prompt.py)

**Files:**
- Create: `services/content/popory_content/youtube_post_prompt.py`
- Test: `services/content/tests/test_youtube_post_prompt.py`

**Interfaces:**
- Produces: `build_youtube_post_system_prompt() -> str`, `build_youtube_post_user_message(topic: str) -> str`.

- [ ] **Step 1: 실패 테스트 작성**

Create `services/content/tests/test_youtube_post_prompt.py`:
```python
# 게시물 프롬프트 빌더가 형식·정확성·태그 규칙을 담는지 검증.
from popory_content.youtube_post_prompt import (
    build_youtube_post_system_prompt,
    build_youtube_post_user_message,
)


def test_system_prompt_has_rules():
    sp = build_youtube_post_system_prompt()
    assert "post_markdown" in sp and "post_meta" in sp
    assert "#오늘의문장 #인생문장 #책추천 #포포리책방" in sp
    assert "quote_verified" in sp
    assert "거짓" in sp  # 허위 인용 금지 규칙


def test_user_message_includes_topic():
    um = build_youtube_post_user_message("미움받을 용기 - 기시미 이치로")
    assert "미움받을 용기" in um
    assert "post_markdown" in um
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_youtube_post_prompt.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: 프롬프트 구현**

Create `services/content/popory_content/youtube_post_prompt.py`:
```python
# claude 에 줄 '오늘의 인생 문장' 유튜브 커뮤니티 게시물 system/user 프롬프트를 조립.

_RULES = """당신은 '포포리 책방' 유튜브 채널의 커뮤니티 게시물을 쓰는 한국어 편집자입니다.
주어진 책 주제에서 '오늘의 인생 문장'을 뽑아 짧은 게시물을 작성합니다.

## 1. 문장 선정
- WebSearch·WebFetch 로 그 책의 실제 문구·핵심 메시지를 확인합니다.
- 실제 인용문이 확인되면 그대로(verbatim) 인용하고 post_meta.quote_verified 를 true 로 둡니다.
- 확인되지 않으면 저자에게 문장을 귀속하지 말고, 책의 주제·메시지에 기반한 사색 문장으로 씁니다(quote_verified=false). 거짓 인용은 절대 만들지 않습니다.

## 2. 게시물 본문(post_markdown) — 아래 순서·형식 그대로
"인용문 또는 사색 문장"

— 『책제목』 저자

공감 한 줄(독자에게 건네는 짧은 말).

#오늘의문장 #인생문장 #책추천 #포포리책방

- verbatim 인용일 때만 `— 『책제목』 저자` 로 저자를 표기합니다. 사색 문장이면 `— 『책제목』` 만 씁니다.

## 3. 문체
- 자연스러운 한국어. 문장은 마침표로 끝냅니다(콜론 종결 금지).
- 간투사(음·어·아·그) 금지. 구독·좋아요·팔로우 유도 문구 금지.

## 4. 출력 (반드시 마지막 응답에 두 태그를 정확히 포함, 태그 안에 코드 블록 표시 금지)
<post_markdown>
(위 형식의 게시물 본문)
</post_markdown>
<post_meta>
{"quote_verified": true, "book": "책제목", "author": "저자 또는 null"}
</post_meta>
"""


def build_youtube_post_system_prompt() -> str:
    return _RULES


def build_youtube_post_user_message(topic: str) -> str:
    return (
        f"책 주제: {topic}\n\n"
        "시스템 규칙에 따라 '오늘의 인생 문장' 커뮤니티 게시물을 작성하세요.\n"
        "마지막 응답에 <post_markdown>...</post_markdown> 과 <post_meta>...</post_meta> 두 태그를 정확히 포함하세요."
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_youtube_post_prompt.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/youtube_post_prompt.py services/content/tests/test_youtube_post_prompt.py
git commit -m "feat(content): 오늘의 인생 문장 게시물 프롬프트 빌더

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 게시물 생성기 (generate_youtube_post)

**Files:**
- Modify: `services/content/popory_content/generate.py`
- Test: `services/content/tests/test_generate.py` (없으면 생성)

**Interfaces:**
- Consumes: Task 1 `parse_youtube_post`, Task 2 `build_youtube_post_system_prompt`/`build_youtube_post_user_message`, 기존 `run_claude_cli`, `GenerateError`, `DEFAULT_MODEL`.
- Produces: `generate_youtube_post(*, topic: str, model: str = DEFAULT_MODEL, job_id: str = "adhoc") -> tuple[str, dict[str, Any]]`.

- [ ] **Step 1: 실패 테스트 작성**

Create/append `services/content/tests/test_generate.py`:
```python
# generate_youtube_post 가 게시물 프롬프트·파서로 run_claude_cli 를 배선하는지 검증.
from popory_content import generate as gen


def test_generate_youtube_post_wires_prompt_and_parser(monkeypatch):
    captured = {}

    def fake_run(*, system_prompt, user_msg, parse, job_id, model):
        captured["system_prompt"] = system_prompt
        captured["user_msg"] = user_msg
        captured["parse"] = parse
        return ("게시물 본문", {"quote_verified": False, "book": "책", "author": None})

    monkeypatch.setattr(gen, "run_claude_cli", fake_run)
    draft, meta = gen.generate_youtube_post(topic="책 - 저자", job_id="j1")
    assert draft == "게시물 본문"
    assert meta["book"] == "책"
    assert captured["parse"] is gen.parse_youtube_post
    assert "책 - 저자" in captured["user_msg"]
    assert "post_markdown" in captured["system_prompt"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_generate.py -q`
Expected: FAIL (`AttributeError: module 'popory_content.generate' has no attribute 'generate_youtube_post'`).

- [ ] **Step 3: 생성기 구현**

In `services/content/popory_content/generate.py`, 상단 import 블록(기존 `from popory_content.prompt import ...` 아래)에 추가:
```python
from popory_content.youtube_post_prompt import build_youtube_post_system_prompt, build_youtube_post_user_message
from popory_content.youtube_post_contract import parse_youtube_post
```

파일 끝(기존 `generate()` 함수 아래)에 추가:
```python
def generate_youtube_post(*, topic: str, model: str = DEFAULT_MODEL,
                          job_id: str = "adhoc") -> tuple[str, dict[str, Any]]:
    sp = build_youtube_post_system_prompt()
    um = build_youtube_post_user_message(topic)
    try:
        return run_claude_cli(system_prompt=sp, user_msg=um, parse=parse_youtube_post, job_id=job_id, model=model)
    except ContractError as e:  # 방어적: run_claude_cli 가 이미 GenerateError 로 감쌈
        raise GenerateError(str(e)) from e
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_generate.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/generate.py services/content/tests/test_generate.py
git commit -m "feat(content): generate_youtube_post — 게시물 프롬프트·파서 배선

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: 워커 youtube-post 분기

**Files:**
- Modify: `services/content/popory_content/worker.py`
- Test: `services/content/tests/test_worker.py`

**Interfaces:**
- Consumes: Task 3 `generate_youtube_post`, 기존 `_report`, `run_once`.
- Produces: platform=="youtube-post"인 잡을 `generate_youtube_post` → `_report(draft, meta, "review")` 처리.

- [ ] **Step 1: 실패 테스트 작성**

In `services/content/tests/test_worker.py`, `test_success_posts_review` 아래에 추가:
```python
def test_youtube_post_branch_reviews(monkeypatch):
    monkeypatch.setattr(
        worker, "generate_youtube_post",
        lambda **kw: ("오늘의 문장 게시물", {"quote_verified": False, "book": "책", "author": None}),
    )
    client = FakeClient({"job": {"id": "p1", "topic": "책 - 저자", "platform": "youtube-post"},
                         "sources": [], "style_samples": []})
    assert worker.run_once(client) is True
    path, body = client.patched[0]
    assert path == "/api/content/jobs/p1/result"
    assert body["status"] == "review"
    assert body["draft"] == "오늘의 문장 게시물"
    assert body["meta"]["book"] == "책"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_worker.py::test_youtube_post_branch_reviews -q`
Expected: FAIL (`AttributeError: ... has no attribute 'generate_youtube_post'` 또는 분기 없어 else 로 빠져 `generate` 호출).

- [ ] **Step 3: 분기 구현**

In `services/content/popory_content/worker.py`, import 수정 — 기존 `from popory_content.generate import generate, GenerateError` 를:
```python
from popory_content.generate import generate, GenerateError, generate_youtube_post
```

`elif platform == "instagram-image":` 블록과 `else:` 블록 사이에 추가:
```python
        elif platform == "youtube-post":
            draft, meta = generate_youtube_post(topic=job["topic"], job_id=job_id)
            _report(client, job_id, {"status": "review", "draft": draft, "meta": meta}, "review")
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_worker.py -q`
Expected: PASS (기존 + 신규 통과).

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/worker.py services/content/tests/test_worker.py
git commit -m "feat(content): 워커 youtube-post 분기 — 게시물 생성 후 review 회신

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: types platform enum 확장 (youtube-post)

**Files:**
- Modify: `packages/types/src/content_job.ts:20,31,60`
- Test: `packages/types/src/content_job.test.ts`

**Interfaces:**
- Produces: `TopicPlatformSchema`·`JobServiceCreateSchema`·`ContentJobCreateSchema` 가 platform `"youtube-post"` 를 허용.

- [ ] **Step 1: 실패 테스트 작성**

In `packages/types/src/content_job.test.ts`, import 에 `TopicPlatformSchema` 추가하고(없으면 `import { ..., TopicPlatformSchema } from "./content_job";`) 새 describe 추가:
```typescript
describe("youtube-post platform", () => {
  it("TopicPlatformSchema가 youtube-post 허용", () => {
    expect(TopicPlatformSchema.safeParse({ platform: "youtube-post" }).success).toBe(true);
  });
  it("JobServiceCreateSchema가 youtube-post 허용", () => {
    expect(JobServiceCreateSchema.safeParse({ owner_sub: "u", topic: "t", platform: "youtube-post" }).success).toBe(true);
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd packages/types && pnpm test`
Expected: FAIL (youtube-post 미허용으로 safeParse.success=false).

- [ ] **Step 3: enum 3곳 수정**

`packages/types/src/content_job.ts`:
- line 20: `platform: z.enum(["naver-blog", "youtube", "shorts", "instagram-image", "youtube-post"]).default("naver-blog"),`
- line 31: `platform: z.enum(["youtube", "shorts", "naver-blog", "youtube-post"]),`
- line 60: `platform: z.enum(["naver-blog", "youtube", "shorts", "instagram-image", "youtube-post"]),`

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd packages/types && pnpm test`
Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add packages/types/src/content_job.ts packages/types/src/content_job.test.ts
git commit -m "feat(types): platform enum 에 youtube-post 추가

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: auto_create 에 youtube-post 플랫폼 추가

**Files:**
- Modify: `services/content/popory_content/auto_create.py:52`
- Test: `services/content/tests/test_auto_create.py:24`

**Interfaces:**
- Consumes: Task 5(API가 youtube-post platform 수용).
- Produces: 매일 topics/service-create 에 `youtube-post` 포함 4개 플랫폼 큐잉.

- [ ] **Step 1: 테스트 기대값 갱신(실패 유도)**

`services/content/tests/test_auto_create.py` line 24 를:
```python
    assert plats == ["naver-blog", "shorts", "youtube", "youtube-post"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_auto_create.py::test_run_creates_one_grouped_topic -q`
Expected: FAIL (현재 3개 플랫폼이라 불일치).

- [ ] **Step 3: platforms 수정**

`services/content/popory_content/auto_create.py` 의 platforms 라인을:
```python
            "platforms": [{"platform": "naver-blog"}, {"platform": "youtube"}, {"platform": "shorts"}, {"platform": "youtube-post"}],
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_auto_create.py -q`
Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/auto_create.py services/content/tests/test_auto_create.py
git commit -m "feat(content): auto_create 에 youtube-post 게시물 잡 추가(4번째 플랫폼)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: 포털 게시물 라벨

**Files:**
- Modify: `apps/portal/src/app/(authed)/content/status/StatusPanel.tsx:14`

**Interfaces:**
- Produces: 상태 패널·목록에서 youtube-post 를 "게시물" 로 표기. 상세는 기존 DraftEditor fallback 이 자동 처리.

- [ ] **Step 1: 라벨 맵 수정**

`apps/portal/src/app/(authed)/content/status/StatusPanel.tsx` 의 라벨 객체(line 14)에 항목 추가:
```typescript
  "naver-blog": "블로그", youtube: "유튜브", shorts: "쇼츠", "instagram-image": "인스타", "youtube-post": "게시물",
```

- [ ] **Step 2: 타입체크·빌드 확인**

Run: `cd apps/portal && pnpm typecheck 2>/dev/null || npx tsc --noEmit`
Expected: 에러 없음(신규 문자열 리터럴 추가라 타입 영향 없음).

- [ ] **Step 3: 커밋**

```bash
git add apps/portal/src/app/\(authed\)/content/status/StatusPanel.tsx
git commit -m "feat(portal): 상태 패널에 게시물(youtube-post) 라벨 추가

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## 통합 검증 (수동 스모크)

전체 배포 후 1회 확인. 코드는 워커 재시작으로 반영, API·포털은 배포 필요.

- [ ] 전체 테스트. `cd services/content && .venv/bin/python -m pytest -q` + `cd packages/types && pnpm test`.
- [ ] API·포털 prod 배포(기존 배포 워크플로). worker 재시작(`launchctl kickstart -k gui/$(id -u)/com.popory.content-worker`).
- [ ] 단일 topic 스모크. 서비스 키로 `topics/service-create` 에 platforms=[{"platform":"youtube-post"}] 로 1건 큐잉 → worker 생성 → 포털 `/content/<jobId>` 에서 게시물 draft(문장+출처+한줄+해시태그) + 복사 버튼 확인.
- [ ] 다음 18:00 auto_create 자연 검증 — 그날 책 주제로 youtube-post 잡이 review 에 뜨는지 확인.

## 범위 밖 (YAGNI)

- 유튜브 커뮤니티 자동 게시(공식 API 부재 — 수동 게시).
- 포털 "콘텐츠 만들기" 폼에 youtube-post 체크박스(auto_create 루틴만 사용).
- youtube-post 재생성 엔드포인트(naver-blog 도 미지원).
- 게시물 이미지·게시 이력 추적.
