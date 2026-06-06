# claude 출력에서 scenes_json·video_meta 추출을 검증.
import pytest
from popory_content.video_contract import parse_video
from popory_content.contract import ContractError


def test_parses_scenes_and_meta():
    text = """잡담
<scenes_json>
[{"caption": "사피엔스란", "narration": "인류의 역사를 다룬 책입니다."}, {"caption": "핵심 메시지", "narration": "허구가 협력을 낳았습니다."}]
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


def test_missing_tags_raises():
    with pytest.raises(ContractError):
        parse_video("장면 없음")


def test_empty_scenes_raises():
    text = '<scenes_json>[]</scenes_json><video_meta>{"title":"t"}</video_meta>'
    with pytest.raises(ContractError):
        parse_video(text)
