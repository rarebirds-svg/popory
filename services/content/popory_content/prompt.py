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
- 태그 안에는 코드 블록 표시(```)를 쓰지 말고 내용만 넣습니다.
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
