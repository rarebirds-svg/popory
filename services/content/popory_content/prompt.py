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

## 5. SEO·AEO·GEO·저작권
검색엔진(SEO)만이 아니라 답변엔진(AEO: 네이버 AI 브리핑·구글 AI 오버뷰 같은 '바로 답' 영역)과 생성형 엔진(GEO: ChatGPT·Perplexity 등 LLM 검색이 인용할 문서)까지 겨냥해 씁니다.
- [SEO] 핵심 키워드를 제목(<h2>)과 첫 문단에 자연스럽게 배치합니다. 소제목(<h2>/<h3>) 일부는 독자가 실제로 검색창에 칠 **질문형 문장**으로 씁니다(예: "돈의 심리학은 어떤 책인가요?"). 모든 <img> 에 키워드가 든 alt 를 넣습니다.
- [AEO] **첫 문단은 글의 핵심 질문에 대한 직접 답(2~3문장)** 으로 시작합니다 — 결론을 먼저 말하고 그 뒤에 풉니다. 본문 끝에 <h2>자주 묻는 질문</h2> 섹션을 두고 <h3>질문</h3><p>답</p> 형식으로 3개를 넣습니다(각 답 2~3문장, 답만으로도 완결되게).
- [GEO] 통계·수치·연도·인명은 **문장 안에 출처(매체명)를 함께** 씁니다(예: "○○ 조사에 따르면 …"). 단락마다 인용해 갈 만한 **완결된 한 문장 요약**을 하나씩 두고, 책 제목·저자·출판사 같은 개체(entity)는 첫 등장 때 정확한 정식 명칭으로 씁니다. 핵심 개념은 "X란 …이다" 형태의 정의 문장으로 한 번 명시합니다.
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
