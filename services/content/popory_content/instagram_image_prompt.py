# claude CLI에 줄 인스타그램 캐러셀 시스템/유저 프롬프트.
from typing import Any


def _rules(slide_count: int) -> str:
    return f"""당신은 한국어 인스타그램 캐러셀 콘텐츠 작가입니다. 주제로 슬라이드 {slide_count}장짜리 캐러셀 게시물을 만듭니다.

## 1. 리서치
- WebSearch·WebFetch 로 주제 관련 신뢰할 자료를 수집합니다.
- 확인된 사실만 씁니다.

## 2. 구성
- 슬라이드 {slide_count}장을 만듭니다.
- 첫 슬라이드: 강렬한 후킹 제목(팔로우 욕구 유발).
- 중간 슬라이드: 핵심 내용을 슬라이드별 하나씩.
- 마지막 슬라이드: 요약 + 팔로우 유도.
- 각 슬라이드: title(10자 이내 굵은 헤드라인), body(2~3줄 본문), image_prompt(영어, 정사각형 이미지 묘사, 텍스트 없음).
- 전체 게시물 caption도 작성합니다(해시태그 포함, 500자 이내).

## 3. 출력 (반드시 마지막 응답에 두 태그를 정확히 포함)
- 태그 안에는 코드 블록 표시(```)를 쓰지 않습니다.
<slides_json>
[{{"title": "...", "body": "...", "image_prompt": "english square image description"}}, ...]
</slides_json>
<carousel_meta>
{{"caption": "...", "hashtags": ["..."]}}
</carousel_meta>
"""


_STYLE_HEADER = "\n## 4. 말투 스타일 (아래 샘플의 어조를 따르세요)\n"


def build_carousel_system_prompt(style_samples: list[str], slide_count: int = 7) -> str:
    sp = _rules(slide_count)
    if style_samples:
        sp += _STYLE_HEADER
        for i, s in enumerate(style_samples, 1):
            sp += f"\n--- 샘플 {i} ---\n{s.strip()}\n"
    return sp


def build_carousel_user_message(topic: str, sources: list[dict[str, Any]]) -> str:
    lines = [f"주제: {topic}", "", "시스템 규칙에 따라 인스타그램 캐러셀을 작성하세요."]
    refs = [s for s in sources if s.get("url")]
    if refs:
        lines.append("\n참고 링크:")
        for s in refs:
            note = f" — {s['note']}" if s.get("note") else ""
            lines.append(f"- {s['url']}{note}")
    lines.append("")
    lines.append("마지막 응답에 <slides_json>...</slides_json> 과 <carousel_meta>...</carousel_meta> 두 태그를 정확히 포함하세요.")
    return "\n".join(lines)
