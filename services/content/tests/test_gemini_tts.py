# gemini_tts — 음성 이름 해석, 단가·월/일 상한 장부, 무음 기준 문장 분할, API 호출 실패 처리.
import base64
import datetime
import math
from array import array

import pytest

from popory_content import gemini_tts as g


@pytest.fixture(autouse=True)
def _ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "LEDGER", tmp_path / "ledger.json")
    monkeypatch.setattr(g.time, "sleep", lambda s: None)
    monkeypatch.delenv("POPORY_GEMINI_TTS_PRICE", raising=False)


def _pcm(parts, rate=24000, pause=0.4, edge=0.1):
    a = array("h", [0] * int(rate * edge))
    for k, sec in enumerate(parts):
        a.extend(int(8000 * math.sin(2 * math.pi * 220 * t / rate)) for t in range(int(rate * sec)))
        a.extend([0] * int(rate * (pause if k < len(parts) - 1 else edge)))
    return a.tobytes()


def test_voice_name_parsing():
    assert g.is_gemini_voice("gemini-3.8-flash-tts/Iapetus")
    assert not g.is_gemini_voice("ko-KR-Neural2-C")
    assert g.parse_voice("gemini-3.8-flash-tts/Iapetus") == ("gemini-3.8-flash-tts", "Iapetus")


def test_price_doubles_from_2027(monkeypatch):
    assert g.price_per_m(datetime.date(2026, 12, 31)) == 9.0
    assert g.price_per_m(datetime.date(2027, 1, 1)) == 18.0
    monkeypatch.setenv("POPORY_GEMINI_TTS_PRICE", "12")
    assert g.price_per_m(datetime.date(2026, 10, 5)) == 12.0


def test_ledger_accumulates_and_resets_by_month_and_day():
    d1 = datetime.date(2026, 10, 5)
    g.record(600, 25, d1)
    g.record(60, 3, d1)
    u = g.usage(d1)
    assert u["month_seconds"] == pytest.approx(660) and u["day_requests"] == 28
    assert u["month_usd"] == pytest.approx(g.cost_usd(660, d1))
    assert g.usage(datetime.date(2026, 10, 6))["day_requests"] == 0          # 날이 바뀌면 요청 수 0
    assert g.usage(datetime.date(2026, 11, 1))["month_usd"] == 0.0           # 달이 바뀌면 사용액 0


def test_budget_blocks_before_exceeding_caps(monkeypatch):
    d = datetime.date(2026, 10, 5)
    assert g.budget_block_reason(["가" * 3000] * 16, d) is None              # 롱폼 1편은 여유 있게 통과
    monkeypatch.setattr(g, "MONTHLY_USD_CAP", 0.05)
    assert "월 상한" in g.budget_block_reason(["가" * 3000] * 16, d)
    monkeypatch.setattr(g, "MONTHLY_USD_CAP", 9.0)
    g.record(0, 85, d)
    assert "일 요청" in g.budget_block_reason(["가"] * 16, d)                # 85 + 16 > 90


def test_split_sentences_cuts_at_pauses_and_trims_edges():
    pcm = _pcm([0.8, 0.5, 1.2])
    pieces = g.split_sentences(pcm, 24000, [20, 12, 30])
    assert pieces is not None and len(pieces) == 3
    secs = [len(p) / 2 / 24000 for p in pieces]
    assert secs == pytest.approx([0.8, 0.5, 1.2], abs=0.03)                  # 앞뒤·사이 무음은 빠진다


def test_split_sentences_prefers_pause_nearest_expected_position():
    # 짧은 숨(0.2초)과 긴 숨(0.5초)이 있어도 원고 비례 위치에 가까운 쪽을 고른다
    rate = 24000
    a = array("h")
    tone = lambda sec: [int(8000 * math.sin(2 * math.pi * 220 * t / rate)) for t in range(int(rate * sec))]
    a.extend(tone(0.4)); a.extend([0] * int(rate * 0.2)); a.extend(tone(0.4))      # 문장 1 안의 숨
    a.extend([0] * int(rate * 0.5)); a.extend(tone(0.8))
    pieces = g.split_sentences(a.tobytes(), rate, [10, 10])
    secs = [len(p) / 2 / rate for p in pieces]
    assert secs == pytest.approx([1.0, 0.8], abs=0.03)


def test_split_sentences_gives_up_without_enough_pauses():
    assert g.split_sentences(_pcm([2.0]), 24000, [10, 10, 10]) is None
    one = g.split_sentences(_pcm([1.0]), 24000, [10])
    assert len(one) == 1 and len(one[0]) / 2 / 24000 == pytest.approx(1.0, abs=0.03)


def test_payload_separates_direction_from_transcript():
    body = g.payload("대본입니다.", "Iapetus", style="calm")
    text = body["contents"][0]["parts"][0]["text"]
    assert text == "### DIRECTOR'S NOTES\ncalm\n\n#### TRANSCRIPT\n대본입니다."
    assert body["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Iapetus"


class _Resp:
    def __init__(self, status, text="", pcm=b""):
        self.status_code, self.text, self._pcm = status, text, pcm

    def json(self):
        return {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/L16;codec=pcm;rate=24000", "data": base64.b64encode(self._pcm).decode()}}]}}]}


def test_synthesize_scene_requires_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(g.GeminiTTSError, match="GEMINI_API_KEY"):
        g.synthesize_scene("대본", "gemini-3.8-flash-tts/Iapetus")


def test_synthesize_scene_returns_pcm_and_records_usage(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    pcm = b"\x00\x01" * 24000                                               # 1초
    seen = {}

    def post(url, params=None, json=None, timeout=None):
        seen.update(url=url, params=params)
        return _Resp(200, pcm=pcm)

    monkeypatch.setattr(g.requests, "post", post)
    out, rate = g.synthesize_scene("대본", "gemini-3.8-flash-tts/Iapetus")
    assert out == pcm and rate == 24000
    assert seen["url"].endswith("/models/gemini-3.8-flash-tts:generateContent") and seen["params"] == {"key": "k"}
    u = g.usage()
    assert u["month_seconds"] == pytest.approx(1.0) and u["day_requests"] == 1


def test_synthesize_scene_does_not_retry_4xx_but_counts_request(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    calls = []
    monkeypatch.setattr(g.requests, "post", lambda *a, **k: calls.append(1) or _Resp(429, "RESOURCE_EXHAUSTED"))
    with pytest.raises(g.GeminiTTSError, match="429"):
        g.synthesize_scene("대본", "gemini-3.8-flash-tts/Iapetus")
    assert len(calls) == 1 and g.usage()["day_requests"] == 1


def test_synthesize_scene_retries_5xx_once(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    seq = [_Resp(503, "busy"), _Resp(200, pcm=b"\x00\x00" * 2400)]
    monkeypatch.setattr(g.requests, "post", lambda *a, **k: seq.pop(0))
    pcm, _ = g.synthesize_scene("대본", "gemini-3.8-flash-tts/Iapetus")
    assert len(pcm) == 4800 and g.usage()["day_requests"] == 2
