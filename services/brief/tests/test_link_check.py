# link_check — URL 추출, 죽은 링크 판정 규칙, 모드 해석 단위 테스트 (실제 네트워크 없음).
"""404·410 만 죽은 링크로 확정한다. 403·5xx·타임아웃을 실패로 보면 봇 차단 언론사의
정상 인용이 탈락한다 — 2026-09-15 실측(메트로신문 403, 뉴스투나잇 연결 실패)에서 나온 규칙."""
from __future__ import annotations

import pytest

from popory_brief import link_check as lc


# ---------------- URL 추출 ----------------

def test_extract_urls_from_markdown_source_lines():
    body = (
        "- [뉴시스 — 제목 (2026.9.15)](https://www.newsis.com/view/NISX123)\n"
        "- [동아 — 제목 (2026.9.14)](https://www.donga.com/news/article/all/1/2)\n"
    )
    assert lc.extract_urls(body) == [
        "https://www.newsis.com/view/NISX123",
        "https://www.donga.com/news/article/all/1/2",
    ]


def test_extract_urls_drops_duplicates_keeping_order():
    body = "a https://x.test/1 b https://y.test/2 c https://x.test/1"
    assert lc.extract_urls(body) == ["https://x.test/1", "https://y.test/2"]


def test_extract_urls_strips_trailing_punctuation():
    """문장 끝 구두점이 URL 에 붙어 오면 404 오판이 된다."""
    assert lc.extract_urls("자세히는 https://x.test/a. 그리고") == ["https://x.test/a"]


def test_extract_urls_excludes_markdown_closing_bracket():
    assert lc.extract_urls("[제목](https://x.test/a)") == ["https://x.test/a"]


def test_extract_urls_keeps_balanced_parentheses():
    """위키식 `Foo_(bar)` 를 `Foo_(bar` 로 자르면 없는 주소를 404 로 판정하고 `)` 가 본문에 남는다."""
    body = "[위키](https://en.wikipedia.org/wiki/Foo_(bar)) 참고"
    assert lc.extract_urls(body) == ["https://en.wikipedia.org/wiki/Foo_(bar)"]


def test_extract_urls_stops_at_closing_paren_that_is_not_part_of_url():
    assert lc.extract_urls("(출처 https://x.test/a) 그리고") == ["https://x.test/a"]


def test_extract_urls_respects_limit():
    body = " ".join(f"https://x.test/{i}" for i in range(50))
    assert len(lc.extract_urls(body, limit=5)) == 5


def test_extract_urls_empty_when_none():
    assert lc.extract_urls("링크 없는 본문") == []
    assert lc.extract_urls("") == []


# ---------------- 상태코드 판정 ----------------

class _Resp:
    def __init__(self, status: int):
        self.status_code = status

    def close(self):
        pass


def _stub(monkeypatch, codes: dict[str, int | None]):
    """URL → 상태코드(또는 None=예외) 대역. HEAD 만 쓰는 경로를 확인한다."""
    def _head(url, **kwargs):
        code = codes.get(url)
        if code is None:
            raise lc.requests.ConnectionError("boom")
        return _Resp(code)
    monkeypatch.setattr(lc.requests, "head", _head)
    monkeypatch.setattr(lc.requests, "get", _head)


@pytest.mark.parametrize("code", [404, 410])
def test_dead_links_reports_missing_documents(monkeypatch, code):
    _stub(monkeypatch, {"https://x.test/gone": code})
    assert lc.dead_links("[t](https://x.test/gone)") == [("https://x.test/gone", code)]


@pytest.mark.parametrize("code", [200, 301, 403, 429, 500, 503])
def test_dead_links_passes_everything_else(monkeypatch, code):
    """403(봇 차단)·5xx 는 판정 불가다 — 실패로 보면 정상 인용이 탈락한다."""
    _stub(monkeypatch, {"https://x.test/a": code})
    assert lc.dead_links("[t](https://x.test/a)") == []


def test_dead_links_passes_on_network_error(monkeypatch):
    _stub(monkeypatch, {"https://x.test/a": None})
    assert lc.dead_links("[t](https://x.test/a)") == []


def test_dead_links_reports_only_the_dead_ones(monkeypatch):
    body = ("[a](https://x.test/ok) [b](https://x.test/gone) "
            "[c](https://x.test/blocked) [d](https://x.test/also-gone)")
    _stub(monkeypatch, {
        "https://x.test/ok": 200,
        "https://x.test/gone": 404,
        "https://x.test/blocked": 403,
        "https://x.test/also-gone": 404,
    })
    assert lc.dead_links(body) == [("https://x.test/gone", 404),
                                   ("https://x.test/also-gone", 404)]


