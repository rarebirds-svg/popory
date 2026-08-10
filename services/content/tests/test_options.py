# 작업 옵션 파싱·매핑 검증.
from popory_content.options import parse_options, SCENE_COUNT, VOICE, STYLE


def test_defaults_when_none():
    o = parse_options(None)
    assert o == {"length": "10", "voice": "male", "image_style": "photo"}


def test_valid_merge():
    o = parse_options('{"length":"10","voice":"male","image_style":"watercolor"}')
    assert o["length"] == "10" and o["voice"] == "male" and o["image_style"] == "watercolor"


def test_invalid_falls_back():
    o = parse_options('{"length":"99","voice":"bad"}')
    assert o["length"] == "10" and o["voice"] == "male"


def test_bad_json():
    assert parse_options("not json")["length"] == "10"


def test_maps_cover_keys():
    assert set(SCENE_COUNT) == {"3", "5", "7", "10"}
    assert VOICE["male"].startswith("ko-KR")
    assert "watercolor" in STYLE["watercolor"]


from popory_content.options import parse_shorts_options, SHORT_SCENE_COUNT


def test_parse_shorts_options_defaults():
    opts = parse_shorts_options(None)
    assert opts["length"] == "60"
    assert opts["voice"] == "male"
    assert opts["image_style"] == "photo"
    assert opts["upload_targets"] == []


def test_parse_shorts_options_all_fields():
    import json
    params = json.dumps({"length": "60", "voice": "male", "image_style": "illust", "upload_targets": ["youtube", "instagram"]})
    opts = parse_shorts_options(params)
    assert opts["length"] == "60"
    assert opts["upload_targets"] == ["youtube", "instagram"]


def test_short_scene_count_keys():
    assert set(SHORT_SCENE_COUNT.keys()) == {"15", "30", "60"}
    assert SHORT_SCENE_COUNT["15"] == 3
    assert SHORT_SCENE_COUNT["30"] == 5
    assert SHORT_SCENE_COUNT["60"] == 8


def test_voice_map_uses_chirp3hd():
    from popory_content.options import VOICE
    assert VOICE["female-calm"] == "ko-KR-Chirp3-HD-Aoede"
    assert VOICE["female-bright"] == "ko-KR-Chirp3-HD-Leda"
    assert VOICE["male"] == "ko-KR-Chirp3-HD-Charon"
