# 책 제목·저자로 4개 서점 검색 링크 댓글을 만든다.
from urllib.parse import quote

_STORES = [
    ("교보문고", "https://search.kyobobook.co.kr/search?keyword={q}"),
    ("영풍문고", "https://www.ypbooks.co.kr/search_word.yp?searchWord={q}"),
    ("알라딘", "https://www.aladin.co.kr/search/wsearchresult.aspx?SearchWord={q}"),
    ("YES24", "https://www.yes24.com/product/search?query={q}"),
]


def build_purchase_comment(title: str, author: str | None) -> str:
    """4개 서점 검색 링크 + 안내 문구. 저자 있으면 검색어에 포함."""
    label = f"{title} - {author}" if author else title
    keyword = f"{title} {author}" if author else title
    q = quote(keyword, safe="")
    lines = [f"📚 『{label}』 구매하기 — 작가와 출판사를 응원해 주세요."]
    for name, tmpl in _STORES:
        lines.append(f"· {name}: {tmpl.format(q=q)}")
    return "\n".join(lines)
