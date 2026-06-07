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
