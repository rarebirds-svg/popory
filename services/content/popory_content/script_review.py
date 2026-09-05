# 대본 오탈자·고유명사 검수 — 생성된 장면 대본·제목·태그를 claude CLI 로 한 번 훑어 교정한다.
#
# 배경(2026-09): 발행된 영상에서 `버몬트→범트`, `구제 옷가게→구제욱가게`, `부(Wealth)→불` 같은
# 오탈자가 자막·TTS 로 그대로 나갔다. names.py 의 교정표는 **아는 오타**만 잡는다. 여기서는 사람이
# 텍스트 편집기로 1분 훑는 검수 루틴을 자동화한다 — 고유명사(인명·지명·책 제목·기관명)와
# 어색한 단어·오탈자를 찾아 "이 문자열을 이걸로" 형태의 교정 목록을 받고, 대본·제목·태그·설명에
# 같은 치환을 일괄 적용한다.
#
# 설계 원칙:
# - **fail-open.** 검수기가 죽어도 대본은 그대로 나간다(image_review 와 같은 원칙). 대신 결과에
#   status="unavailable" 을 남겨 "검수했는데 고칠 게 없음"과 구분한다.
# - **교정은 치환 목록으로만.** 대본을 통째로 다시 쓰게 하면 어미 다양화·길이·CTA 규칙이 무너진다.
#   from→to 쌍만 받아 적용하므로 검수기가 문장을 바꿔치기할 수 없다.
# - 치환은 보수적으로: from 이 대본 어딘가에 실제로 있어야 하고, 너무 짧은(1글자) 치환은 버린다.
import json
import os
import re
from typing import Any

from popory_content.generate import run_claude_cli, model_for, GenerateError

ENABLED = os.environ.get("POPORY_SCRIPT_REVIEW", "1") != "0"
TIMEOUT_SECONDS = int(os.environ.get("POPORY_SCRIPT_REVIEW_TIMEOUT", "300"))
MAX_ATTEMPTS = int(os.environ.get("POPORY_SCRIPT_REVIEW_ATTEMPTS", "2"))
MODEL_ENV = os.environ.get("POPORY_SCRIPT_REVIEW_MODEL")
MAX_FIXES = 30

SYSTEM_PROMPT = """당신은 한국어 유튜브 대본의 교정자입니다. 대본을 **다시 쓰지 않고**, 틀린 부분만 찾아 치환 목록으로 돌려줍니다.

찾을 것:
- 고유명사 오기 — 인명·지명·책 제목·기관명·상품명. 외국 저자명은 국립국어원 표기가 아니라 **국내 출판사가 책 표지에 쓰는 표기**가 정답입니다(예: 보도 섀퍼, 모건 하우절, 나폴레온 힐). 확신이 없으면 WebSearch 로 서점 상세페이지·출판사 표기를 확인합니다. 출판사마다 갈리는 표기(말콤/맬컴 글래드웰)는 오타가 아니므로 건드리지 않습니다.
- 명백한 오탈자·탈락 글자·잘못 붙은 단어(예: "구제욱가게"→"구제 옷가게", "범트"→"버몬트").
- 문맥상 뜻이 통하지 않는 어색한 단어(예: 부(富)를 "불"로 쓴 경우).
- 숫자·단위 오기(예: 100억 → 10억처럼 근거와 다른 수치)는 **근거가 확실할 때만** 고칩니다.

건드리지 말 것:
- 문체·어미·문장 길이·구성. 취향 교정은 하지 않습니다.
- 맞는 문장을 더 좋은 문장으로 바꾸는 일. 틀린 것만 고칩니다.
- "구독과 좋아요" 같은 마무리 문구, 카드 문구의 줄임.

출력은 마지막 응답에 태그 하나만. 고칠 게 없으면 빈 배열을 넣습니다. 태그 안에 코드블록 표시(```)를 넣지 않습니다.
<script_fixes>
[{"from": "대본에 실제로 있는 문자열", "to": "고친 문자열", "reason": "짧은 이유"}]
</script_fixes>
- from 은 대본에 **그대로 존재하는 문자열**이어야 합니다(부분 문자열, 2글자 이상). 같은 오기가 여러 번 나오면 한 항목이면 됩니다(전부 치환됩니다).
"""

