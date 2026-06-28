# 책 제목·저자로 4개 서점 검색 링크 댓글을 만든다.
import requests
from urllib.parse import quote

_STORES = [
    ("교보문고", "https://search.kyobobook.co.kr/search?keyword={q}"),
    ("영풍문고", "https://www.ypbooks.co.kr/search_word.yp?searchWord={q}"),
    ("알라딘", "https://www.aladin.co.kr/search/wsearchresult.aspx?SearchWord={q}"),
    ("YES24", "https://www.yes24.com/product/search?query={q}"),
]


_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _default_status(url: str) -> int:
    """검색 URL 도달성 확인용 기본 fetcher — status code 반환."""
    resp = requests.get(url, timeout=8, headers={"User-Agent": _UA}, allow_redirects=True, stream=True)
    resp.close()
    return resp.status_code


def validate_store_url(url: str, fetcher=_default_status) -> bool:
    """도달 가능(2xx~3xx)하면 True. 예외·4xx·5xx면 False."""
    try:
        code = fetcher(url)
    except Exception:  # noqa: BLE001 — 네트워크 오류는 무효 처리.
        return False
    return code is not None and 200 <= code < 400


def build_purchase_comment_validated(title: str, author: str | None, fetcher=_default_status) -> str | None:
    """도달 가능한 서점 링크만 담은 댓글. 유효 0개면 None."""
    label = f"{title} - {author}" if author else title
    keyword = f"{title} {author}" if author else title
    q = quote(keyword, safe="")
    valid = [(name, tmpl.format(q=q)) for name, tmpl in _STORES if validate_store_url(tmpl.format(q=q), fetcher)]
    if not valid:
        return None
    lines = [f"📚 『{label}』 구매하기 — 작가와 출판사를 응원해 주세요."]
    for name, url in valid:
        lines.append(f"· {name}: {url}")
    return "\n".join(lines)


def build_purchase_comment(title: str, author: str | None) -> str:
    """4개 서점 검색 링크 + 안내 문구. 저자 있으면 검색어에 포함."""
    label = f"{title} - {author}" if author else title
    keyword = f"{title} {author}" if author else title
    q = quote(keyword, safe="")
    lines = [f"📚 『{label}』 구매하기 — 작가와 출판사를 응원해 주세요."]
    for name, tmpl in _STORES:
        lines.append(f"· {name}: {tmpl.format(q=q)}")
    return "\n".join(lines)
