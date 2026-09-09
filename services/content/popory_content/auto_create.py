# 매일 recommend 대기열에서 주제를 골라 1주제·3플랫폼 묶음 잡을 큐잉하는 스케줄러.
import os
import sys
from pathlib import Path

from popory_content.generate import GenerateError
from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.log import append_log
from popory_content.recommend_weekly import generate_items
from popory_content.names import normalize_names

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
AREA = "content-worker"


def _client() -> PortalClient:
    key_file = os.environ["POPORY_CONTENT_KEY_FILE"]
    base = os.environ["POPORY_PORTAL_API_BASE"]
    material = KeyMaterial.load(Path(key_file))
    return PortalClient(
        base_url=base,
        token_provider=lambda: sign_for_portal(material, area=AREA, ttl_seconds=300),
    )


# 대기열에서 한 번에 훑어볼 추천 건수. 1건만 가져오면 맨 앞이 저자 없는 행일 때
# 저자 없는 제목으로 굳어버려서, 앞쪽 몇 건 중 저자가 있는 행을 고를 여지를 둔다.
PENDING_SCAN = int(os.environ.get("POPORY_PENDING_SCAN", "20"))


def _pending(client: PortalClient, owner_sub: str) -> list[dict]:
    """대기 중인 추천을 오래된 순으로 조회한다(포털의 [추천 컨텐츠] 목록 그대로)."""
    data = client.get(f"/api/content/recommendations/service?owner_sub={owner_sub}&limit={PENDING_SCAN}")
    return data.get("recommendations", [])


def choose(recs: list[dict]) -> dict:
    """대기열에서 오늘 만들 1건을 고른다. 순서는 오래된 순을 지키되, 저자가 있는 행을
    먼저 집는다 — 제목에 저자를 붙이는 게 목적이라 저자 없는 행을 굳이 먼저 소진할 이유가 없다.
    전부 저자가 없으면 원래대로 맨 앞을 쓴다."""
    for r in recs:
        if (r.get("author") or "").strip():
            return r
    return recs[0]


def _recommend_now(client: PortalClient, owner_sub: str) -> dict:
    """주간 잡과 같은 프롬프트·중복 방지로 즉석 추천을 만들어 대기열에 넣는다.
    known-titles 조회가 실패하면 중복 추천 위험이 있으므로 폴백 자체를 실패시킨다."""
    known = client.get(f"/api/content/recommendations/known-titles?owner_sub={owner_sub}").get("titles", [])
    items = generate_items(known)
    return client.post("/api/content/recommendations/service-bulk", json={
        "owner_sub": owner_sub,
        "items": items,
        "category_slug": "book-review",
    })


def topic_with_author(title: str, author: str | None) -> str:
    """주제 제목에 저자를 붙여 '제목 - 저자' 로 만든다.

    레포 전체가 이 표기를 전제한다 — backfill_comments._parse_topic 이 " - " 로 저자를
    떼어 구매 링크 댓글을 만들고, topics 라우트도 같은 방식으로 추천 행을 매칭한다.
    저자 없이 제목만 남으면 목록에서 어떤 책인지 구분이 안 되고(동명 제목),
    구매 링크 검색어도 저자 없이 나가 정확도가 떨어진다.
    이미 그 저자가 붙어 있으면 그대로 둔다(중복 방지)."""
    t = (title or "").strip()
    a = (author or "").strip()
    if not a or t.endswith(f" - {a}"):
        return t
    return f"{t} - {a}"


def run() -> int:
    owner_sub = os.environ.get("POPORY_RECOMMEND_OWNER")
    if not owner_sub:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "no_owner"})
        return 0
    try:
        client = _client()
    except (KeyError, PortalError) as e:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "init_fail", "error": str(e)})
        return 2

    try:
        recs = _pending(client, owner_sub)
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "fetch_fail", "error": str(e)})
        return 3

    # 대기열이 비면 그 자리에서 추천을 만들어 큐에 넣고, 다시 조회해 기존 경로로 진행한다
    # (used 표시·중복 처리 같은 상태 전이를 그대로 태우기 위함).
    if not recs:
        try:
            out = _recommend_now(client, owner_sub)
            append_log(LOGS_DIR, {"cli": "auto_create", "status": "fallback_recommended",
                                  "added": out.get("added"), "skipped": out.get("skipped")})
            recs = _pending(client, owner_sub)
        except (PortalError, GenerateError) as e:
            append_log(LOGS_DIR, {"cli": "auto_create", "status": "fallback_fail", "error": str(e)[:300]})
            return 4
        if not recs:
            append_log(LOGS_DIR, {"cli": "auto_create", "status": "fallback_fail",
                                  "error": "추천 생성 후에도 대기열이 비어 있습니다 (전량 중복)"})
            return 4
    rec = choose(recs)
    # 이 시점의 추천은 포털에 이미 저장된 행이라 claude CLI 를 다시 거치지 않는다. 교정
    # 이전에 쌓인 표기가 그대로 주제·저자로 굳는 걸 막으려 등록 직전에 한 번 더 통과시킨다.
    title = normalize_names(rec["title"])
    author = normalize_names(rec.get("author") or "") or None
    topic = topic_with_author(title, author)
    try:
        out = client.post("/api/content/topics/service-create", json={
            "owner_sub": owner_sub,
            "topic": topic,
            "author": author,
            "category_slug": "book-review",
            "platforms": [{"platform": "naver-blog"}, {"platform": "youtube"}, {"platform": "shorts"}, {"platform": "youtube-post"}],
            "recommendation_id": rec["id"],
        })
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "create_fail", "topic": topic, "error": str(e)})
        return 0
    # 어떤 추천에서 골랐는지 남긴다 — 저자 누락은 추천 행 자체의 문제이므로 로그에서 바로 갈린다.
    append_log(LOGS_DIR, {"cli": "auto_create", "status": "ok", "topic": topic,
                          "recommendation_id": rec["id"], "author": author or "",
                          "topic_id": out.get("topic_id"), "job_ids": out.get("job_ids")})
    return 0


if __name__ == "__main__":
    sys.exit(run())