_TAG = re.compile(r"<script_fixes>\s*(\[.*?\])\s*</script_fixes>", re.S)


def _parse_fixes(stdout: str) -> list[dict[str, str]]:
    m = _TAG.search(stdout)
    if not m:
        raise ValueError("script_fixes 태그 없음")
    data = json.loads(m.group(1))
    if not isinstance(data, list):
        raise ValueError("script_fixes 가 배열이 아님")
    out: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        src, dst = str(item.get("from") or ""), str(item.get("to") or "")
        if not src or src == dst:
            continue
        out.append({"from": src, "to": dst, "reason": str(item.get("reason") or "")[:120]})
    return out[:MAX_FIXES]


def _script_text(scenes: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    lines = [f"[제목] {meta.get('title', '')}", f"[설명] {meta.get('description', '')}",
             f"[태그] {', '.join(str(t) for t in meta.get('tags', []) or [])}", ""]
    for i, s in enumerate(scenes, 1):
        lines.append(f"[장면 {i} 헤드라인] {s.get('caption', '')}")
        lines.append(f"[장면 {i} 내레이션] {s.get('narration', '')}")
        card = s.get("card")
        if isinstance(card, dict):
            body = card.get("text") or " / ".join(card.get("items", []))
            lines.append(f"[장면 {i} 카드] {card.get('title') or ''} {body}".strip())
        lines.append("")
    return "\n".join(lines)


def apply_fixes(scenes: list[dict[str, Any]], meta: dict[str, Any],
                fixes: list[dict[str, str]]) -> list[dict[str, str]]:
    """치환을 장면·메타에 적용하고 **실제로 적용된** 항목만 돌려준다. 원본에 없는 from 은 무시 —
    검수기가 지어낸 문자열로 엉뚱한 곳을 바꾸는 걸 막는다."""
    corpus = _script_text(scenes, meta)
    applied: list[dict[str, str]] = []
    for fx in fixes:
        src = fx["from"]
        if len(src) < 2 or src not in corpus:
            continue
        applied.append(fx)

    def sub(text: Any) -> Any:
        if not isinstance(text, str):
            return text
        for fx in applied:
            text = text.replace(fx["from"], fx["to"])
        return text

    if applied:
        for s in scenes:
            s["caption"] = sub(s.get("caption"))
            s["narration"] = sub(s.get("narration"))
            card = s.get("card")
            if isinstance(card, dict):
                for k in ("text", "source", "title"):
                    if k in card:
                        card[k] = sub(card[k])
                if isinstance(card.get("items"), list):
                    card["items"] = [sub(x) for x in card["items"]]
        for k in ("title", "description", "thumbnail_copy"):
            if k in meta:
                meta[k] = sub(meta[k])
        if isinstance(meta.get("tags"), list):
            meta["tags"] = [sub(t) for t in meta["tags"]]
    return applied


def review_script(scenes: list[dict[str, Any]], meta: dict[str, Any], *,
                  job_id: str = "adhoc", runner=run_claude_cli) -> dict[str, Any]:
    """대본을 검수해 제자리에서 교정한다. 반환은 meta 에 실을 요약 {status, fixes}.
    status: ok(검수 완료) / unavailable(검수기 실패 → 원문 그대로) / disabled."""
    if not ENABLED:
        return {"status": "disabled", "fixes": []}
    user_msg = ("다음 유튜브 대본에서 고유명사 오기·오탈자·어색한 단어만 찾아 치환 목록으로 돌려주세요.\n\n"
                + _script_text(scenes, meta))
    try:
        fixes = runner(system_prompt=SYSTEM_PROMPT, user_msg=user_msg, parse=_parse_fixes,
                       job_id=f"{job_id}_script_review", model=MODEL_ENV or model_for("script_review"),
                       timeout_seconds=TIMEOUT_SECONDS, max_attempts=MAX_ATTEMPTS,
                       allowed_tools=("WebSearch", "WebFetch"))
    except GenerateError as e:
        return {"status": "unavailable", "fixes": [], "error": str(e)[:200]}
    applied = apply_fixes(scenes, meta, fixes)
    return {"status": "ok", "fixes": applied}
