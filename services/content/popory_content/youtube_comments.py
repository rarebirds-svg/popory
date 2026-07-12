# 유튜브 최상위 댓글을 조회하고 답글 대상(우리가 아직 답하지 않은 남의 댓글)만 골라낸다.
import requests

from popory_content.youtube_upload import COMMENT_LIST_URL, UploadError


class VideoUnavailable(UploadError):
    """삭제(404)·비공개(403) 영상. 재시도해도 소용없으므로 실패가 아니라 대상 제외로 센다."""


def list_comment_threads(access_token: str, video_id: str) -> list[dict]:
    """영상의 최상위 댓글 스레드(답글 포함)를 최대 100건 조회. 실패 시 UploadError."""
    resp = requests.get(
        COMMENT_LIST_URL,
        params={
            "part": "snippet,replies",
            "videoId": video_id,
            "maxResults": 100,
            "textFormat": "plainText",
            "order": "time",
        },
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if resp.status_code in (403, 404):
        raise VideoUnavailable(f"commentThreads {resp.status_code}: {resp.text[:200]}")
    if resp.status_code != 200:
        # 조회 실패를 "댓글 없음"으로 오해하면 안 되므로 예외로 올린다.
        raise UploadError(f"commentThreads {resp.status_code}: {resp.text[:200]}")
    return resp.json().get("items", [])


def _author_channel(snippet: dict) -> str | None:
    return snippet.get("authorChannelId", {}).get("value")


def collect_new_comments(items: list[dict], channel_id: str) -> list[dict]:
    """우리 채널이 쓴 댓글과 이미 우리 답글이 달린 댓글을 제외한 나머지를 정규화해 반환."""
    out: list[dict] = []
    for it in items:
        top = it.get("snippet", {}).get("topLevelComment", {})
        snip = top.get("snippet", {})
        if _author_channel(snip) == channel_id:
            continue
        replies = it.get("replies", {}).get("comments", [])
        if any(_author_channel(r.get("snippet", {})) == channel_id for r in replies):
            continue
        cid = top.get("id")
        text = snip.get("textOriginal", "")
        if not cid or not text:
            continue
        out.append({
            "comment_id": cid,
            "author_name": snip.get("authorDisplayName"),
            "text": text,
            "published_at": snip.get("publishedAt"),
        })
    return out
