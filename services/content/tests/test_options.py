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
    assert VOICE["male"].startswith(("ko-KR", "gemini-"))
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


def test_parse_shorts_options_keeps_facebook_target():
    import json
    params = json.dumps({"upload_targets": ["youtube", "instagram", "facebook", "tiktok"]})
    opts = parse_shorts_options(params)
    assert opts["upload_targets"] == ["youtube", "instagram", "facebook"]


def test_short_scene_count_keys():
    assert set(SHORT_SCENE_COUNT.keys()) == {"15", "30", "60"}
    assert SHORT_SCENE_COUNT["15"] == 3
    assert SHORT_SCENE_COUNT["30"] == 5
    assert SHORT_SCENE_COUNT["60"] == 8


def test_voice_map_uses_chirp3hd():
    from popory_content.options import VOICE
    assert VOICE["female-calm"] == "ko-KR-Chirp3-HD-Aoede"
    assert VOICE["female-bright"] == "ko-KR-Chirp3-HD-Leda"


def test_male_default_is_a_designed_gemini_voice():
    from popory_content import gemini_tts as g
    model, speaker = g.parse_voice(VOICE["male"])
    assert g.is_gemini_voice(VOICE["male"]) and model == "gemini-3.8-flash-tts"
    assert speaker == "voice_s8vzho2m0lq6"
    assert g.payload("x", speaker)["generationConfig"]["speechConfig"]["voiceConfig"] == {"voice": speaker}


def test_designed_voice_expiry(monkeypatch):
    # 운영 음성 ID·만료일에 묶이지 않게 가짜 만료표로 잰다
    from datetime import date
    from popory_content import options
    monkeypatch.setattr(options, "DESIGNED_VOICE_EXPIRES", {"voice_testexpiry": date(2030, 1, 31)})
    assert options.designed_voice_expiry("gemini-3.8-flash-tts/voice_testexpiry") == date(2030, 1, 31)
    assert options.designed_voice_expiry("voice_testexpiry") == date(2030, 1, 31)
    assert options.designed_voice_expiry("gemini-3.8-flash-tts/Iapetus") is None
    assert options.designed_voice_expiry("ko-KR-Chirp3-HD-Aoede") is None


def test_designed_voice_days_left(monkeypatch):
    from datetime import date
    from popory_content import options
    monkeypatch.setattr(options, "DESIGNED_VOICE_EXPIRES", {"voice_testexpiry": date(2030, 1, 31)})
    assert options.designed_voice_days_left("gemini-3.8-flash-tts/voice_testexpiry", date(2030, 1, 1)) == 30
    assert options.designed_voice_days_left("voice_testexpiry", date(2030, 2, 1)) == -1
    assert options.designed_voice_days_left("gemini-3.8-flash-tts/Iapetus", date(2030, 1, 1)) is None
    assert options.designed_voice_days_left("ko-KR-Chirp3-HD-Aoede", date(2030, 1, 1)) is None


def test_every_designed_voice_has_an_expiry():
    """VOICE 의 설계 음성(voice_…)은 모두 만료표에 있어야 한다 — 다음 교체 때 표를 빠뜨리면 만료 경고가 영영 안 난다."""
    from popory_content.options import DESIGNED_VOICE_EXPIRES
    speakers = [v.rpartition("/")[2] for v in VOICE.values()]
    assert [s for s in speakers if s.startswith("voice_") and s not in DESIGNED_VOICE_EXPIRES] == []
