# 본문에 인용된 링크가 실제로 열리는지 확인한다 — 존재하지 않는 출처를 걸러내기 위함.
"""브리핑의 핵심 가치는 "출처를 눌러 확인할 수 있다"는 것이다. 그런데 Gemini 의 Google
Search grounding 은 검색 결과 URL 을 그대로 받아 쓰는 게 아니라 모델이 문장을 쓰면서 URL 을
적어 넣기 때문에, 형식만 맞는 존재하지 않는 링크가 섞인다
(2026-09-15 네이버 시범 실측: 인용 7개 중 2개가 404).

grounding 응답의 근거 URL(groundingMetadata)과 대조하는 방법도 있지만, 구글이 주는 값은
`vertexaisearch.cloud.google.com/grounding-api-redirect/...` 리다이렉트 주소라 기사 URL 과
문자열이 다르다. 리다이렉트를 풀어 비교하려면 구글 도메인에 추가 요청이 필요하고, 모델이
검색 결과 페이지 안에서 본 링크를 인용한 정상 경우까지 탈락시킬 위험이 있다. 그래서 공급자와
무관하게 "링크가 열리는가"를 직접 본다.

판정 규칙. 404·410 만 죽은 링크로 확정한다. 403(봇 차단)·429·5xx·타임아웃·연결 실패는
판정 불가로 통과시킨다 — 언론사가 자동 요청을 막는 경우가 흔해서 이것까지 실패로 보면 정상
인용이 탈락한다(같은 실측에서 메트로신문 403, 뉴스투나잇 연결 실패).
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor

import requests

# 마크다운 링크에서 URL 만 뽑는다. 닫는 괄호·인용부호는 URL 에 포함하지 않는다.
# 단 한 단계 균형 괄호는 URL 의 일부로 받는다 — 위키식 `Foo_(bar)` 를 `Foo_(bar` 로 자르면
# 없는 주소를 404 로 판정하고 링크를 벗길 때 `)` 가 본문에 남는다.
URL_RE = re.compile(r"""https?://(?:\([^\s()\]<>"'`]*\)|[^\s)\]<>"'`])+""")
# 인라인 링크 `[텍스트](목적지 "title")`, 이미지 `![alt](목적지)`, 자동링크 `<URL>`.
# 텍스트는 두 단계 중첩 대괄호(`[[단독] 제목]`, `[a [b [c]]]`)와 이스케이프를, 목적지는 `<URL>`
# 표기와 한 단계 균형 괄호를 받는다 — URL_RE 가 뽑는 주소와 같은 범위다. 이미지의 `!` 를 매치에
# 넣는 이유. 링크 부분만 벗기면 `!` 가 본문에 떠 `!차트` 로 나간다.
_PLAIN = r"[^\[\]\\]|\\."
_NEST1 = rf"\[(?:{_PLAIN})*\]"
_NEST2 = rf"\[(?:{_PLAIN}|{_NEST1})*\]"
_TEXT = rf"(?:{_PLAIN}|{_NEST2})*"
_DEST = r"<(?P<adest>[^<>\n]*)>|(?P<dest>(?:[^\s()\\]|\\.|\((?:[^\s()\\]|\\.)*\))+)"
_TITLE = r"""(?:\s+(?:"[^"]*"|'[^']*'|\([^()]*\)))?"""
_LINK_RE = re.compile(
    rf"(?P<bang>!)?\[(?P<text>{_TEXT})\]\(\s*(?:{_DEST}){_TITLE}\s*\)|<(?P<auto>https?://[^\s<>]*)>",
    re.S)
# 본문을 한 번 훑어 링크(목적지)와 맨 URL 을 등장 순서대로 찾는다.
_TOKEN_RE = re.compile(f"{_LINK_RE.pattern}|{URL_RE.pattern}", re.S)
# 강등 뒤 남은 맨 URL 을 찾을 때 쓴다. 코드 표기 안의 주소(이미 강등된 것)는 건너뛴다.
_SCAN_RE = re.compile(f"`[^`\n]*`|{_LINK_RE.pattern}|{URL_RE.pattern}", re.S)
# 링크 텍스트 안에서 렌더러(linkify·remark-gfm)가 자동링크로 만드는 표기 — 스킴 또는 `www.`.
# 이미 코드 표기인 부분은 그대로 둔다(두 번 감싸면 표기가 깨진다).
_TEXT_URL_RE = re.compile(r"""`[^`\n]*`|(?:https?://|www\.)[^\s<>"'`()\[\]]+""", re.I)
_TRAILING = ".,;:"
# 없는 문서라고 단정할 수 있는 상태코드만. 나머지는 판정 불가로 본다.
DEAD_CODES = frozenset({404, 410})
# HEAD 를 막는 서버가 있다 — 이때만 GET 으로 한 번 더 본다.
HEAD_REJECTED = frozenset({403, 405, 501})
VALID_MODES = ("off", "warn", "degrade", "strict")
TIMEOUT_SECONDS = float(os.environ.get("BRIEF_LINK_CHECK_TIMEOUT", "6"))
MAX_URLS = int(os.environ.get("BRIEF_LINK_CHECK_MAX", "40"))
WORKERS = int(os.environ.get("BRIEF_LINK_CHECK_WORKERS", "8"))
# 사람이 보는 브라우저처럼 보이게 한다. 기본 UA 로는 막는 언론사가 많아 403 판정 불가가 늘어난다.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")


