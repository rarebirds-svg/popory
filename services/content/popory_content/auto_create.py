# 매일 recommend 대기열에서 주제를 골라 1주제·3플랫폼 묶음 잡을 큐잉하는 스케줄러.
import os
import sys
from pathlib import Path

from popory_content.generate import GenerateError
from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.log import append_log
from popory_content.recommend_weekly import generate_items

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


def _pending(client: PortalClient, owner_sub: str) -> list[dict]:
    """대기 중인 추천 1건을 조회한다."""
    data = client.get(f"/api/content/recommendations/service?owner_sub={owner_sub}&limit=1")
    return data.get("recommendations", [])


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
    rec = recs[0]
    try:
        out = client.post("/api/content/topics/service-create", json={
            "owner_sub": owner_sub,
            "topic": rec["title"],
            "author": rec.get("author"),
            "category_slug": "book-review",
            "platforms": [{"platform": "naver-blog"}, {"platform": "youtube"}, {"platform": "shorts"}, {"platform": "youtube-post"}],
            "recommendation_id": rec["id"],
        })
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "create_fail", "topic": rec["title"], "error": str(e)})
        return 0
    append_log(LOGS_DIR, {"cli": "auto_create", "status": "ok", "topic": rec["title"], "topic_id": out.get("topic_id"), "job_ids": out.get("job_ids")})
    return 0


if __name__ == "__main__":
    sys.exit(run())
