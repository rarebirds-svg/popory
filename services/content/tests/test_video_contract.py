# claude 출력에서 scenes_json·video_meta 추출을 검증.
import pytest
from popory_content.video_contract import parse_video
from popory_content.contract import ContractError


def test_parses_scenes_and_meta():
    text = """잡담
<scenes_json>
[{"caption": "사피엔스란", "narration": "인류의 역사를 다룬 책입니다.", "image_prompt": "ancient humans by fire, cinematic"}, {"caption": "핵심 메시지", "narration": "허구가 협력을 낳았습니다.", "image_prompt": "abstract cooperation, no text"}]
</scenes_json>
<video_meta>
{"title": "사피엔스 요약", "description": "책 요약 영상", "tags": ["책", "사피엔스"]}
</video_meta>
끝"""
    scenes, meta = parse_video(text)
    assert len(scenes) == 2
    assert scenes[0]["caption"] == "사피엔스란"
    assert scenes[1]["narration"].endswith("협력을 낳았습니다.")
    assert meta["title"] == "사피엔스 요약"
    assert meta["tags"] == ["책", "사피엔스"]
    assert scenes[0]["image_prompt"].startswith("ancient")
    assert scenes[1]["image_prompt"]  # 모든 장면에 image_prompt 필수
    # 설명란에 구독 CTA·브랜딩이 자동 append 된다(요약은 보존)
    assert "책 요약 영상" in meta["description"]
    assert "sub_confirmation=1" in meta["description"]
    assert "포포리 책방" in meta["description"]


def test_missing_tags_raises():
    with pytest.raises(ContractError):
        parse_video("장면 없음")


def test_empty_scenes_raises():
    text = '<scenes_json>[]</scenes_json><video_meta>{"title":"t"}</video_meta>'
    with pytest.raises(ContractError):
        parse_video(text)


def test_missing_image_prompt_raises():
    text = """<scenes_json>
[{"caption": "장면", "narration": "내레이션 있음."}]
</scenes_json>
<video_meta>
{"title": "t", "description": "d", "tags": []}
</video_meta>"""
    with pytest.raises(ContractError):
        parse_video(text)


def _two_scenes(last_narration="여운을 남기는 마무리입니다.", card=None):
    second = {"caption": "핵심", "narration": last_narration, "image_prompt": "a quiet lamp"}
    if card is not None:
        second["card"] = card
    scenes = [{"caption": "도입", "narration": "결론부터 말합니다.", "image_prompt": "old road"}, second]
    import json
    return f"<scenes_json>{json.dumps(scenes, ensure_ascii=False)}</scenes_json><video_meta>{{\"title\":\"t\",\"description\":\"d\",\"tags\":[]}}</video_meta>"


def test_ending_cta_appended_for_longform_only():
    from popory_content.video_prompt import ENDING_CTA_CAPTION
    scenes, _ = parse_video(_two_scenes(), ending_cta=True)
    assert len(scenes) == 3
    assert scenes[-1]["caption"] == ENDING_CTA_CAPTION
    assert "구독" in scenes[-1]["narration"] and "댓글" in scenes[-1]["narration"]
    assert scenes[-1]["image_prompt"]  # 배경 생성이 되도록 image_prompt 필수
    # 쇼츠(기본값)는 CTA 를 붙이지 않는다
    scenes, _ = parse_video(_two_scenes())
    assert len(scenes) == 2


def test_ending_cta_not_duplicated_when_llm_wrote_it():
    scenes, _ = parse_video(_two_scenes("도움되셨다면 구독과 좋아요 부탁드립니다. 댓글로 남겨주세요."), ending_cta=True)
    assert len(scenes) == 2


def test_card_normalized_and_malformed_dropped():
    scenes, _ = parse_video(_two_scenes(card={"type": "quote", "text": "“부는 보이지 않는다”", "source": "모건 하우절"}))
    assert scenes[1]["card"] == {"type": "quote", "text": "부는 보이지 않는다", "source": "모건 하우절"}
    scenes, _ = parse_video(_two_scenes(card={"type": "keypoints", "title": "3원칙", "items": ["복리", " 인내심 ", "", "통제권", "다섯", "여섯"]}))
    assert scenes[1]["card"] == {"type": "keypoints", "title": "3원칙", "items": ["복리", "인내심", "통제권", "다섯"]}
    for bad in ({"type": "keypoints", "items": "복리"}, {"type": "quote"}, {"type": "table"}, "quote", {"type": "keypoints", "items": ["하나"]}):
        scenes, _ = parse_video(_two_scenes(card=bad))
        assert "card" not in scenes[1]
