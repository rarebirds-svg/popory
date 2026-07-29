# YouTube Data API resumable 업로드(access_token + MP4 바이트 → video id). 영상은 비공개.
import json
import requests

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
CAPTION_URL = "https://www.googleapis.com/upload/youtube/v3/captions?part=snippet&uploadType=multipart"
THUMBNAIL_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
COMMENT_URL = "https://www.googleapis.com/youtube/v3/commentThreads?part=snippet"
COMMENT_LIST_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
_STORE_MARKERS = ("aladin.co.kr", "kyobobook.co.kr", "yes24.com", "ypbooks.co.kr")


class UploadError(Exception):
    """업로드 실패."""


def get_snippet(access_token: str, video_id: str) -> dict:
    """영상의 현재 snippet(제목·설명·categoryId·태그) 반환. 실패 시 UploadError."""
    resp = requests.get(
        VIDEOS_URL, params={"part": "snippet", "id": video_id},
        headers={"Authorization": f"Bearer {access_token}"}, timeout=30,
    )
    if resp.status_code != 200:
        raise UploadError(f"videos.list {resp.status_code}: {resp.text[:200]}")
    items = resp.json().get("items", [])
    if not items:
        raise UploadError(f"video {video_id} not found")
    return items[0]["snippet"]


def update_description(access_token: str, video_id: str, snippet: dict, description: str) -> None:
    """description만 교체해 videos.update. snippet PUT은 전체 교체라 title·categoryId·태그는 보존한다."""
    keep = {k: snippet[k] for k in ("title", "categoryId", "tags", "defaultLanguage", "defaultAudioLanguage") if k in snippet}
    resp = requests.put(
        VIDEOS_URL, params={"part": "snippet"},
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"id": video_id, "snippet": {**keep, "description": description}}, timeout=30,
    )
    if resp.status_code != 200:
        raise UploadError(f"videos.update {resp.status_code}: {resp.text[:200]}")


def commentable_video_ids(access_token: str, video_ids: list[str]) -> set[str]:
    """댓글을 달 수 있는 영상 id만 반환. 비공개(유튜브가 댓글을 끔)와 삭제된 영상은 뺀다.

    조회가 실패한 배치는 판단을 보류하고 그대로 통과시킨다 — 일시적 API 오류로
    멀쩡한 대상을 영구히 빠뜨리는 쪽이 더 나쁘다.
    """
    out: set[str] = set()
    for i in range(0, len(video_ids), 50):  # videos.list id 파라미터 상한
        batch = video_ids[i:i + 50]
        resp = requests.get(
            VIDEOS_URL, params={"part": "status", "id": ",".join(batch)},
            headers={"Authorization": f"Bearer {access_token}"}, timeout=30,
        )
        if resp.status_code != 200:
            out.update(batch)
            continue
        for it in resp.json().get("items", []):
            if it.get("status", {}).get("privacyStatus") != "private":
                out.add(it["id"])
    return out


def comment_exists(access_token: str, video_id: str) -> bool:
    """영상에 서점 링크 댓글이 이미 있으면 True. 조회 실패면 False."""
    resp = requests.get(
        COMMENT_LIST_URL,
        params={"part": "snippet", "videoId": video_id, "maxResults": 100, "textFormat": "plainText"},
        headers={"Authorization": f"Bearer {access_token}"}, timeout=30,
    )
    if resp.status_code != 200:
        return False
    for it in resp.json().get("items", []):
        text = it.get("snippet", {}).get("topLevelComment", {}).get("snippet", {}).get("textOriginal", "")
        if any(m in text for m in _STORE_MARKERS):
            return True
    return False


def upload(access_token: str, mp4_bytes: bytes, title: str, description: str, tags: list[str], privacy: str = "private") -> str:
    init = requests.post(
        UPLOAD_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(len(mp4_bytes)),
        },
        json={"snippet": {"title": title[:100], "description": description, "tags": tags}, "status": {"privacyStatus": privacy}},
        timeout=60,
    )
    if init.status_code not in (200, 201):
        raise UploadError(f"init {init.status_code}: {init.text[:200]}")
    location = init.headers.get("Location")
    if not location:
        raise UploadError("upload Location 없음")
    put = requests.put(location, headers={"Authorization": f"Bearer {access_token}", "Content-Type": "video/mp4"}, data=mp4_bytes, timeout=600)
    if put.status_code not in (200, 201):
        raise UploadError(f"put {put.status_code}: {put.text[:200]}")
    vid = put.json().get("id")
    if not vid:
        raise UploadError("video id 없음")
    return vid


def set_thumbnail(access_token: str, video_id: str, jpg_bytes: bytes) -> None:
    """업로드된 영상에 커스텀 썸네일 설정. 채널 미인증 등 실패 시 UploadError."""
    resp = requests.post(
        f"{THUMBNAIL_URL}?videoId={video_id}",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "image/jpeg"},
        data=jpg_bytes, timeout=60,
    )
    if resp.status_code not in (200, 201):
        raise UploadError(f"thumbnail {resp.status_code}: {resp.text[:200]}")


def post_comment(access_token: str, video_id: str, text: str) -> None:
    """영상에 최상위 댓글 1개 작성. 실패 시 UploadError."""
    resp = requests.post(
        COMMENT_URL,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text}}}},
        timeout=60,
    )
    if resp.status_code not in (200, 201):
        raise UploadError(f"comment {resp.status_code}: {resp.text[:200]}")


def upload_caption(access_token: str, video_id: str, language: str, name: str, srt_bytes: bytes) -> None:
    """captions.insert(multipart/related)로 자막 트랙 1개 업로드. 실패 시 UploadError."""
    meta = {"snippet": {"videoId": video_id, "language": language, "name": name, "isDraft": False}}
    boundary = "popory_caption_boundary"
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(meta)}\r\n"
        f"--{boundary}\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + srt_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    resp = requests.post(
        CAPTION_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        data=body,
        timeout=60,
    )
    if resp.status_code not in (200, 201):
        raise UploadError(f"caption {resp.status_code}: {resp.text[:200]}")
