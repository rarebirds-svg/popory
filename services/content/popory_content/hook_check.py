# 롱폼 대본의 첫 장면 프리후크 검수 — 첫 두 문장이 결과(결론·수치·대비)로 시작하는지 판정하고, 어기면 그 문장만 고친다.
#
# 배경(2026-10): 롱폼 평균 시청 지속이 12분 영상에서 약 2분(14~17%)이고 한 영상은 첫 30초에 61%가 이탈했다.
# 실제 대본 10편의 첫 두 문장을 보니 프리후크 규칙(첫 문장에 결론·대비)을 온전히 지킨 건 4편뿐이었다 — 4편은
# "~한 사람이 있었습니다"로 인물·상황을 소개해 반전을 둘째 문장으로 미뤘고, 1편은 배경 도입, 1편은 질문 시작이었다.
# 규칙은 프롬프트에만 있었고 코드로 확인하는 곳이 없었다(parse_video 는 필드 유무만, script_review 는 오탈자만 본다).
#
# 설계 원칙(script_review 와 같다):
# - **fail-open.** 검수기가 죽어도 대본은 그대로 나간다. 대신 결과에 status 를 남겨 "통과"와 "검수 못 함"을 가른다.
# - **첫 장면의 앞 문장만 바꾼다.** 대본을 통째로 다시 쓰게 하면 어미 다양화·길이·CTA 규칙이 무너진다.
#   교체 문장은 아래 검증을 통과해야만 적용하고, 못 미더우면 원문을 둔다(rejected).
# - **없는 사실을 지어내지 않는다.** 새 첫 문장은 대본 뒷부분에서 다룰 내용으로만 쓰게 하고, 코드로도 새 숫자가
#   원문 대본에 없으면 버린다(숫자는 환각이 가장 잘 드러나고 가장 해로운 부분이다).
import json
import os
import re
from typing import Any, Callable

from popory_content.generate import run_claude_cli, model_for, GenerateError

ENABLED = os.environ.get("POPORY_HOOK_CHECK", "1") != "0"
TIMEOUT_SECONDS = int(os.environ.get("POPORY_HOOK_CHECK_TIMEOUT", "300"))
MAX_ATTEMPTS = int(os.environ.get("POPORY_HOOK_CHECK_ATTEMPTS", "2"))
MODEL_ENV = os.environ.get("POPORY_HOOK_CHECK_MODEL")
# 이 길이를 넘는 문장은 훅이 아니라 설명이다. 프롬프트 규칙(60자 안쪽)에 여유를 둔 상한.
FIRST_SENTENCE_MAX = 80
SENTENCE_MAX = 130
# 판정 근거로 모델에 보여 줄 대본 길이 상한(자). 결과는 뒷부분에서 가져오므로 첫 장면 외에도 보여 준다.
CONTEXT_MAX_CHARS = 9000

