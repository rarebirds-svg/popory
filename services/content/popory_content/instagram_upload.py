# Instagram Graph API를 통한 Reels·캐러셀 업로드.
import time
import requests


GRAPH_BASE = "https://graph.facebook.com/v19.0"
MAX_POLL = 20


class InstagramUploadError(Exception):
    """Instagram Graph API 업로드 실패."""


def _post(path: str, access_token: str, **params) -> dict:
    url = f"{GRAPH_BASE}/{path}"
    resp = requests.post(url, params={"access_token": access_token, **params}, timeout=30)
    if not resp.ok:
        raise InstagramUploadError(f"POST {path} {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def _wait_container(container_id: str, access_token: str) -> None:
    """컨테이너가 FINISHED 상태가 될 때까지 폴링."""
    for _ in range(MAX_POLL):
        resp = requests.get(
            f"{GRAPH_BASE}/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=15,
        )
        if resp.ok:
            data = resp.json()
            status = data.get("status_code", "")
            if status == "FINISHED":
                return
            if status == "ERROR":
                raise InstagramUploadError(f"컨테이너 오류: {data}")
        time.sleep(5)
    raise InstagramUploadError("컨테이너 FINISHED 대기 초과")


def upload_reels(ig_user_id: str, access_token: str, video_url: str, caption: str) -> str:
    """Reels(짧은 영상) 업로드. 게시된 media_id 반환."""
    container = _post(
        f"{ig_user_id}/media", access_token,
        media_type="REELS",
        video_url=video_url,
        caption=caption,
    )
    container_id = container["id"]
    _wait_container(container_id, access_token)
    result = _post(f"{ig_user_id}/media_publish", access_token, creation_id=container_id)
    return result["id"]


def upload_carousel(ig_user_id: str, access_token: str, image_urls: list[str], caption: str) -> str:
    """캐러셀 이미지 업로드. 게시된 media_id 반환."""
    child_ids = []
    for img_url in image_urls:
        resp = _post(f"{ig_user_id}/media", access_token, image_url=img_url, is_carousel_item="true")
        child_ids.append(resp["id"])
    carousel = _post(
        f"{ig_user_id}/media", access_token,
        media_type="CAROUSEL",
        children=",".join(child_ids),
        caption=caption,
    )
    result = _post(f"{ig_user_id}/media_publish", access_token, creation_id=carousel["id"])
    return result["id"]
