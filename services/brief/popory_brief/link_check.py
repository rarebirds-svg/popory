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
URL_RE = re.compile(r"""https?://[^\s)\]<>"'`]+""")
# 없는 문서라고 단정할 수 있는 상태코드만. 나머지는 판정 불가로 본다.
DEAD_CODES = frozenset({404, 410})
# HEAD 를 막는 서버가 있다 — 이때만 GET 으로 한 번 더 본다.
HEAD_REJECTED = frozenset({403, 405, 501})
VALID_MODES = ("off", "warn", "strict")
TIMEOUT_SECONDS = float(os.environ.get("BRIEF_LINK_CHECK_TIMEOUT", "6"))
MAX_URLS = int(os.environ.get("BRIEF_LINK_CHECK_MAX", "40"))
WORKERS = int(os.environ.get("BRIEF_LINK_CHECK_WORKERS", "8"))
# 사람이 보는 브라우저처럼 보이게 한다. 기본 UA 로는 막는 언론사가 많아 403 판정 불가가 늘어난다.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")


def mode() -> str:
    """off(검사 안 함) / warn(로그만) / strict(죽은 링크면 실패). 기본 warn.

    기본을 warn 으로 두는 이유. 켜는 순간 strict 였다면 오판 한 건이 그날 브리핑을 통째로
    날린다. 먼저 며칠 빈도를 보고 사람이 strict 로 올리는 순서가 맞다."""
    raw = (os.environ.get("BRIEF_LINK_CHECK") or "warn").strip().lower()
    return raw if raw in VALID_MODES else "warn"


def extract_urls(markdown: str, *, limit: int = MAX_URLS) -> list[str]:
    """본문에서 중복 없는 URL 목록. 등장 순서를 유지하고 limit 개까지만 본다."""
    seen: dict[str, None] = {}
    for m in URL_RE.finditer(markdown or ""):
        url = m.group(0).rstrip(".,;:")   # 문장 끝 구두점이 붙어 오는 경우
        if url not in seen:
            seen[url] = None
        if len(seen) >= limit:
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


def dead_links(markdown: str, *, timeout: float = TIMEOUT_SECONDS,
               workers: int = WORKERS, limit: int = MAX_URLS) -> list[tuple[str, int]]:
    """(죽은 링크, 상태코드) 목록. 404·410 만 담는다."""
    urls = extract_urls(markdown, limit=limit)
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(urls)))) as pool:
        codes = list(pool.map(lambda u: check_url(u, timeout=timeout), urls))
    return [(u, c) for u, c in zip(urls, codes) if c in DEAD_CODES]
