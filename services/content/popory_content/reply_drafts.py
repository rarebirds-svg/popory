# 유튜브 신규 댓글을 수집해 답글 초안을 만들고 포털에 승인 대기로 올리는 일일 CLI.
import os
import sys
from pathlib import Path

from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.youtube_comments import list_comment_threads, collect_new_comments, VideoUnavailable
from popory_content.generate import generate_reply
from popory_content.telegram import send_telegram, TelegramError
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


def _notify(text: str) -> None:
    """대기 건수를 텔레그램으로 알린다. 토큰이 없으면 조용히 넘어간다."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        send_telegram(token, chat_id, text)
    except TelegramError as e:
        append_log(LOGS_DIR, {"cli": "reply_drafts", "status": "notify_fail", "error": str(e)[:200]})


def run() -> int:
    try:
        client = _client()
    except (KeyError, PortalError) as e:
        append_log(LOGS_DIR, {"cli": "reply_drafts", "status": "init_fail", "error": str(e)})
        return 2
    try:
        data = client.get("/api/content/youtube/comment-scan")
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "reply_drafts", "status": "fetch_fail", "error": str(e)})
        return 3

    drafted = skipped = failed = unavailable = 0
    for it in data.get("items", []):
        video_id = it["video_id"]
        try:
            threads = list_comment_threads(it["access_token"], video_id)
            fresh = collect_new_comments(threads, it["channel_id"])
        except VideoUnavailable as e:
            # 삭제·비공개 영상. 매일 반복되는 정상 상태이므로 failed 로 세지 않는다.
            unavailable += 1
            append_log(LOGS_DIR, {"cli": "reply_drafts", "status": "video_unavailable", "video": video_id, "error": str(e)[:200]})
            continue
        except Exception as e:  # noqa: BLE001 — 한 영상 실패는 건너뛰고 계속.
            failed += 1
            append_log(LOGS_DIR, {"cli": "reply_drafts", "status": "item_fail", "video": video_id, "error": str(e)[:200]})
            continue
        if not fresh:
            continue
        payload = {"items": [{**c, "category_id": it["category_id"], "video_id": video_id} for c in fresh]}
        try:
            new_rows = client.post("/api/content/youtube/comments/ingest", json=payload).get("items", [])
        except PortalError as e:
            failed += 1
            append_log(LOGS_DIR, {"cli": "reply_drafts", "status": "ingest_fail", "video": video_id, "error": str(e)[:200]})
            continue
        for row in new_rows:
            try:
                got = generate_reply(comment_text=row["text"], topic=it["topic"], job_id=row["id"])
                body = {"skip": True} if got["skip"] else {"draft": got["reply"]}
                client.patch(f"/api/content/youtube/comments/{row['id']}/draft", json=body)
                if got["skip"]:
                    skipped += 1
                else:
                    drafted += 1
            except Exception as e:  # noqa: BLE001 — 댓글 하나 실패는 초안 없는 pending 으로 남긴다.
                failed += 1
                append_log(LOGS_DIR, {"cli": "reply_drafts", "status": "draft_fail", "comment": row.get("id"), "error": str(e)[:200]})

    append_log(LOGS_DIR, {"cli": "reply_drafts", "status": "done", "drafted": drafted, "skipped": skipped, "failed": failed, "unavailable": unavailable})
    if drafted:
        _notify(f"유튜브 답글 초안 {drafted}건 대기 중입니다. https://poporyfamily.com/content/comments")
    return 0


if __name__ == "__main__":
    sys.exit(run())