def test_dead_links_empty_body_makes_no_request(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("링크가 없으면 요청하지 않아야 한다")
    monkeypatch.setattr(lc.requests, "head", _boom)
    assert lc.dead_links("링크 없음") == []


def test_check_url_retries_with_get_when_head_rejected(monkeypatch):
    """HEAD 를 막는 서버가 있다 — GET 으로 한 번 더 봐야 405 를 404 로 오판하지 않는다."""
    calls: list[str] = []

    def _head(url, **kwargs):
        calls.append("head")
        return _Resp(405)

    def _get(url, **kwargs):
        calls.append("get")
        return _Resp(200)

    monkeypatch.setattr(lc.requests, "head", _head)
    monkeypatch.setattr(lc.requests, "get", _get)
    assert lc.check_url("https://x.test/a") == 200
    assert calls == ["head", "get"]


# ---------------- 모드 ----------------

@pytest.mark.parametrize("raw,expected", [
    (None, "degrade"), ("", "degrade"), ("warn", "warn"),
    ("off", "off"), ("OFF", "off"), (" strict ", "strict"),
    ("nonsense", "degrade"),
])
def test_mode_parsing(monkeypatch, raw, expected):
    """오타가 검사를 약화시키면 안 된다 — 모르는 값은 기본값(degrade)으로 돌린다."""
    if raw is None:
        monkeypatch.delenv("BRIEF_LINK_CHECK", raising=False)
    else:
        monkeypatch.setenv("BRIEF_LINK_CHECK", raw)
    assert lc.mode() == expected


# ---------------- degrade: 링크만 벗기고 출처 텍스트는 남긴다 ----------------
#
# 2026-09-15 실측에서 claude 경로도 인용 42개 중 7개가 404 였다(카테고리 7개 중 3개).
# strict 면 그 카테고리가 매일 통째로 빈다 — 그래서 링크만 벗기는 중간 단계가 필요하다.

_DEAD = "https://www.lawtimes.co.kr/news/articleView.html?idxno=226414"
_LIVE = "https://www.donga.com/news/article/all/1/2"


def test_strip_dead_links_keeps_citation_text():
    body = f"- [법률신문 — 제목 (2026.9.15)]({_DEAD})\n"
    out, n = lc.strip_dead_links(body, [_DEAD])
    assert out == "- 법률신문 — 제목 (2026.9.15)\n"
    assert n == 1


def test_strip_dead_links_leaves_live_links_alone():
    body = f"- [동아 — 제목]({_LIVE})\n- [법률신문 — 제목]({_DEAD})\n"
    out, n = lc.strip_dead_links(body, [_DEAD])
    assert f"]({_LIVE})" in out          # 살아 있는 링크는 그대로 클릭된다
    assert _DEAD not in out
    assert n == 1


def test_strip_dead_links_handles_repeated_occurrences():
    body = f"[a]({_DEAD}) 중간 [b]({_DEAD})"
    out, n = lc.strip_dead_links(body, [_DEAD])
    assert out == "a 중간 b"
    assert n == 2


def test_strip_dead_links_tolerates_title_and_spaces_in_link():
    body = f'[매체 — 제목]( {_DEAD} "제목")'
    out, n = lc.strip_dead_links(body, [_DEAD])
    assert out == "매체 — 제목"
    assert n == 1


def test_strip_dead_links_leaves_bare_url_untouched():
    """맨 URL 은 문장 구조를 모르는 채 지우면 문맥이 깨진다 — 로그로만 남긴다."""
    body = f"자세히는 {_DEAD} 참고"
    out, n = lc.strip_dead_links(body, [_DEAD])
    assert out == body
    assert n == 0


@pytest.mark.parametrize("text", [
    "[단독] 법률신문 — 제목 (2026.9.15)",   # 언론사 말머리
    r"법률신문 — 제목 \[속보\]",            # 이스케이프된 대괄호
])
def test_strip_dead_links_handles_brackets_in_link_text(text):
    body = f"- [{text}]({_DEAD})\n"
    out, n = lc.strip_dead_links(body, [_DEAD])
    assert out == f"- {text}\n"
    assert n == 1


def test_strip_dead_links_handles_angle_bracket_destination():
    body = f"- [법률신문 — 제목](<{_DEAD}>)\n"
    out, n = lc.strip_dead_links(body, [_DEAD])
    assert out == "- 법률신문 — 제목\n"
    assert n == 1


def _email_html(body: str) -> str:
    """발송 경로 그대로 렌더한 HTML — 맨 URL 도 linkify 로 링크가 된다."""
    from popory_brief.markdown import markdown_to_email_html
    return markdown_to_email_html(body)


@pytest.mark.parametrize("link", [f"[{_DEAD}]({_DEAD})", f"<{_DEAD}>"])
def test_strip_dead_links_does_not_leave_url_text_clickable(link):
    """텍스트가 URL 자체면 표기만 벗겨도 맨 URL 이 남아 렌더러가 다시 링크로 만든다.
    코드 표기로 남겨 주소는 보이되 눌리지 않게 한다."""
    body = f"- 출처 {link}\n"
    out, n = lc.strip_dead_links(body, [_DEAD])
    assert out == f"- 출처 `{_DEAD}`\n"
    assert n == 1
    assert "href" not in _email_html(out)


def test_strip_dead_links_leaves_live_link_that_extends_dead_url():
    """접두 일치로 벗기면 살아 있는 링크가 사라진다 — 주소 전체가 같아야 한다."""
    dead = "https://x.test/a"
    body = "[살아 있음](https://x.test/a?b=1) [죽음](https://x.test/a)"
    out, n = lc.strip_dead_links(body, [dead])
    assert out == "[살아 있음](https://x.test/a?b=1) 죽음"
    assert n == 1


def test_strip_dead_links_handles_parentheses_in_url():
    """URL 안의 괄호를 끝으로 보면 링크가 덜 벗겨지고 `)` 가 본문에 남는다."""
    dead = "https://en.wikipedia.org/wiki/Foo_(bar)"
    out, n = lc.strip_dead_links(f"[위키 — Foo]({dead}) 참고", [dead])
    assert out == "위키 — Foo 참고"
    assert n == 1


def test_degrade_keeps_live_link_with_parentheses(monkeypatch):
    """잘린 주소(`Foo_(bar`)는 실제로 404 다 — 그걸로 판정하면 살아 있는 링크가 벗겨지고
    `)` 가 본문에 남는다. 점검부터 벗기기까지 한 흐름으로 본다."""
    full = "https://en.wikipedia.org/wiki/Foo_(bar)"
    body = f"[위키 — Foo]({full}) 참고"
    _stub(monkeypatch, {full: 200, full[:-1]: 404})
    dead = [u for u, _ in lc.dead_links(body)]
    assert lc.strip_dead_links(body, dead) == (body, 0)


@pytest.mark.parametrize("codes,expected", [
    # 목적지 끝의 `.` 까지가 주소다. 떼고 점검하면 죽은 링크를 놓친다.
    ({"https://x.test/a.": 404, "https://x.test/a": 200}, ("t", 1)),
    # 반대로 뗀 주소로 판정해 벗기면 살아 있는 링크(위키 `Apple_Inc.` 형태)가 사라진다.
    ({"https://x.test/a.": 200, "https://x.test/a": 404}, ("[t](https://x.test/a.)", 0)),
])
def test_degrade_checks_link_destination_verbatim(monkeypatch, codes, expected):
    body = "[t](https://x.test/a.)"
    _stub(monkeypatch, codes)
    dead = [u for u, _ in lc.dead_links(body)]
    assert lc.strip_dead_links(body, dead) == expected


@pytest.mark.parametrize("text", [
    "www.lawtimes.co.kr/news/articleView.html?idxno=226414",
    "lawtimes.co.kr/news/articleView.html?idxno=226414",
    "http://www.lawtimes.co.kr/news/articleView.html?idxno=226414",
])
def test_strip_dead_links_neutralizes_url_text_written_differently(text):
    """스킴·www 만 다른 같은 주소도 렌더러가 다시 링크로 만든다."""
    out, n = lc.strip_dead_links(f"- [{text}]({_DEAD})\n", [_DEAD])
    assert out == f"- `{text}`\n"
    assert n == 1
    assert "href" not in _email_html(out)


def test_strip_dead_links_noop_when_nothing_dead():
    body = f"- [동아 — 제목]({_LIVE})\n"
    assert lc.strip_dead_links(body, []) == (body, 0)


def test_degrade_is_a_valid_mode(monkeypatch):
    monkeypatch.setenv("BRIEF_LINK_CHECK", "degrade")
    assert lc.mode() == "degrade"
