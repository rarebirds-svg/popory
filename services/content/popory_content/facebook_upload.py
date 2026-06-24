# Facebook 페이지 Reels를 Graph API 3단계 resumable 업로드로 게시.
import time
import requests


GRAPH_BASE = "https://graph.facebook.com/v23.0"
RUPLOAD_BASE = "https://rupload.facebook.com/video-upload/v23.0"
MAX_POLL = 20


class FacebookUploadError(Exception):
    """Facebook Graph API 업로드 실패."""


def _wait_published(video_id: str, access_token: str) -> None:
    """릴스가 게시 완료(또는 처리 완료)될 때까지 폴링. 타임아웃은 비차단(서버에서 계속 처리)."""
    for _ in range(MAX_POLL):
        resp = requests.get(
            f"{GRAPH_BASE}/{video_id}",
            params={"fields": "status", "access_token": access_token},
            timeout=15,
        )
        if resp.ok:
            status = resp.json().get("status", {})
            publishing = status.get("publishing_phase", {})
            if publishing.get("status") == "complete" or status.get("video_status") == "ready":
                return
            if publishing.get("status") == "error" or status.get("processing_phase", {}).get("status") == "error":
                raise FacebookUploadError(f"릴스 처리 오류: {status}")
        time.sleep(5)
    # 타임아웃: 페이스북이 비동기로 게시를 마저 처리하므로 실패로 보지 않는다.


def upload_reels(page_id: str, access_token: str, video_url: str, description: str) -> str:
    """페이지 릴스 게시. 게시된 video_id 반환."""
    # 1. start — 업로드 세션 생성.
    start = requests.post(
        f"{GRAPH_BASE}/{page_id}/video_reels",
        params={"upload_phase": "start", "access_token": access_token},
        timeout=30,
    )
    if not start.ok:
        raise FacebookUploadError(f"start {start.status_code}: {start.text[:300]}")
    video_id = start.json().get("video_id")
    if not video_id:
        raise FacebookUploadError(f"start 응답에 video_id 없음: {start.text[:300]}")

    # 2. upload — 호스팅 URL(file_url)로 영상 전송.
    up = requests.post(
        f"{RUPLOAD_BASE}/{video_id}",
        headers={"Authorization": f"OAuth {access_token}", "file_url": video_url},
        timeout=120,
    )
    if not up.ok:
        raise FacebookUploadError(f"upload {up.status_code}: {up.text[:300]}")

    # 3. finish — 게시(PUBLISHED).
    finish = requests.post(
        f"{GRAPH_BASE}/{page_id}/video_reels",
        params={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": description,
            "access_token": access_token,
        },
        timeout=30,
    )
    if not finish.ok:
        raise FacebookUploadError(f"finish {finish.status_code}: {finish.text[:300]}")

    _wait_published(video_id, access_token)
    return video_id
