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
    (None, "warn"), ("", "warn"), ("warn", "warn"),
    ("off", "off"), ("OFF", "off"), (" strict ", "strict"),
    ("nonsense", "warn"),
])
def test_mode_parsing(monkeypatch, raw, expected):
    """오타가 검사를 조용히 끄면 안 된다 — 모르는 값은 warn 으로 돌린다."""
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


def test_strip_dead_links_noop_when_nothing_dead():
    body = f"- [동아 — 제목]({_LIVE})\n"
    assert lc.strip_dead_links(body, []) == (body, 0)


def test_degrade_is_a_valid_mode(monkeypatch):
    monkeypatch.setenv("BRIEF_LINK_CHECK", "degrade")
    assert lc.mode() == "degrade"
