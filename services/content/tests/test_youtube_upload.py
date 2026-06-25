# YouTube resumable 업로드 REST 동작 검증(모킹).
import responses
import pytest
from popory_content.youtube_upload import upload, UploadError, UPLOAD_URL


@responses.activate
def test_upload_returns_video_id():
    loc = "https://upload.example/u1"
    responses.add(responses.POST, UPLOAD_URL, status=200, headers={"Location": loc})
    responses.add(responses.PUT, loc, json={"id": "vid_abc"}, status=200)
    vid = upload("tok", b"\x00\x01", "제목", "설명", ["t"])
    assert vid == "vid_abc"


@responses.activate
def test_upload_init_error():
    responses.add(responses.POST, UPLOAD_URL, status=403, json={"error": "x"})
    with pytest.raises(UploadError):
        upload("tok", b"\x00", "t", "", [])


@responses.activate
def test_upload_sends_privacy():
    import json as _json
    loc = "https://upload.example/u2"
    responses.add(responses.POST, UPLOAD_URL, status=200, headers={"Location": loc})
    responses.add(responses.PUT, loc, json={"id": "v"}, status=200)
    upload("tok", b"\x00", "t", "", [], privacy="public")
    body = _json.loads(responses.calls[0].request.body)
    assert body["status"]["privacyStatus"] == "public"


@responses.activate
def test_upload_caption_posts_multipart_related():
    from popory_content.youtube_upload import upload_caption, CAPTION_URL
    responses.add(responses.POST, CAPTION_URL, json={"id": "cap1"}, status=200)
    upload_caption("tok", "vid1", "en", "popory en", b"1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    req = responses.calls[0].request
    assert req.headers["Authorization"] == "Bearer tok"
    assert req.headers["Content-Type"].startswith("multipart/related; boundary=")


@responses.activate
def test_upload_caption_error_raises():
    from popory_content.youtube_upload import upload_caption, CAPTION_URL, UploadError
    responses.add(responses.POST, CAPTION_URL, status=403, json={"error": "scope"})
    with pytest.raises(UploadError):
        upload_caption("tok", "vid1", "en", "n", b"x")