SYSTEM_PROMPT = """당신은 유튜브 롱폼 대본의 프리후크 검수자입니다. 첫 장면의 첫 두 문장이 아래 규칙을 지켰는지 판정하고, 어겼으면 그 문장만 고쳐 돌려줍니다.

규칙: **첫 문장에 '결과'를 먼저 준다.** 누구의 이야기인지 소개하기 전에, 이야기가 도착하는 결론·충격적인 수치·극적인 대비를 먼저 말한다. 첫 문장은 60자 안쪽의 평서문 하나이고, 둘째 문장은 그 결과를 더 놀랍게 만드는 반전이나 이유의 단서다.

통과 기준(하나라도 해당하면 통과):
- 첫 문장에 결론·결과가 들어 있다("몇 년 뒤 그는 수천만 독자의 스승이 됐습니다").
- 첫 문장에 충격적인 수치나 사실이 들어 있다.
- 첫 문장이 하나의 문장 안에서 극적인 대비를 이룬다("100억을 남기고 떠난 청소부, 그리고 파산한 하버드 출신 임원").
- 첫 문장이 도발적인 주장이다.

위반(kind):
- intro_person — 인물·상황을 소개하며 연다("~한 사람이 있었습니다", "1987년, 한 경영자가 취임합니다"). 결과가 둘째 문장 이후로 밀려 있어도 위반이다.
- question — 질문으로 연다.
- greeting — 인사·채널 소개·"오늘은 …를 이야기해 보겠습니다".
- lyrical — 서정적 배경 묘사·시대 설명으로 연다.
- other — 그 밖에 결과가 없는 시작.

고칠 때(위반일 때만):
- 첫 두 문장(또는 첫 문장 하나)을 바꾼 새 문장 목록 rewrite 를 준다. replace_count 는 원문에서 몇 문장을 대체하는지(1~3)다. 나머지 원문 문장은 그대로 이어진다.
- 새 첫 문장은 60자 안쪽 평서문이고 결과(결론·수치·대비)로 시작한다. 새 문장은 합쇼체를 기본으로 해요체(~죠)를 섞은 구어체다.
- **대본에 이미 나온 사실만** 쓴다. 대본에 없는 인물·사건·숫자를 지어내지 않는다. 결과는 아래 대본 뒷부분(장면 2 이후)에서 가져온다.
- 원문 첫 장면의 도입 정보(인물 소개 등)를 잃지 않는다 — 결과를 앞으로 당기고, 소개는 뒤 문장에서 이어지게 한다.
- 질문으로 시작하지 않는다. 인사하지 않는다.

출력은 마지막 응답에 태그 하나만. 코드블록 표시(```)를 넣지 않는다. 통과면 rewrite 는 빈 배열이다.
<hook_verdict>
{"pass": true또는false, "kind": "intro_person|question|greeting|lyrical|other|none", "reason": "짧은 이유", "replace_count": 2, "rewrite": ["새 첫 문장.", "새 둘째 문장."]}
</hook_verdict>
"""

_TAG = re.compile(r"<hook_verdict>\s*(\{.*?\})\s*</hook_verdict>", re.S)
_GREETING = re.compile(r"안녕|반갑|오늘은\s*.{0,30}(이야기|알아보|살펴|소개)")
_NUMBER = re.compile(r"\d[\d,.]*")


def _parse_verdict(stdout: str) -> dict[str, Any]:
    m = _TAG.search(stdout)
    if not m:
        raise ValueError("hook_verdict 태그 없음")
    data = json.loads(m.group(1))
    if not isinstance(data, dict) or not isinstance(data.get("pass"), bool):
        raise ValueError("hook_verdict 에 pass(불리언)가 없음")
    rewrite = data.get("rewrite") or []
    if not isinstance(rewrite, list):
        raise ValueError("rewrite 가 배열이 아님")
    return {
        "pass": data["pass"],
        "kind": str(data.get("kind") or "none")[:40],
        "reason": str(data.get("reason") or "")[:200],
        "replace_count": data.get("replace_count") if isinstance(data.get("replace_count"), int) else 2,
        "rewrite": [str(x).strip() for x in rewrite if str(x).strip()],
    }


def _numbers(text: str) -> set[str]:
    """본문에 나온 숫자 토큰(쉼표·소수점 정리). 새 첫 문장이 지어낸 수치를 걸러내는 데 쓴다."""
    return {n.replace(",", "").rstrip(".") for n in _NUMBER.findall(text)}


