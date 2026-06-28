# 매일 recommend 대기열에서 주제를 골라 1주제·3플랫폼 묶음 잡을 큐잉하는 스케줄러.
import os
import sys
from pathlib import Path

from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.log import append_log

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
        data = client.get(f"/api/content/recommendations/service?owner_sub={owner_sub}&limit=1")
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "fetch_fail", "error": str(e)})
        return 3

    recs = data.get("recommendations", [])
    if not recs:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "skipped", "reason": "empty"})
        return 0
    rec = recs[0]
    try:
        out = client.post("/api/content/topics/service-create", json={
            "owner_sub": owner_sub,
            "topic": rec["title"],
            "author": rec.get("author"),
            "category_slug": "book-review",
            "platforms": [{"platform": "naver-blog"}, {"platform": "youtube"}, {"platform": "shorts"}],
            "recommendation_id": rec["id"],
        })
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "create_fail", "topic": rec["title"], "error": str(e)})
        return 0
    append_log(LOGS_DIR, {"cli": "auto_create", "status": "ok", "topic": rec["title"], "topic_id": out.get("topic_id"), "job_ids": out.get("job_ids")})
    return 0


if __name__ == "__main__":
    sys.exit(run())
