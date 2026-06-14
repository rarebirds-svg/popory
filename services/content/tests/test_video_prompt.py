# 영상 대본 system prompt 가 장면·메타 출력 계약을 담는지 검증.
from popory_content.video_prompt import build_video_system_prompt, build_video_user_message


def test_system_prompt_has_contract():
    sp = build_video_system_prompt([], scene_count=12, image_style_kw="watercolor painting")
    assert "scenes_json" in sp
    assert "video_meta" in sp
    assert "narration" in sp
    assert "caption" in sp
    assert "image_prompt" in sp
    assert "12" in sp
    assert "watercolor" in sp


def test_system_prompt_embeds_style():
    sp = build_video_system_prompt(["내 말투 샘플"])
    assert "내 말투 샘플" in sp


def test_user_message_has_topic():
    um = build_video_user_message("사피엔스 요약", [])
    assert "사피엔스 요약" in um
    assert "scenes_json" in um


from popory_content.video_prompt import build_shorts_system_prompt, build_shorts_user_message


def test_build_shorts_system_prompt_includes_shorts_rules():
    sp = build_shorts_system_prompt([], scene_count=5, image_style_kw="photorealistic")
    assert "쇼츠" in sp or "Shorts" in sp
    assert "5" in sp
    assert "세로형" in sp or "60초" in sp


def test_build_shorts_user_message_includes_topic():
    msg = build_shorts_user_message("전세사기 예방", [])
    assert "전세사기 예방" in msg
    assert "scenes_json" in msg


def test_system_prompt_demands_consistent_style_suffix():
    from popory_content.video_prompt import build_video_system_prompt
    sp = build_video_system_prompt([], scene_count=8, image_style_kw="watercolor painting")
    # 모든 장면이 같은 톤이 되도록 '일관된'/'동일' 류 지시가 image_prompt 규칙에 있어야 한다
    assert "일관" in sp
    assert "watercolor painting" in sp


def test_video_and_shorts_prompts_avoid_frontfacing_faces():
    """무서운 얼굴 방지 — 정면 얼굴 구도를 피하고 뒷모습·실루엣·원경으로 유도(사람 자체는 허용)."""
    from popory_content.video_prompt import build_video_system_prompt, build_shorts_system_prompt
    for sp in (build_video_system_prompt([]), build_shorts_system_prompt([])):
        assert "정면" in sp             # 정면 얼굴 회피 지시
        assert "뒷모습" in sp           # 얼굴이 안 드러나는 대안 구도
        assert "사람이 필요하면" in sp   # 사람 자체는 허용(하드 금지 아님)