def _corpus(scenes: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    parts = [str(meta.get("title", "")), str(meta.get("description", ""))]
    for s in scenes:
        parts += [str(s.get("caption", "")), str(s.get("narration", ""))]
        card = s.get("card")
        if isinstance(card, dict):
            parts.append(str(card.get("text", "")) + " ".join(str(x) for x in card.get("items", []) or []))
    return "\n".join(parts)


def validate_rewrite(verdict: dict[str, Any], sentences: list[str], corpus: str) -> str | None:
    """교체 문장이 믿을 만한지. 문제가 있으면 사유 문자열, 괜찮으면 None."""
    rewrite = verdict["rewrite"]
    n = verdict["replace_count"]
    if not rewrite:
        return "rewrite 가 비어 있음"
    if not 1 <= len(rewrite) <= 3:
        return "rewrite 문장 수가 1~3 이 아님"
    if not 1 <= n <= min(3, len(sentences)):
        return f"replace_count({n}) 가 원문 문장 수 범위를 벗어남"
    if len(rewrite[0]) > FIRST_SENTENCE_MAX:
        return f"새 첫 문장이 {FIRST_SENTENCE_MAX}자를 넘음"
    if any(len(x) > SENTENCE_MAX for x in rewrite):
        return f"새 문장이 {SENTENCE_MAX}자를 넘음"
    if rewrite[0].rstrip().endswith("?"):
        return "새 첫 문장이 질문"
    if any(_GREETING.search(x) for x in rewrite):
        return "새 문장에 인사·안내가 있음"
    if rewrite == sentences[:len(rewrite)]:
        return "원문과 같음"
    new_nums = _numbers(" ".join(rewrite)) - _numbers(corpus)
    if new_nums:
        return f"원문에 없는 숫자: {sorted(new_nums)}"
    return None


def _user_message(scenes: list[dict[str, Any]], meta: dict[str, Any], first_sentences: list[str]) -> str:
    lines = [f"[제목] {meta.get('title', '')}", "", f"[첫 장면 헤드라인] {scenes[0].get('caption', '')}",
             "[첫 장면 내레이션 — 문장 단위]"]
    lines += [f"{i}. {s}" for i, s in enumerate(first_sentences, 1)]
    lines += ["", "[전체 대본 — 결과(결론·수치·대비)는 여기서 가져온다]"]
    body: list[str] = []
    for i, s in enumerate(scenes, 1):
        body.append(f"(장면 {i} · {s.get('caption', '')}) {s.get('narration', '')}")
    text = "\n".join(body)
    lines.append(text[:CONTEXT_MAX_CHARS])
    lines += ["", "첫 장면의 첫 두 문장이 프리후크 규칙을 지켰는지 판정해 주세요."]
    return "\n".join(lines)


def check_hook(scenes: list[dict[str, Any]], meta: dict[str, Any], *,
               split: Callable[[str], list[str]], job_id: str = "adhoc",
               runner=run_claude_cli) -> dict[str, Any]:
    """첫 장면 프리후크를 판정하고 어겼으면 제자리에서 앞 문장을 고친다. 반환은 meta 에 실을 요약.

    status: passed(규칙 지킴) / rewritten(고침) / rejected(고치려 했지만 검증에 걸려 원문 유지) /
            unavailable(검수기 실패 → 원문 유지) / disabled / skipped(첫 장면이 비었음).
    split 은 문장 분리 함수(video._split_sentences) — 순환 import 를 피하려고 받는다."""
    if not ENABLED:
        return {"status": "disabled"}
    if not scenes or not str(scenes[0].get("narration", "")).strip():
        return {"status": "skipped"}
    narration = str(scenes[0]["narration"])
    sentences = split(narration) or [narration.strip()]
    before = sentences[:3]
    try:
        verdict = runner(system_prompt=SYSTEM_PROMPT, user_msg=_user_message(scenes, meta, sentences[:4]),
                         parse=_parse_verdict, job_id=f"{job_id}_hook_check",
                         model=MODEL_ENV or model_for("script_review"),
                         timeout_seconds=TIMEOUT_SECONDS, max_attempts=MAX_ATTEMPTS, allowed_tools=())
    except GenerateError as e:
        return {"status": "unavailable", "error": str(e)[:200], "before": before}
    if verdict["pass"]:
        return {"status": "passed", "kind": verdict["kind"], "reason": verdict["reason"], "before": before}
    problem = validate_rewrite(verdict, sentences, _corpus(scenes, meta))
    if problem:
        return {"status": "rejected", "kind": verdict["kind"], "reason": verdict["reason"],
                "rejected_because": problem, "before": before}
    new_sentences = verdict["rewrite"] + sentences[verdict["replace_count"]:]
    scenes[0]["narration"] = " ".join(new_sentences)
    return {"status": "rewritten", "kind": verdict["kind"], "reason": verdict["reason"],
            "before": before, "after": new_sentences[:3]}
