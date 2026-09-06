# 블로그·유튜브 게시글의 SEO·AEO·GEO 검토 — 생성 직후 claude CLI 로 한 번 점검·교정한다.
#
# 세 축:
# - SEO  검색엔진. 키워드 배치(제목·h2·첫 문단), 질문형 소제목, alt, 내부 구조, 제목 길이, 태그.
# - AEO  답변엔진(네이버 AI 브리핑·구글 AI 오버뷰). 첫 문단의 직접 답, FAQ 섹션, 답이 자립하는지.
# - GEO  생성형 엔진(ChatGPT·Perplexity 인용). 문장 안 출처, 수치·개체의 정확성, 인용 가능한 완결 문장, 정의문.
#
# 설계 원칙:
# - **fail-open.** 검토기가 죽어도 원고는 그대로 review 로 간다. 결과에 status="unavailable" 을 남겨
#   "검토했고 통과"와 구분한다(image_review·script_review 와 같은 원칙).
# - 교정본(revised)은 **검증을 통과할 때만** 채택한다 — 길이가 원문의 70% 아래로 줄거나 script/style 이
#   섞이면 버린다. 검토기가 글을 망가뜨리는 것보다 원문이 낫다.
# - 점수는 meta 에 남겨 포털 검수 화면에서 볼 수 있게 한다.
import json
import os
import re
from typing import Any

from popory_content.generate import run_claude_cli, model_for, GenerateError
from popory_content.seo_title import strip_prefix

ENABLED = os.environ.get("POPORY_SEO_REVIEW", "1") != "0"
TIMEOUT_SECONDS = int(os.environ.get("POPORY_SEO_REVIEW_TIMEOUT", "600"))
MAX_ATTEMPTS = int(os.environ.get("POPORY_SEO_REVIEW_ATTEMPTS", "2"))
MODEL_ENV = os.environ.get("POPORY_SEO_REVIEW_MODEL")
# 교정본 채택 하한 — 이보다 짧아지면 검토기가 본문을 잘라먹은 것으로 보고 원문을 유지한다.
MIN_REVISED_RATIO = 0.7
AXES = ("seo", "aeo", "geo")

_CHECKLIST = """검토 기준 — 축마다 0~100 점과 문제 목록을 냅니다.
[SEO]
- 제목이 **책 제목·저자 같은 핵심 검색어로 시작**하는가. `[책 리뷰]`·`[서평]` 말머리, 날짜, 순번으로 시작하면 감점이고 revised_title 로 고친다 — 검색 봇은 제목 첫 15자에 가장 높은 가중치를 준다. 형식은 `{저자} {책제목} 핵심 요약 및 서평: {핵심 메시지}` 이며 롱테일어(핵심 요약·서평·줄거리·책 추천) 1~2개가 앞부분에 있는가. 60자 이내이고 클릭 유인이 있는가.
- 핵심 키워드가 첫 문단(도입 3줄 이내)·관련 소제목·결론부에 각 1회, 글 전체 4~6회 들어갔는가. 키워드 과잉(스터핑)은 감점.
- **소제목(<h2>/<h3>)이 본문 600~800자마다 있어 글 전체 5~8개인가.** 굵은 <p> 로 소제목을 대신했으면 <h3> 로 바꾼다. 소제목 중 독자가 검색창에 칠 질문형 문장이 있는가.
- 모든 <img> 에 핵심 검색어가 든 서술형 alt 와 사진 설명(figcaption)이 있는가. "이미지"·"사진" 같은 빈 설명은 감점이고 채운다. 태그가 주제·책·저자·핵심 개념을 5~10개로 덮는가.
[AEO]
- 첫 문단이 글의 핵심 질문에 2~3문장으로 **직접 답**하는가(배경 설명으로 시작하면 감점).
- <h2>자주 묻는 질문</h2> 아래 <h3>질문</h3><p>답</p> 3개가 있고 각 답이 그 자체로 완결되는가.
- 소제목 아래 첫 문장이 그 소제목의 답인가(발췌돼도 뜻이 통하는가).
[GEO]
- 수치·연도·인명·인용에 문장 안 출처(매체·기관·책)가 붙어 있는가. 출처 없는 단정은 감점.
- 책 제목·저자·출판사 등 개체가 정식 명칭·국내 출판 표기로 정확한가(예: 보도 섀퍼, 모건 하우절).
- 단락마다 인용해 갈 만한 완결된 한 문장 요약이 있는가. 핵심 개념에 "X란 …이다" 정의문이 있는가.
- 사실 오류·근거 없는 통계가 있으면 GEO 최대 감점 사유이며 revised 에서 삭제하거나 완화합니다."""

