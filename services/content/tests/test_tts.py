# Google TTS 합성 — 키 유무·응답별 동작 검증(REST 모킹).
import base64

import responses

from popory_content import tts


@responses.activate
def test_synthesize_returns_bytes(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    audio = base64.b64encode(b"\xff\xfbMP3").decode()
    responses.add(responses.POST, tts.TTS_URL, json={"audioContent": audio}, status=200)
    out = tts.synthesize("안녕하세요")
    assert out == b"\xff\xfbMP3"


def test_synthesize_none_without_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_TTS_API_KEY", raising=False)
    assert tts.synthesize("안녕") is None


@responses.activate
def test_synthesize_none_on_error(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    responses.add(responses.POST, tts.TTS_URL, json={"error": "x"}, status=500)
    assert tts.synthesize("안녕") is None


@responses.activate
def test_synthesize_uses_voice(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    responses.add(responses.POST, tts.TTS_URL, json={"audioContent": base64.b64encode(b"x").decode()}, status=200)
    tts.synthesize("안녕", voice="ko-KR-Neural2-C")
    body = responses.calls[0].request.body
    assert "ko-KR-Neural2-C" in (body if isinstance(body, str) else body.decode())


def test_split_for_pauses_strips_literal_brackets():
    from popory_content.tts import _split_for_pauses
    out = _split_for_pauses("[단독] 첫 문장입니다. 둘째 문장이에요.")
    # 내레이션의 리터럴 대괄호는 제거되고, 문장 사이 pause 마크업만 남는다
    assert "[단독]" not in out
    assert "단독 첫 문장입니다." in out
    assert "[pause]" in out  # 문장 구분 pause는 유지


def test_split_for_pauses_inserts_pause_markup():
    from popory_content.tts import _split_for_pauses
    out = _split_for_pauses("첫째 문장입니다. 둘째 문장이에요!")
    assert out == "첫째 문장입니다. [pause] 둘째 문장이에요!"


def test_split_for_pauses_comma_gets_short_pause():
    from popory_content.tts import _split_for_pauses
    out = _split_for_pauses("사과와, 배 그리고, 감을 샀습니다.")
    # 쉼표 뒤에는 짧은 호흡([pause short])이 들어간다 — 급하게 안 읽도록
    assert out.count("[pause short]") == 2
    assert ", [pause short] 배" in out


def test_split_for_pauses_comma_shorter_than_sentence():
    from popory_content.tts import _split_for_pauses
    out = _split_for_pauses("그는, 천천히 말했다. 그리고 떠났다.")
    # 쉼표는 [pause short], 문장 끝은 더 긴 [pause] — 계단식
    assert "[pause short]" in out
    assert "[pause]" in out


@responses.activate
def test_synthesize_uses_markup_and_rate(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    responses.add(responses.POST, tts.TTS_URL,
                  json={"audioContent": base64.b64encode(b"x").decode()}, status=200)
    tts.synthesize("첫 문장. 둘째 문장.", voice="ko-KR-Chirp3-HD-Aoede")
    import json as _json
    body = responses.calls[0].request.body
    payload = _json.loads(body if isinstance(body, str) else body.decode())
    assert payload["input"].get("markup")  # text 아니라 markup 사용
    assert "[pause]" in payload["input"]["markup"]  # 문장 사이 pause
    assert payload["audioConfig"]["speakingRate"] == 0.96
    assert payload["voice"]["name"] == "ko-KR-Chirp3-HD-Aoede"
