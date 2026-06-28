# 유튜브 썸네일 렌더(전용 카피·배경) 단위 테스트.
import io
from pathlib import Path
from PIL import Image
from popory_content import video
from popory_content.video_prompt import build_video_system_prompt, build_shorts_system_prompt
import responses
import pytest
from popory_content.youtube_upload import set_thumbnail, UploadError


def _png(color=(20, 40, 80)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (16, 9), color).save(b, format="PNG")
    return b.getvalue()


def test_none_when_missing_copy_or_prompt(tmp_path):
    assert video.render_thumbnail(None, "bg", tmp_path / "t.jpg", image_fetcher=lambda p: _png()) is None
    assert video.render_thumbnail("후킹", None, tmp_path / "t.jpg", image_fetcher=lambda p: _png()) is None


def test_landscape_1280x720(tmp_path):
    out = video.render_thumbnail("인생을 바꾼 한 문장", "cinematic library", tmp_path / "t.jpg", portrait=False, image_fetcher=lambda p: _png())
    assert out is not None
    im = Image.open(out)
    assert im.size == (1280, 720)
    assert im.format == "JPEG"


def test_portrait_1080x1920_with_solid_fallback(tmp_path):
    # image_fetcher가 None 반환 → 단색 폴백 경로
    out = video.render_thumbnail("강렬한 한 줄", "cinematic", tmp_path / "t.jpg", portrait=True, image_fetcher=lambda p: None)
    assert out is not None
    im = Image.open(out)
    assert im.size == (1080, 1920)
    assert im.format == "JPEG"


def test_broken_image_bytes_falls_back(tmp_path):
    out = video.render_thumbnail("카피", "cinematic", tmp_path / "t.jpg", image_fetcher=lambda p: b"not-an-image")
    assert out is not None
    assert Image.open(out).size == (1280, 720)


def test_prompts_instruct_thumbnail_keys():
    assert "thumbnail_copy" in build_video_system_prompt([], scene_count=8)
    assert "thumbnail_image_prompt" in build_video_system_prompt([], scene_count=8)
    assert "thumbnail_copy" in build_shorts_system_prompt([], scene_count=8)
    assert "thumbnail_image_prompt" in build_shorts_system_prompt([], scene_count=8)


@responses.activate
def test_set_thumbnail_ok():
    responses.add(responses.POST, "https://www.googleapis.com/upload/youtube/v3/thumbnails/set", json={"items": [{}]}, status=200)
    set_thumbnail("tok", "vid123", b"\xff\xd8\xff")  # 예외 없으면 통과


@responses.activate
def test_set_thumbnail_403_raises():
    responses.add(responses.POST, "https://www.googleapis.com/upload/youtube/v3/thumbnails/set", json={"error": {}}, status=403)
    with pytest.raises(UploadError):
        set_thumbnail("tok", "vid123", b"\xff\xd8\xff")
