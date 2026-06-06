# 컨텐츠 관리 리치 HTML (이미지·영상 임베드) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 컨텐츠 생성물을 플레인 마크다운에서 이미지·YouTube 임베드를 포함한 리치 HTML로 바꾸고, 상세 페이지에서 샌드박스 iframe으로 미리본다.

**Architecture:** 기존 파이프라인(claim→generate→result→review→편집) 유지. 바뀌는 것은 ① 워커 생성 프롬프트(HTML+이미지+영상) ② 출력 계약 태그(`<draft_html>`) ③ 초안 R2 contentType(text/html) ④ 포털 상세 렌더링(샌드박스 iframe 미리보기 + HTML 소스 편집).

**Tech Stack:** Python(prompt/contract, pytest), TypeScript(Hono Worker · Next.js 포털), claude CLI.

**전제:** Slice 1(A·B·C)이 prod 가동 중. 스펙 `docs/superpowers/specs/2026-06-06-content-studio-rich-html-design.md`.

---

## File Structure

| 파일 | 변경 | 책임 |
|------|------|------|
| `services/content/popory_content/prompt.py` | 수정 | HTML+이미지+영상 생성 규칙 |
| `services/content/tests/test_prompt.py` | 수정 | 규칙 단언 갱신 |
| `services/content/popory_content/contract.py` | 수정 | `<draft_html>` 추출 |
| `services/content/tests/test_contract.py` | 수정 | 태그·meta 단언 갱신 |
| `workers/api/src/routes/content_jobs.ts` | 수정 | 초안 R2 contentType text/html (2곳) |
| `apps/portal/src/app/(authed)/content/[id]/DraftEditor.tsx` | 수정 | 샌드박스 iframe 미리보기 + HTML 소스 편집 |

`generate.py`·워커·API 스키마는 변경 없음(draft는 문자열, contract가 태그 추출).

---

## Task 1: prompt.py — 리치 HTML 생성 규칙

**Files:**
- Modify: `services/content/popory_content/prompt.py`
- Modify: `services/content/tests/test_prompt.py`

- [ ] **Step 1: 테스트 갱신 (실패 유도)**

`services/content/tests/test_prompt.py` 전체를 아래로 교체:

```python
# system prompt 가 HTML·이미지·영상·출처 규칙과 스타일 샘플을 담는지, user message 가 주제·출처를 담는지 검증.
from popory_content.prompt import build_system_prompt, build_user_message


def test_system_prompt_embeds_samples_and_rules():
    sp = build_system_prompt(["내 글 샘플 본문입니다."])
    assert "내 글 샘플 본문입니다." in sp
    assert "figure" in sp            # 이미지 임베드 규칙
    assert "youtube" in sp.lower()   # 영상 임베드 규칙
    assert "출처" in sp              # 출처 표기
    assert "저작권" in sp
    assert "draft_html" in sp        # 출력 계약
    assert "meta_json" in sp


def test_system_prompt_without_samples():
    sp = build_system_prompt([])
    assert "draft_html" in sp


def test_user_message_has_topic_and_sources():
    um = build_user_message("전세사기 예방", [{"url": "https://law.go.kr/x", "note": "근거"}])
    assert "전세사기 예방" in um
    assert "https://law.go.kr/x" in um
    assert "draft_html" in um
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_prompt.py -q`
Expected: FAIL (현재 prompt는 `draft_markdown`·`figure` 없음).

- [ ] **Step 3: prompt.py 교체**

`services/content/popory_content/prompt.py` 전체를 아래로 교체:

