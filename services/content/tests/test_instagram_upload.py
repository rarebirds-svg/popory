# Instagram Graph API 업로드 모듈 테스트.
import pytest
import responses as rsps_lib
from popory_content.instagram_upload import upload_reels, upload_carousel


@rsps_lib.activate
def test_upload_reels_calls_meta_api():
    ig_user = "123"
    access_token = "tok"
    video_url = "https://api.example.com/media/token"
    caption = "테스트 캡션"

    rsps_lib.add(rsps_lib.POST, f"https://graph.facebook.com/v19.0/{ig_user}/media",
                 json={"id": "container_1"}, status=200)
    rsps_lib.add(rsps_lib.GET, f"https://graph.facebook.com/v19.0/container_1",
                 json={"status_code": "FINISHED", "id": "container_1"}, status=200)
    rsps_lib.add(rsps_lib.POST, f"https://graph.facebook.com/v19.0/{ig_user}/media_publish",
                 json={"id": "media_published_1"}, status=200)

    media_id = upload_reels(ig_user, access_token, video_url, caption)
    assert media_id == "media_published_1"


@rsps_lib.activate
def test_upload_carousel_calls_meta_api():
    ig_user = "123"
    access_token = "tok"
    image_urls = ["https://example.com/img/0", "https://example.com/img/1"]
    caption = "캐러셀 캡션"

    rsps_lib.add(rsps_lib.POST, f"https://graph.facebook.com/v19.0/{ig_user}/media",
                 json={"id": "img_c_0"}, status=200)
    rsps_lib.add(rsps_lib.POST, f"https://graph.facebook.com/v19.0/{ig_user}/media",
                 json={"id": "img_c_1"}, status=200)
    rsps_lib.add(rsps_lib.POST, f"https://graph.facebook.com/v19.0/{ig_user}/media",
                 json={"id": "carousel_c"}, status=200)
    rsps_lib.add(rsps_lib.POST, f"https://graph.facebook.com/v19.0/{ig_user}/media_publish",
                 json={"id": "carousel_published"}, status=200)

    media_id = upload_carousel(ig_user, access_token, image_urls, caption)
    assert media_id == "carousel_published"
