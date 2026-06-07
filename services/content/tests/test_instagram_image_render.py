# 인스타그램 캐러셀 슬라이드 Pillow 렌더러 테스트.
from popory_content.instagram_image_render import render_slide, render_carousel


def test_render_slide_returns_jpeg_bytes():
    slide = {"title": "제목", "body": "본문 내용입니다.", "image_prompt": "sunny sky"}
    data = render_slide(slide)
    assert isinstance(data, bytes)
    assert len(data) > 1000
    assert data[:2] == b"\xff\xd8"


def test_render_carousel_returns_list():
    slides = [
        {"title": f"제목{i}", "body": "본문", "image_prompt": "sky"}
        for i in range(3)
    ]
    images = render_carousel(slides)
    assert len(images) == 3
    for img in images:
        assert img[:2] == b"\xff\xd8"


def test_render_slide_with_bg_image():
    """배경 이미지가 주어지면 커버 크롭해 사용한다."""
    from PIL import Image
    import io
    bg = Image.new("RGB", (800, 600), (100, 200, 100))
    buf = io.BytesIO()
    bg.save(buf, format="JPEG")
    bg_bytes = buf.getvalue()
    slide = {"title": "제목", "body": "본문", "image_prompt": "p"}
    data = render_slide(slide, bg_image_bytes=bg_bytes)
    assert data[:2] == b"\xff\xd8"