```python
# claude CLI 에 줄 system prompt(리치 HTML 작성 규칙 + 스타일) 와 user message(주제 + 출처) 를 조립.
from typing import Any

_BASE_RULES = """당신은 블로그용 리치 HTML 글을 쓰는 한국어 작성자입니다. 아래 절차와 규칙을 지키세요.

## 1. 리서치
- WebSearch·WebFetch 로 주제 관련 공신력 있는 자료(정부·기관·통계·신뢰 언론)를 우선 수집합니다.
- 사용자가 제공한 참고 링크가 있으면 반드시 검토해 반영합니다.
- 본문에 넣을 관련 이미지(절대 URL)와 관련 YouTube 영상을 함께 찾습니다.
- 근거가 부족하면 추측으로 채우지 말고, 확인된 사실만 씁니다.

## 2. 작성 (리치 HTML)
- 시맨틱 HTML 조각으로 작성합니다. <h2>·<h3>·<p>·<ul>/<li>·<blockquote>·<table> 를 적절히 씁니다.
- <html>·<body> 래퍼, <script>, <style> 는 쓰지 않습니다. 본문 조각만 출력합니다.
- 자연스러운 한국어. 문장은 마침표로 끝냅니다.

## 3. 이미지 (리서치로 찾은 웹 이미지 임베드)
- 본문 흐름에 어울리는 이미지를 2~4장 배치합니다.
- 형식. <figure><img src="이미지 절대URL" alt="설명"><figcaption>출처: 매체명 (<a href="원문URL">링크</a>)</figcaption></figure>
- 출처 표기는 필수입니다. 출처를 모르는 이미지는 넣지 않습니다.

## 4. 영상 (관련 YouTube)
- 주제와 관련된 YouTube 1~2개를 임베드합니다.
- 형식. <div class="video"><iframe src="https://www.youtube-nocookie.com/embed/영상ID" title="제목" frameborder="0" allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>
- 실제로 존재하는 영상만 임베드합니다.

## 5. SEO·저작권
- 핵심 키워드를 제목(<h2>)과 첫 문단에 자연스럽게 배치합니다.
- 원문을 그대로 길게 베끼지 않습니다. 자신의 말로 바꿔 씁니다(패러프레이즈).
- 사실·수치·인용·이미지·영상에는 출처를 표기합니다.

## 6. 출력 (반드시 마지막 응답에 두 태그를 정확히 포함)
- 태그 안에는 코드 블록 표시(```)를 쓰지 말고 내용만 넣습니다.
<draft_html>
(완성된 리치 HTML 본문 조각)
</draft_html>
<meta_json>
{"title": "...", "tags": ["..."], "sources": ["URL", ...], "images": [{"url": "...", "source": "..."}], "videos": [{"url": "...", "title": "..."}], "seo": {"score": 0-100, "notes": "..."}, "copyright": {"ok": true/false, "notes": "..."}}
</meta_json>
"""

_STYLE_HEADER = "\n## 7. 사용자 글 스타일 (아래 샘플의 어조·문장 길이·표현을 따르세요)\n"


def build_system_prompt(style_samples: list[str]) -> str:
    sp = _BASE_RULES
    if style_samples:
        sp += _STYLE_HEADER
        for i, s in enumerate(style_samples, 1):
            sp += f"\n--- 샘플 {i} ---\n{s.strip()}\n"
    return sp


def build_user_message(topic: str, sources: list[dict[str, Any]]) -> str:
    lines = [f"주제: {topic}", "", "시스템 규칙의 절차를 따라 리치 HTML 블로그 글을 작성하세요."]
    refs = [s for s in sources if s.get("url")]
    if refs:
        lines.append("")
        lines.append("참고 링크:")
        for s in refs:
            note = f" — {s['note']}" if s.get("note") else ""
            lines.append(f"- {s['url']}{note}")
    lines.append("")
    lines.append("마지막 응답에 <draft_html>...</draft_html> 과 <meta_json>...</meta_json> 두 태그를 정확히 포함하세요.")
    return "\n".join(lines)
```

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_prompt.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/prompt.py services/content/tests/test_prompt.py
git commit -m "feat(content-worker): 리치 HTML+이미지+영상 생성 프롬프트"
```

---

## Task 2: contract.py — `<draft_html>` 추출

**Files:**
- Modify: `services/content/popory_content/contract.py`
- Modify: `services/content/tests/test_contract.py`

- [ ] **Step 1: 테스트 갱신 (실패 유도)**

`services/content/tests/test_contract.py` 전체를 아래로 교체:

```python
# claude 출력에서 draft_html·meta_json 추출을 검증.
import pytest
from popory_content.contract import parse_generation, ContractError


def test_parses_draft_and_meta():
    text = """헤더 잡담