BLOG_SYSTEM_PROMPT = f"""당신은 한국어 블로그 글의 SEO·AEO·GEO 검토·교정자입니다. 주어진 HTML 본문과 메타를 검토하고, 고칠 것이 있으면 **같은 HTML 조각 형식**으로 교정본을 냅니다.

{_CHECKLIST}

교정 규칙:
- 시맨틱 HTML 조각만(<h2><h3><p><ul><blockquote><table><figure>). <html>·<body>·<script>·<style> 금지.
- 글의 어조·문장 길이·구성은 유지합니다. 빠진 구조(직접 답 첫 문단·FAQ·alt·정의문·출처 문구)를 **보태는** 교정이 우선이고, 본문을 줄이거나 다시 쓰지 않습니다.
- 출처를 모르는 사실은 지어내지 말고 문장을 완화하거나 삭제합니다. 이미지·영상 임베드는 그대로 둡니다.
- 고칠 게 없으면 <revised_html> 태그를 비워 둡니다.

출력은 마지막 응답에 두 태그(태그 안에 코드블록 표시 금지):
<seo_review>
{{"seo": {{"score": 0, "issues": ["..."]}}, "aeo": {{"score": 0, "issues": ["..."]}}, "geo": {{"score": 0, "issues": ["..."]}}, "revised_title": "고친 제목 또는 null", "revised_tags": ["..."] 또는 null, "summary": "한 줄 총평"}}
</seo_review>
<revised_html>
(교정본 전체 HTML 조각. 고칠 게 없으면 비움)
</revised_html>
"""

POST_SYSTEM_PROMPT = f"""당신은 유튜브 커뮤니티 게시글의 SEO·AEO·GEO 검토·교정자입니다. 짧은 게시글이므로 기준을 게시글 규모로 적용합니다.

{_CHECKLIST}
게시글 특화:
- 책 제목·저자가 정식 표기로 들어갔는가(검색·추천 노출의 핵심). 해시태그가 4~6개로 주제·책·채널을 덮는가.
- 첫 줄(인용문 또는 사색 문장)이 그 자체로 인용 가능한 완결 문장인가. 확인되지 않은 문장을 저자에게 귀속하지 않았는가.
- 원래 형식(인용문 → `— 『책제목』 저자` → 공감 한 줄 → 해시태그)을 그대로 유지합니다. 구독·좋아요 유도 문구는 넣지 않습니다.

출력은 마지막 응답에 두 태그(태그 안에 코드블록 표시 금지):
<seo_review>
{{"seo": {{"score": 0, "issues": ["..."]}}, "aeo": {{"score": 0, "issues": ["..."]}}, "geo": {{"score": 0, "issues": ["..."]}}, "revised_title": null, "revised_tags": null, "summary": "한 줄 총평"}}
</seo_review>
<revised_post>
(교정본 전체. 고칠 게 없으면 비움)
</revised_post>
"""

_REVIEW_TAG = re.compile(r"<seo_review>\s*(\{.*?\})\s*</seo_review>", re.S)
_HTML_TAG = re.compile(r"<revised_html>(.*?)</revised_html>", re.S)
_POST_TAG = re.compile(r"<revised_post>(.*?)</revised_post>", re.S)
_FORBIDDEN = re.compile(r"<\s*(script|style|html|body)\b", re.I)


def _axis(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"score": None, "issues": []}
    try:
        score = int(raw.get("score"))
        score = max(0, min(100, score))
    except (TypeError, ValueError):
        score = None
    issues = raw.get("issues")
    issues = [str(x)[:200] for x in issues][:10] if isinstance(issues, list) else []
    return {"score": score, "issues": issues}


