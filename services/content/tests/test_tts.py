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
