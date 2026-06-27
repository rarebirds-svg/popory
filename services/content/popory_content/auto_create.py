# 매일 recommend 대기열에서 주제를 골라 영상·쇼츠 잡을 큐잉하는 스케줄러.
import os
import sys
from pathlib import Path

from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.log import append_log

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
AREA = "content-worker"


def select_assignments(recs: list[dict]) -> list[tuple[str, dict]]:
    """오래된 순 recs에서 youtube·shorts 배정. 1건이면 둘 다 같은 주제, 0건이면 빈 리스트."""
    if not recs:
        return []
    yt = recs[0]
    sh = recs[1] if len(recs) >= 2 else recs[0]
    return [("youtube", yt), ("shorts", sh)]


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
        data = client.get(f"/api/content/recommendations/service?owner_sub={owner_sub}&limit=2")
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "fetch_fail", "error": str(e)})
        return 3
    recs = data.get("recommendations", [])
    assignments = select_assignments(recs)
    if not assignments:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "skipped", "reason": "empty"})
        return 0

    created = []
    errors = 0
    for platform, rec in assignments:
        try:
            out = client.post("/api/content/jobs/service-create", json={
                "owner_sub": owner_sub,
                "topic": rec["title"],
                "platform": platform,
                "recommendation_id": rec["id"],
            })
            created.append({"platform": platform, "topic": rec["title"], "job_id": out.get("id")})
        except PortalError as e:
            errors += 1
            append_log(LOGS_DIR, {"cli": "auto_create", "status": "create_fail", "platform": platform, "topic": rec["title"], "error": str(e)})
    final_status = "partial" if errors else "ok"
    append_log(LOGS_DIR, {"cli": "auto_create", "status": final_status, "created": created})
    return 0


if __name__ == "__main__":
    sys.exit(run())
