# 이미 업로드된 영상 설명란에 구독 CTA를 소급 추가하는 일회성 CLI. 기본 DRY-RUN, --apply 로만 실제 수정.
import os
import sys
import time
from pathlib import Path

from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.youtube_upload import get_snippet, update_description, UploadError
from popory_content.video_prompt import append_subscribe_cta, CHANNEL_SUB_URL
from popory_content.log import append_log

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
AREA = "content-worker"
WRITE_DELAY_SECONDS = 0.3   # videos.update 사이 간격(레이트리밋 완화)


def _client() -> PortalClient:
    key_file = os.environ["POPORY_CONTENT_KEY_FILE"]
    base = os.environ["POPORY_PORTAL_API_BASE"]
    material = KeyMaterial.load(Path(key_file))
    return PortalClient(
        base_url=base,
        token_provider=lambda: sign_for_portal(material, area=AREA, ttl_seconds=300),
    )


def run(apply: bool) -> int:
    mode = "apply" if apply else "dry-run"
    try:
        client = _client()
    except (KeyError, PortalError) as e:
        append_log(LOGS_DIR, {"cli": "backfill_descriptions", "status": "init_fail", "error": str(e)})
        return 2
    try:
        data = client.get("/api/content/youtube/comment-backfill")
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "backfill_descriptions", "status": "fetch_fail", "error": str(e)})
        return 3
    items = data.get("items", [])
    updated = skipped = failed = 0
    quota_hit = False
    for it in items:
        try:
            snippet = get_snippet(it["access_token"], it["video_id"])
            old = snippet.get("description", "")
            if CHANNEL_SUB_URL in old:      # 이미 CTA 있음 → 멱등 스킵
                skipped += 1
                continue
            new = append_subscribe_cta(old)
            if new == old:
                skipped += 1
                continue
            if apply:
                update_description(it["access_token"], it["video_id"], snippet, new)
                time.sleep(WRITE_DELAY_SECONDS)
            updated += 1
        except (UploadError, KeyError) as e:  # 개별 실패는 건너뛰고 계속
            failed += 1
            if "quota" in str(e).lower():
                quota_hit = True
            append_log(LOGS_DIR, {"cli": "backfill_descriptions", "status": "item_fail",
                                  "video": it.get("video_id"), "error": str(e)[:200]})
    append_log(LOGS_DIR, {"cli": "backfill_descriptions", "status": "done", "mode": mode,
                          "updated": updated, "skipped": skipped, "failed": failed,
                          "total": len(items), "quota_hit": quota_hit})
    print(f"[{mode}] total={len(items)} updated={updated} skipped={skipped} failed={failed} quota_hit={quota_hit}")
    return 4 if quota_hit else 0   # 4=쿼터로 미완(재시도 필요), 0=완료(남은 실패는 삭제된 영상뿐)


if __name__ == "__main__":
    sys.exit(run("--apply" in sys.argv))
