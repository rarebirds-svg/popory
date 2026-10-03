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


# 마크다운 링크 `[텍스트](URL)`. URL 뒤에 공백·title 이 붙는 변형까지 받는다.
def _link_pattern(url: str) -> re.Pattern[str]:
    return re.compile(r"\[([^\]]*)\]\(\s*" + re.escape(url) + r"[^)]*\)")


def strip_dead_links(markdown: str, dead_urls: list[str]) -> tuple[str, int]:
    """죽은 링크를 링크 표기만 벗겨 텍스트로 남긴다. (새 본문, 벗긴 개수).

    `[법률신문 — 제목 (2026.9.15)](https://...404)` → `법률신문 — 제목 (2026.9.15)`
    출처 자체를 지우면 근거 없는 주장이 되고, 링크를 두면 열리지 않는 약속이 된다. 매체·제목·
    날짜는 남겨 독자가 직접 검색할 수 있게 하는 편이 둘 다보다 낫다.

    마크다운 링크가 아닌 맨 URL 은 손대지 않는다 — 문장 구조를 모르는 채로 지우면 문맥이
    깨진다. 그런 경우는 로그의 dead 목록으로 남아 사람이 판단한다."""
    out = markdown
    replaced = 0
    for url in dead_urls:
        out, n = _link_pattern(url).subn(lambda m: m.group(1), out)
        replaced += n
    return out, replaced
