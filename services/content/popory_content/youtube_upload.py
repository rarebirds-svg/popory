# YouTube Data API resumable 업로드(access_token + MP4 바이트 → video id). 영상은 비공개.
import requests

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"


class UploadError(Exception):
    """업로드 실패."""


def upload(access_token: str, mp4_bytes: bytes, title: str, description: str, tags: list[str]) -> str:
    init = requests.post(
        UPLOAD_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(len(mp4_bytes)),
        },
        json={"snippet": {"title": title[:100], "description": description, "tags": tags}, "status": {"privacyStatus": "private"}},
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
