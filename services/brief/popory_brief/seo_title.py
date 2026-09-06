# 브리핑 제목의 검색 유입(SEO) 정규화 — 말머리·날짜를 앞에서 걷어내고, 발행 정보는 뒤로 보낸다.
#
# 배경(2026-09-06 제미나이 검토). 네이버·구글 검색 봇은 제목의 **가장 왼쪽(첫 15자)** 에 가장 높은
# 키워드 가중치를 준다. 그런데 기존 제목은 `[부동산 주간 이슈 브리핑] 2026-09-05` 처럼 검색자가
# 절대 검색창에 치지 않는 고정 말머리와 날짜가 앞단을 전부 차지했다. 검색자는 "개포우성7차 통합심의",
# "종부세 1주택 실거주 공제" 같은 구체 이슈를 친다. 그래서 형식을 다음으로 바꾼다.
#
#     {핵심 검색 키워드 1~2개} {핵심 팩트 요약} | {발행 라벨} {카테고리} 브리핑
#     예. 개포우성7차 가락삼익 재건축 통과와 코인 매각 주택 매수 분석 | 9월 1주차 부동산 브리핑
#
# 규칙은 각 카테고리 SKILL.md 에 있지만 LLM 은 습관적으로 옛 말머리를 붙인다. 이 모듈은 그 길목에서
# 결정적으로 걸러 주는 안전망이다(names.py 와 같은 원칙 — 프롬프트를 믿되 출력은 검증한다).
#
# 하지 않는 것. 제목을 새로 짓거나 줄이지 않는다. 키워드가 없는 제목(말머리+날짜뿐)은 fallback 으로
# 돌려 사람이 알아볼 수 있게 한다 — 없는 내용을 지어내는 것보다 낫다.
from __future__ import annotations

import datetime
import re

# 제목 앞의 `[...]` 말머리. 여러 개 붙어도 전부 걷어낸다 (`[부동산] [주간]`).
_LEADING_BRACKET = re.compile(r"^\s*(?:[\[【][^\]】]*[\]】]\s*)+")
# 제목 앞의 날짜. `2026-09-05`, `2026.09.05`, `2026/9/5`, `9월 5일`, `(2026-09-05)` 등.
_LEADING_DATE = re.compile(
    r"^\s*\(?(?:\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}월\s*\d{1,2}일)\)?\s*[:\-–—|]?\s*")
# 제목 앞의 순번·구분 기호 (`① `, `1. `, `- `).
_LEADING_MARKER = re.compile(r"^\s*(?:[①-⑳]|\d{1,2}[.)])\s*")
# 옛 형식의 꼬리 괄호. `(당일 브리핑 및 주간브리핑 포함)` 처럼 브리핑 종류만 적은 설명은 검색어가 아니다.
_TRAILING_NOTE = re.compile(r"\s*\((?:[^()]*브리핑[^()]*)\)\s*$")
# 옛 말머리에서 걷어낸 뒤 남은 게 날짜뿐이면 키워드가 없는 제목이다.
_DATE_ONLY = re.compile(r"^[\d\s\-./월일()]*$")
_SEP = " | "
# 네이버 블로그 제목 상한은 100자, 검색 결과에서 잘리지 않는 안전선은 60자 안팎이다.
RECOMMENDED_MAX = 60


def date_label(d: datetime.date, *, weekly: bool) -> str:
    """발행 라벨. 주간 브리핑은 `9월 1주차`, 일간은 `9월 5일`. 앞자리 0 없이 쓴다(한국식 표기)."""
    if weekly:
        week = (d.day - 1) // 7 + 1
        return f"{d.month}월 {week}주차"
    return f"{d.month}월 {d.day}일"


def strip_boilerplate(title: str) -> str:
    """제목 앞의 `[말머리]`·날짜·순번 기호와 뒤의 `(… 브리핑 …)` 설명을 걷어낸다.
    키워드 본문만 남기며, 말머리 안에 있던 단어는 되살리지 않는다."""
    t = (title or "").strip()
    # 말머리와 날짜가 번갈아 붙기도 한다 (`[X] 2026-09-05 [Y]`). 더 벗겨지지 않을 때까지 반복.
    while True:
        before = t
        t = _LEADING_BRACKET.sub("", t)
        t = _LEADING_DATE.sub("", t)
        t = _LEADING_MARKER.sub("", t)
        if t == before:
            break
    t = _TRAILING_NOTE.sub("", t)
    return t.strip(" \t:-–—|")


def has_suffix(title: str) -> bool:
    return _SEP in title


def normalize_title(title: str, *, suffix: str, fallback: str) -> str:
    """LLM 이 낸 제목을 SEO 형식으로 맞춘다.

    - 앞의 말머리·날짜를 걷어낸다.
    - 걷어낸 뒤 키워드가 남지 않으면(말머리+날짜뿐) fallback 을 그대로 돌려준다.
    - `|` 뒤 발행 꼬리가 없으면 `{suffix}` 를 붙인다. 이미 있으면 LLM 이 쓴 것을 존중한다.
    """
    core = strip_boilerplate(title)
    if not core or _DATE_ONLY.match(core):
        return fallback
    if has_suffix(core):
        return core
    suffix = (suffix or "").strip()
    return f"{core}{_SEP}{suffix}" if suffix else core


def keyword_part(title: str) -> str:
    """`|` 앞의 검색 키워드 부분. 검토 로그·자가 점검용."""
    return title.split(_SEP, 1)[0].strip() if has_suffix(title) else title.strip()