def mode() -> str:
    """off(검사 안 함) / warn(로그만) / degrade(링크만 벗김) / strict(실패). 기본 degrade.

    2026-09-15 실측으로 기본값을 degrade 로 정했다. claude 경로 발행분에서 인용 42개 중
    7개가 404 였다(카테고리 7개 중 3개). 즉 열리지 않는 출처가 이미 매일 구독자에게 나가고
    있었다 — 기본이 warn(로그만)이면 그 상태가 그대로 유지된다.

    strict 는 쓰지 않는다. 그 비율이면 legal-ai·naver 가 매일 통째로 빈다. degrade 는 죽은
    링크만 벗겨 `매체 — 제목 (날짜)` 텍스트로 남기므로, 브리핑을 죽이지 않으면서 거짓 링크를
    내보내지 않는다.

    env 지시가 아니라 코드 기본값인 이유. content-worker 가 generic_brief 를 부를 때는
    brief 쪽 env 가 안 실려서, env 로 켜면 온디맨드 경로만 예전 동작으로 갈린다."""
    raw = (os.environ.get("BRIEF_LINK_CHECK") or "degrade").strip().lower()
    return raw if raw in VALID_MODES else "degrade"


def extract_urls(markdown: str, *, limit: int = MAX_URLS) -> list[str]:
    """본문에서 중복 없는 URL 목록. 등장 순서를 유지하고 limit 개까지만 본다.

    마크다운 링크는 목적지를 그대로 쓴다. strip_dead_links 가 같은 문자열로 대조하므로 여기서
    모양을 바꾸면 점검한 주소와 벗기는 링크가 어긋난다 — `…/Apple_Inc.` 를 `…/Apple_Inc` 로
    점검하면 살아 있는 링크를 벗기거나 죽은 링크를 놓친다. 문장 끝 구두점은 맨 URL 에서만 뗀다.

    링크 텍스트 안의 URL(`[https://a/x](https://b/y)`)도 점검한다. 링크가 하나의 토큰으로
    소비되므로 따로 뽑지 않으면 텍스트 쪽 주소는 아예 점검되지 않는다."""
    seen: dict[str, None] = {}

    def add(url: str) -> bool:
        if url not in seen:
            seen[url] = None
        return len(seen) >= limit

    for m in _TOKEN_RE.finditer(markdown or ""):
        if m.group(0)[0] in "![<":
            url = _link_url(m)
            if url.startswith(("http://", "https://")) and add(url):
                break
            if any(add(t.group(0).rstrip(_TRAILING)) for t in URL_RE.finditer(m.group("text") or "")):
                break
        elif add(m.group(0).rstrip(_TRAILING)):   # 문장 끝 구두점이 붙어 오는 경우
            break
    return list(seen)


def check_url(url: str, *, timeout: float = TIMEOUT_SECONDS) -> int | None:
    """상태코드. 네트워크 문제로 못 구하면 None(판정 불가)."""
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True, headers=headers)
        if resp.status_code in HEAD_REJECTED:
            resp = requests.get(url, timeout=timeout, allow_redirects=True,
                                headers=headers, stream=True)
            resp.close()
        return resp.status_code
    except requests.RequestException:
        return None
    except Exception:   # noqa: BLE001
        # 모델이 쓴 URL 은 호스트가 깨져 있을 수 있다('news..naver.com', 63자 넘는 레이블).
        # urllib3 버전에 따라 LocationParseError(ValueError) 가 requests 로 감싸지지 않고 새어 나와
        # pool.map 에서 generate 전체를 exit 1 로 죽였다 — 점검 하나로 발행을 막지 않는다(판정 불가).
        return None


def dead_links(markdown: str, *, timeout: float = TIMEOUT_SECONDS,
               workers: int = WORKERS, limit: int = MAX_URLS) -> list[tuple[str, int]]:
    """(죽은 링크, 상태코드) 목록. 404·410 만 담는다."""
    urls = extract_urls(markdown, limit=limit)
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(urls)))) as pool:
        codes = list(pool.map(lambda u: check_url(u, timeout=timeout), urls))
    return [(u, c) for u, c in zip(urls, codes) if c in DEAD_CODES]


