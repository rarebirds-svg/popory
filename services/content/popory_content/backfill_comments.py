# 이미 업로드된 책 리뷰 영상에 서점 구매 링크 댓글을 소급 작성하는 일회성 CLI.
import os
import sys
from pathlib import Path

from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.bookstore_links import build_purchase_comment_validated
from popory_content.youtube_upload import post_comment, comment_exists, commentable_video_ids
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


def _parse_topic(topic: str) -> tuple[str, str | None]:
    """제목 - 저자 형식이면 분리, 아니면 제목만."""
    if " - " in topic:
        title, author = topic.split(" - ", 1)
        return title.strip(), author.strip()
    return topic.strip(), None


def _drop_uncommentable(items: list[dict]) -> list[dict]:
    """비공개·삭제된 영상을 대상에서 뺀다. 댓글 API가 영구 실패하는 건이라 매일 재시도할 이유가 없다."""
    by_token: dict[str, list[str]] = {}
    for it in items:
        by_token.setdefault(it["access_token"], []).append(it["video_id"])
    commentable: set[str] = set()
    for token, vids in by_token.items():
        commentable |= commentable_video_ids(token, vids)
    kept = [it for it in items if it["video_id"] in commentable]
    dropped = [it["video_id"] for it in items if it["video_id"] not in commentable]
    if dropped:
        append_log(LOGS_DIR, {"cli": "backfill_comments", "status": "uncommentable",
                              "count": len(dropped), "videos": dropped})
    return kept


def run() -> int:
    try:
        client = _client()
    except (KeyError, PortalError) as e:
        append_log(LOGS_DIR, {"cli": "backfill_comments", "status": "init_fail", "error": str(e)})
        return 2
    try:
        data = client.get("/api/content/youtube/comment-backfill")
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "backfill_comments", "status": "fetch_fail", "error": str(e)})
        return 3
    items = _drop_uncommentable(data.get("items", []))
    posted = skipped = failed = 0
    for it in items:
        try:
            if comment_exists(it["access_token"], it["video_id"]):
                skipped += 1
                continue
            title, author = _parse_topic(it["topic"])
            text = build_purchase_comment_validated(title, author)
            if not text:
                skipped += 1
                continue
            post_comment(it["access_token"], it["video_id"], text)
            posted += 1
        except Exception as e:  # noqa: BLE001 — 개별 실패는 건너뛰고 계속.
            failed += 1
            append_log(LOGS_DIR, {"cli": "backfill_comments", "status": "item_fail", "video": it.get("video_id"), "error": str(e)[:200]})
    append_log(LOGS_DIR, {"cli": "backfill_comments", "status": "done", "posted": posted, "skipped": skipped, "failed": failed})
    return 0


if __name__ == "__main__":
    sys.exit(run())
