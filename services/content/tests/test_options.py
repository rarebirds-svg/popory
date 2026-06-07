# 작업 옵션 파싱·매핑 검증.
from popory_content.options import parse_options, SCENE_COUNT, VOICE, STYLE


def test_defaults_when_none():
    o = parse_options(None)
    assert o == {"length": "5", "voice": "female-calm", "image_style": "photo"}


def test_valid_merge():
    o = parse_options('{"length":"10","voice":"male","image_style":"watercolor"}')
    assert o["length"] == "10" and o["voice"] == "male" and o["image_style"] == "watercolor"


def test_invalid_falls_back():
    o = parse_options('{"length":"99","voice":"bad"}')
    assert o["length"] == "5" and o["voice"] == "female-calm"


def test_bad_json():
    assert parse_options("not json")["length"] == "5"


def test_maps_cover_keys():
    assert set(SCENE_COUNT) == {"3", "5", "7", "10"}
    assert VOICE["male"].startswith("ko-KR")
    assert "watercolor" in STYLE["watercolor"]