<draft_html>
<h2>전세사기 예방</h2>
<p>본문입니다.</p>
<figure><img src="https://x/i.jpg" alt="a"><figcaption>출처: 매체</figcaption></figure>
</draft_html>
<meta_json>
{"title": "전세사기 예방", "tags": ["전세"], "images": [{"url": "https://x/i.jpg", "source": "매체"}], "videos": [], "seo": {"score": 82}, "copyright": {"ok": true}}
</meta_json>
끝말"""
    draft, meta = parse_generation(text)
    assert "<h2>" in draft
    assert "figure" in draft
    assert meta["title"] == "전세사기 예방"
    assert meta["images"][0]["source"] == "매체"
    assert meta["seo"]["score"] == 82


def test_missing_tags_raises():
    with pytest.raises(ContractError):
        parse_generation("draft 없음")


def test_bad_json_raises():
    text = "<draft_html>x</draft_html><meta_json>{not json}</meta_json>"
    with pytest.raises(ContractError):
        parse_generation(text)
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_contract.py -q`
Expected: FAIL (현재 contract는 `<draft_markdown>`만 추출 → draft_html 텍스트에서 태그 못 찾아 ContractError, 첫 테스트 실패).

- [ ] **Step 3: contract.py 수정**

`services/content/popory_content/contract.py`의 `parse_generation` 안 정규식 한 줄을 변경. 변경 전:
```python
    body_m = re.search(r"<draft_markdown>(.*?)</draft_markdown>", text, re.DOTALL)
```
변경 후:
```python
    body_m = re.search(r"<draft_html>(.*?)</draft_html>", text, re.DOTALL)
```
그리고 태그 누락 에러 메시지를 변경. 변경 전:
```python
        raise ContractError("draft_markdown/meta_json 태그를 찾지 못함")
```
변경 후:
```python
        raise ContractError("draft_html/meta_json 태그를 찾지 못함")
```
(나머지 — meta_json 정규식·JSON 파싱·반환 — 그대로.)

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_contract.py -q`
Expected: 3 passed.

- [ ] **Step 5: 전체 워커 회귀**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest -q`
Expected: contract(3) + prompt(3) + worker(4) = 10 passed.

- [ ] **Step 6: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/contract.py services/content/tests/test_contract.py
git commit -m "feat(content-worker): 출력 계약 draft_html 로 전환"
```

---

## Task 3: Worker API — 초안 R2 contentType text/html

**Files:**
- Modify: `workers/api/src/routes/content_jobs.ts`

- [ ] **Step 1: 두 R2 put 의 contentType 변경**

`workers/api/src/routes/content_jobs.ts` 에서 `text/markdown; charset=utf-8` 문자열은 정확히 2곳(사용자 PATCH 핸들러, 워커 result 핸들러)에 있다. 둘 다 `text/html; charset=utf-8` 로 바꾼다.

변경 전(2곳 동일):
```ts
      await c.env.R2.put(draftKey, parsed.data.draft, { httpMetadata: { contentType: "text/markdown; charset=utf-8" } });
```
변경 후(2곳 동일):
```ts
      await c.env.R2.put(draftKey, parsed.data.draft, { httpMetadata: { contentType: "text/html; charset=utf-8" } });
```

(사용자 PATCH 쪽은 `parsed.data.draft`, result 쪽도 `parsed.data.draft` 로 동일 문자열 패턴이다. 두 군데 모두 교체.)

- [ ] **Step 2: 라우트 회귀 + 타입체크**

Run: `cd /Users/daegong/projects/popory && pnpm --filter @popory/api test -- --run content_jobs 2>&1 | tail -4`
Expected: 18 passed (contentType 변경은 본문 round-trip 테스트에 영향 없음).

Run: `pnpm --filter @popory/api typecheck 2>&1 | tail -3`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
cd /Users/daegong/projects/popory
git add workers/api/src/routes/content_jobs.ts
git commit -m "feat(content): 초안 R2 contentType 을 text/html 로"
```

---

## Task 4: 포털 상세 — 샌드박스 미리보기 + HTML 소스 편집

**Files:**
- Modify: `apps/portal/src/app/(authed)/content/[id]/DraftEditor.tsx`

- [ ] **Step 1: DraftEditor.tsx 전체 교체**

`apps/portal/src/app/(authed)/content/[id]/DraftEditor.tsx` 전체를 아래로 교체:

```tsx
"use client";
// 초안 미리보기(샌드박스 iframe)·HTML 소스 편집 client — PATCH /api/content/jobs/:id.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

interface Props {
  jobId: string;
  initialDraft: string;
  done: boolean;
  seo: unknown;
  copyright: unknown;
  sources: Array<{ id: string; url: string | null; title: string | null; note: string | null }>;
}

export function DraftEditor({ jobId, initialDraft, done, seo, copyright, sources }: Props) {
  const router = useRouter();
  const [draft, setDraft] = useState(initialDraft);
  const [showSource, setShowSource] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function patch(body: Record<string, unknown>) {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}`, {
        method: "PATCH",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        setMsg(`저장 실패 ${res.status}`);
        return;
      }
      setMsg("저장됨");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  function copy() {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(draft).then(() => setMsg("복사됨")).catch(() => setMsg("복사 실패"));
    } else {
      setMsg("복사 미지원 환경");
    }
  }

  return (
    <div className="mt-8 space-y-6">
      {(seo != null || copyright != null) && (
        <div className="flex flex-wrap gap-2 text-xs">
          {seo != null && <span className="rounded-full border border-popory-border px-2 py-0.5 text-popory-muted">SEO: {JSON.stringify(seo)}</span>}
          {copyright != null && <span className="rounded-full border border-popory-border px-2 py-0.5 text-popory-muted">저작권: {JSON.stringify(copyright)}</span>}
        </div>
      )}

      <div>
        <span className="mb-1 block text-xs font-semibold text-popory-muted">미리보기</span>
        <iframe
          title="콘텐츠 미리보기"
          srcDoc={draft}
          sandbox="allow-scripts allow-popups"
          className="h-[70vh] w-full rounded-md border border-popory-border bg-white"
        />
      </div>

      <div>
        <button type="button" onClick={() => setShowSource((s) => !s)} className="text-xs text-popory-accent">
          {showSource ? "HTML 소스 숨기기" : "HTML 소스 편집"}
        </button>
        {showSource && (
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={20}
            className="mt-2 w-full rounded-md border border-popory-border bg-popory-card p-3 font-mono text-xs leading-relaxed text-popory-fg"
          />
        )}
      </div>

      {sources.length > 0 && (
        <div>
          <span className="mb-1 block text-xs font-semibold text-popory-muted">출처</span>
          <ul className="space-y-1 text-xs text-popory-muted">
            {sources.map((s) => (
              <li key={s.id}>
                {s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-popory-accent">{s.title || s.url}</a> : (s.title || s.note)}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-xs text-popory-muted">네이버 블로그는 HTML 붙여넣기가 제한적입니다. 복사한 HTML은 일부 수동 조정이 필요할 수 있습니다.</p>

      <div className="flex items-center gap-3">
        <button onClick={() => patch({ draft })} disabled={busy} className="rounded-md border border-popory-border px-4 py-2 text-sm disabled:opacity-50">초안 저장</button>
        <button onClick={copy} type="button" className="rounded-md border border-popory-border px-4 py-2 text-sm">HTML 복사</button>
        {!done && (
          <button onClick={() => patch({ draft, status: "done" })} disabled={busy} className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">완료 표시</button>
        )}
        {done && <span className="text-sm text-popory-muted">완료됨</span>}
        {msg && <span className="text-xs text-popory-muted">{msg}</span>}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 타입체크 + 빌드**

Run: `cd /Users/daegong/projects/popory && pnpm --filter @popory/portal typecheck 2>&1 | tail -3`
Expected: clean.

Run: `NEXT_PUBLIC_API_BASE=https://api.poporyfamily.com pnpm --filter @popory/portal build:cf 2>&1 | grep -E "Build completed|error|Error"`
Expected: `Build completed successfully.`

- [ ] **Step 3: Commit**

```bash
cd /Users/daegong/projects/popory
git add "apps/portal/src/app/(authed)/content/[id]/DraftEditor.tsx"
git commit -m "feat(portal): 초안 샌드박스 미리보기 + HTML 소스 편집"
```

---

## Task 5: 검증 + 배포

**Files:** 없음 (검증·운영)

- [ ] **Step 1: 전체 회귀**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest -q` → 10 passed.
Run: `cd /Users/daegong/projects/popory && pnpm --filter @popory/api test -- --run 2>&1 | grep "Tests"` → all pass.
Run: `pnpm -r typecheck 2>&1 | grep -E "Done|error"` → 6 Done.

- [ ] **Step 2: prod 배포 (사용자 확인 후)**

Worker 배포(R2 contentType 변경 반영):
```bash
cd /Users/daegong/projects/popory/workers/api
pnpm exec wrangler deploy --env prod --config ../../infra/wrangler/api.toml
```
포털 배포(미리보기 UI):
```bash
NEXT_PUBLIC_API_BASE=https://api.poporyfamily.com pnpm --filter @popory/portal build:cf
cd workers/api && pnpm exec wrangler pages deploy /Users/daegong/projects/popory/apps/portal/.vercel/output/static --project-name popory-portal --branch main
```

- [ ] **Step 3: 워커 재시작 (새 prompt/contract 로드)**

워커는 launchd 상주 + editable install이라 prompt.py·contract.py 변경 후 재시작해야 반영된다.
```bash
launchctl kickstart -k "gui/$(id -u)/com.popory.content-worker"
```
확인: `launchctl list | grep content-worker` (PID 존재).

- [ ] **Step 4: e2e (휴먼)**

포털에서 새 작업 생성 → 워커 생성(~3~5분) → review → 상세 페이지에서 이미지·YouTube가 포함된 리치 미리보기 확인.

---

## Self-Review (작성자 체크)

**Spec coverage:**
- §5.1 HTML+이미지+영상 프롬프트 → Task 1. ✅
- §5.2 `<draft_html>` 계약 → Task 2. ✅
- §5.3 generate 변경 없음 → 명시(파일구조). ✅
- §5.4 R2 contentType text/html → Task 3. ✅
- §5.5 샌드박스 미리보기 + 소스 편집 → Task 4. ✅
- §8 테스트(contract·prompt·api·portal build) → Task 1·2·3·4·5. ✅

**Placeholder scan:** 모든 코드 단계 실제 코드. "TBD" 없음. Task 3의 "2곳"은 동일 문자열 교체로 구체적. ✅

**Type consistency:** `parse_generation`·`build_system_prompt`·`build_user_message` 시그니처 불변. `DraftEditor` props(jobId·initialDraft·done·seo·copyright·sources) 불변 — 상세 page.tsx 호출부와 일치. PATCH 바디(`draft`·`status:"done"`) `ContentJobEditSchema`와 일치. R2 키·문자열 패턴 일치. ✅
