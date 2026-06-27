# recommend_weekly 의 프롬프트 빌더(기존 제목 주입) 단위 테스트.
from popory_content.recommend_weekly import build_user_msg


def test_empty_known_returns_base_only():
    msg = build_user_msg([])
    assert "새로운 책" in msg
    assert "겹치" not in msg  # 목록 없으면 회피 지시 없음


def test_known_titles_injected_with_avoid_instruction():
    msg = build_user_msg(["원씽", "사피엔스", "부의 추월 차선"])
    assert "절대 제안하지 마라" in msg
    assert "원씽" in msg
    assert "사피엔스" in msg
    assert "부의 추월 차선" in msg
