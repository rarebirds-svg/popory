# 인스타그램 캐러셀 프롬프트 빌더 테스트.
from popory_content.instagram_image_prompt import build_carousel_system_prompt, build_carousel_user_message


def test_system_prompt_includes_slide_count():
    sp = build_carousel_system_prompt([], slide_count=7)
    assert "7" in sp


def test_system_prompt_includes_style_samples():
    sp = build_carousel_system_prompt(["샘플 텍스트"], slide_count=5)
    assert "샘플 텍스트" in sp


def test_user_message_includes_topic():
    msg = build_carousel_user_message("전세사기 예방", [])
    assert "전세사기 예방" in msg
    assert "slides_json" in msg


def test_user_message_includes_sources():
    sources = [{"url": "https://example.com", "note": "참고"}]
    msg = build_carousel_user_message("t", sources)
    assert "https://example.com" in msg