def _parse(revised_tag: re.Pattern):
    def parse(stdout: str) -> dict[str, Any]:
        m = _REVIEW_TAG.search(stdout)
        if not m:
            raise ValueError("seo_review 태그 없음")
        data = json.loads(m.group(1))
        out: dict[str, Any] = {axis: _axis(data.get(axis)) for axis in AXES}
        scores = [out[a]["score"] for a in AXES if out[a]["score"] is not None]
        out["overall"] = round(sum(scores) / len(scores)) if scores else None
        out["summary"] = str(data.get("summary") or "")[:300]
        title = data.get("revised_title")
        # 검토기가 고친 제목에도 말머리가 붙어 올 수 있다 — 같은 길목에서 걷어낸다.
        out["revised_title"] = strip_prefix(str(title)) if isinstance(title, str) and title.strip() else None
        tags = data.get("revised_tags")
        out["revised_tags"] = [str(t).strip() for t in tags if str(t).strip()][:15] if isinstance(tags, list) and tags else None
        rm = revised_tag.search(stdout)
        out["revised_body"] = rm.group(1).strip() if rm else ""
        return out
    return parse


def accept_revision(original: str, revised: str, *, html: bool) -> bool:
    """교정본을 채택해도 되는지. 비었거나, 너무 짧아졌거나, HTML 에 금지 태그가 섞이면 거부."""
    if not revised:
        return False
    if len(revised) < len(original) * MIN_REVISED_RATIO:
        return False
    if html and _FORBIDDEN.search(revised):
        return False
    return True


def _run(system_prompt: str, user_msg: str, revised_tag: re.Pattern, *, job_id: str,
         runner) -> dict[str, Any] | None:
    try:
        return runner(system_prompt=system_prompt, user_msg=user_msg, parse=_parse(revised_tag),
                      job_id=f"{job_id}_seo_review", model=MODEL_ENV or model_for("seo_review"),
                      timeout_seconds=TIMEOUT_SECONDS, max_attempts=MAX_ATTEMPTS,
                      allowed_tools=("WebSearch", "WebFetch"))
    except GenerateError as e:
        return {"status": "unavailable", "error": str(e)[:200]}


def _summary(result: dict[str, Any], revised: bool) -> dict[str, Any]:
    return {"status": "ok", "overall": result["overall"], "summary": result["summary"], "revised": revised,
            **{axis: result[axis] for axis in AXES}}


def review_blog(draft_html: str, meta: dict[str, Any], *, topic: str, job_id: str = "adhoc",
                runner=run_claude_cli) -> tuple[str, dict[str, Any]]:
    """블로그 HTML 을 검토·교정한다. 반환 (본문, meta) — meta.seo_review 에 결과가 실린다.
    교정본이 채택되면 본문·제목·태그가 바뀌고 meta.seo_review.revised=True."""
    if not ENABLED:
        return draft_html, {**meta, "seo_review": {"status": "disabled"}}
    user_msg = (f"주제: {topic}\n제목: {meta.get('title', '')}\n태그: {', '.join(str(t) for t in meta.get('tags', []) or [])}\n\n"
                "다음 블로그 HTML 본문을 SEO·AEO·GEO 기준으로 검토하고 필요하면 교정본을 내세요.\n\n" + draft_html)
    result = _run(BLOG_SYSTEM_PROMPT, user_msg, _HTML_TAG, job_id=job_id, runner=runner)
    if result is None or result.get("status") == "unavailable":
        return draft_html, {**meta, "seo_review": result or {"status": "unavailable"}}
    body = draft_html
    revised = accept_revision(draft_html, result["revised_body"], html=True)
    if revised:
        body = result["revised_body"]
    new_meta = dict(meta)
    if revised and result["revised_title"]:
        new_meta["title"] = result["revised_title"]
    if revised and result["revised_tags"]:
        new_meta["tags"] = result["revised_tags"]
    new_meta["seo_review"] = _summary(result, revised)
    return body, new_meta


def review_youtube_post(post: str, meta: dict[str, Any], *, topic: str, job_id: str = "adhoc",
                        runner=run_claude_cli) -> tuple[str, dict[str, Any]]:
    """유튜브 커뮤니티 게시글 검토·교정. 반환 (게시글, meta)."""
    if not ENABLED:
        return post, {**meta, "seo_review": {"status": "disabled"}}
    user_msg = f"책 주제: {topic}\n\n다음 커뮤니티 게시글을 SEO·AEO·GEO 기준으로 검토하고 필요하면 교정본을 내세요.\n\n{post}"
    result = _run(POST_SYSTEM_PROMPT, user_msg, _POST_TAG, job_id=job_id, runner=runner)
    if result is None or result.get("status") == "unavailable":
        return post, {**meta, "seo_review": result or {"status": "unavailable"}}
    revised = accept_revision(post, result["revised_body"], html=False)
    body = result["revised_body"] if revised else post
    return body, {**meta, "seo_review": _summary(result, revised)}
