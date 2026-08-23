# 외국 저자·인명의 한글 표기 교정. LLM이 국내 출판 표기와 다르게 쓰면 제목·대본·태그·설명이
# 통째로 틀린 이름으로 나간다. 제목은 검색 유입에 직결되므로 그대로 두면 손해다.
#
# 규칙 — 키는 **틀린 표기**, 값은 **국내 출판사가 실제로 쓰는 표기**다. 국립국어원 외래어
# 표기법이 아니라 출판사 표기를 따른다. 독자가 검색창에 치는 건 책 표지에 박힌 쪽이다.
#
# 새 항목은 **책 표지나 서점 상세페이지에서 확인한 뒤에만** 넣는다. 추측으로 넣으면 맞는
# 이름을 틀리게 바꾸는, 원래보다 나쁜 버그가 된다. 표기가 출판사마다 갈리는 이름
# (예: 말콤/맬컴 글래드웰)은 어느 쪽도 오타가 아니므로 아예 넣지 않는다.
import re

_NAME_FIXES: dict[str, str] = {
    # Bodo Schäfer — 『돈, 뜨겁게 사랑하고 차갑게 다루어라』(토네이도)
    "보도 새퍼": "보도 섀퍼",
    # Napoleon Hill — 『생각하라 그리고 부자가 되어라』
    "나폴레옹 힐": "나폴레온 힐",
    # Robert Kiyosaki — 『부자 아빠 가난한 아빠』(민음인)
    "로버트 기요사끼": "로버트 기요사키",
}


def _expand(fixes: dict[str, str]) -> dict[str, str]:
    """띄어쓰기를 뗀 형태도 같이 잡는다(`보도새퍼` → `보도섀퍼`). 원문의 띄어쓰기 습관을
    바꾸지 않으려고 값도 같은 방식으로 붙여 둔다."""
    out = dict(fixes)
    for wrong, right in fixes.items():
        if " " in wrong:
            out.setdefault(wrong.replace(" ", ""), right.replace(" ", ""))
    return out


_FIXES = _expand(_NAME_FIXES)
# 긴 키가 먼저 걸리게 정렬 — 짧은 키가 긴 이름의 일부를 먼저 먹는 걸 막는다.
_PATTERN = re.compile("|".join(re.escape(k) for k in sorted(_FIXES, key=len, reverse=True)))


def normalize_names(text: str) -> str:
    """표기가 틀린 인명을 출판 표기로 바꾼다. 매칭이 없으면 원문 그대로 돌려준다."""
    if not text:
        return text
    return _PATTERN.sub(lambda m: _FIXES[m.group(0)], text)
