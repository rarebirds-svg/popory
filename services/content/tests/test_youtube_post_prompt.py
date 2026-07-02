# 게시물 프롬프트 빌더가 형식·정확성·태그 규칙을 담는지 검증.
from popory_content.youtube_post_prompt import (
    build_youtube_post_system_prompt,
    build_youtube_post_user_message,
)


def test_system_prompt_has_rules():
    sp = build_youtube_post_system_prompt()
    assert "post_markdown" in sp and "post_meta" in sp
    assert "#오늘의문장 #인생문장 #책추천 #포포리책방" in sp
    assert "quote_verified" in sp
    assert "거짓" in sp  # 허위 인용 금지 규칙


def test_user_message_includes_topic():
    um = build_youtube_post_user_message("미움받을 용기 - 기시미 이치로")
    assert "미움받을 용기" in um
    assert "post_markdown" in um