def _link_url(m: re.Match[str]) -> str:
    """_LINK_RE 매치의 목적지(`<URL>` 표기면 괄호 안, 자동링크면 그 URL)."""
    return m.group("adest") or m.group("dest") or m.group("auto") or ""


def _bare(s: str) -> str:
    """스킴·`www.`·끝 `/` 를 뗀 주소."""
    return re.sub(r"^(?:https?://)?(?:www\.)?", "", s.strip(), flags=re.I).rstrip("/")


def _same_address(text: str, url: str) -> bool:
    """텍스트가 스킴·`www.`·끝 `/`·대소문자만 다른 같은 주소인가 — 렌더러는 이런 텍스트도 링크로 만든다."""
    return _bare(text).lower() == _bare(url).lower()


def _code(s: str) -> str:
    """코드 표기로 감싸 보이되 눌리지 않게 한다. 문장 끝 구두점은 밖에 둔다."""
    core = s.rstrip(_TRAILING)
    return f"`{core}`{s[len(core):]}" if core else s


def _neutralize(text: str, url: str) -> str:
    """강등한 링크 텍스트에 남은 주소 표기를 코드로 바꾼다.

    링크가 살아 있을 땐 텍스트 안 주소가 링크의 일부라 따로 눌리지 않지만, 링크를 벗기면
    맨 텍스트가 되어 렌더러가 다시 링크로 만든다 — `[링크 www.a.com/x 참고](https://a.com/x)`
    가 404 면 `www.a.com/x` 가 그대로 눌린다. 스킴·`www.` 표기는 모두, 스킴 없는 표기는 죽은
    목적지와 같은 주소일 때만 바꾼다(메일 linkify 는 `a.com/x` 도 링크로 만든다)."""
    out = _TEXT_URL_RE.sub(lambda m: m.group(0) if m.group(0)[0] == "`" else _code(m.group(0)), text)
    addr = _bare(url)
    if addr:
        out = re.sub(rf"(?<![\w`/.@-]){re.escape(addr)}/?(?![\w`/])",
                     lambda m: f"`{m.group(0)}`", out, flags=re.I)
    return out


def strip_dead_links(markdown: str, dead_urls: list[str]) -> tuple[str, int]:
    """죽은 링크를 링크 표기만 벗겨 텍스트로 남긴다. (새 본문, 벗긴 개수).

    `[법률신문 — 제목 (2026.9.15)](https://...404)` → `법률신문 — 제목 (2026.9.15)`
    출처 자체를 지우면 근거 없는 주장이 되고, 링크를 두면 열리지 않는 약속이 된다. 매체·제목·
    날짜는 남겨 독자가 직접 검색할 수 있게 하는 편이 둘 다보다 낫다. 이미지 `![alt](…)` 는
    alt 텍스트만 남긴다.

    목적지가 죽은 주소와 정확히 같을 때만 벗긴다. 접두 일치로 보면 `…/a` 가 죽었을 때
    살아 있는 `…/a?b=1` 까지 벗겨진다.

    벗긴 텍스트에 주소 표기가 남으면(`[URL](URL)`, `<URL>`, 스킴·www·대소문자만 다른 표기,
    텍스트 중간의 URL) 메일(linkify)·포털(remark-gfm)이 다시 링크로 만든다. 그 주소는 코드
    표기로 바꿔 보이되 눌리지 않게 한다.

    마크다운 링크가 아닌 맨 URL 도 죽었으면 코드 표기로 바꾼다 — 지우지 않으므로 문맥은
    그대로다. 링크 정규식이 못 잡는 표기(세 단계 넘는 중첩 대괄호 등)에서 죽은 링크가 그대로
    나가지 않게 하는 마지막 그물이기도 하다."""
    dead = set(dead_urls)
    if not dead:
        return markdown, 0
    replaced = 0

    def _degrade(m: re.Match[str]) -> str:
        nonlocal replaced
        url = _link_url(m)
        if url not in dead:
            return m.group(0)
        replaced += 1
        text = m.group("text")
        if text is None:              # 자동링크는 텍스트가 곧 URL
            return f"`{url}`"
        if _same_address(text, url):
            return f"`{text.strip()}`"
        return _neutralize(text, url)

    def _bare_url(m: re.Match[str]) -> str:
        nonlocal replaced
        s = m.group(0)
        if s[0] in "`![<" or s.rstrip(_TRAILING) not in dead:
            return s
        replaced += 1
        return _code(s)

    out = _LINK_RE.sub(_degrade, markdown)
    return _SCAN_RE.sub(_bare_url, out), replaced
