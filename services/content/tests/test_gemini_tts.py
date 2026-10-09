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
    # 사이 무음은 빠지고, 앞뒤는 끝소리가 잘리지 않게 EDGE_PAD_MS(40ms)만 남긴다
    assert secs == pytest.approx([0.84, 0.5, 1.24], abs=0.03)


def test_split_sentences_prefers_pause_nearest_expected_position():
    # 짧은 숨(0.2초)과 긴 숨(0.5초)이 있어도 원고 비례 위치에 가까운 쪽을 고른다
    rate = 24000
    a = array("h")
    tone = lambda sec: [int(8000 * math.sin(2 * math.pi * 220 * t / rate)) for t in range(int(rate * sec))]
    a.extend(tone(0.4)); a.extend([0] * int(rate * 0.2)); a.extend(tone(0.4))      # 문장 1 안의 숨
    a.extend([0] * int(rate * 0.5)); a.extend(tone(0.8))
    pieces = g.split_sentences(a.tobytes(), rate, [10, 10])
    secs = [len(p) / 2 / rate for p in pieces]
    assert secs == pytest.approx([1.0, 0.8], abs=0.03)   # 앞뒤에 무음이 없으면 덧붙일 여유도 없다


def test_split_sentences_gives_up_without_enough_pauses():
    assert g.split_sentences(_pcm([2.0]), 24000, [10, 10, 10]) is None
    one = g.split_sentences(_pcm([1.0]), 24000, [10])
    assert len(one) == 1 and len(one[0]) / 2 / 24000 == pytest.approx(1.08, abs=0.03)


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
    monkeypatch.setattr(g.requests, "post", lambda *a, **k: calls.append(1) or _Resp(400, "INVALID_ARGUMENT"))
    with pytest.raises(g.GeminiTTSError, match="400"):
        g.synthesize_scene("대본", "gemini-3.8-flash-tts/Iapetus")
    assert len(calls) == 1 and g.usage()["day_requests"] == 1


def test_synthesize_scene_daily_quota_429_is_not_retried(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    calls = []
    body = "RESOURCE_EXHAUSTED Quota exceeded for metric: generate_requests_per_model_per_day, limit: 100 (PerDay)"
    monkeypatch.setattr(g.requests, "post", lambda *a, **k: calls.append(1) or _Resp(429, body))
    with pytest.raises(g.GeminiTTSError, match="PerDay"):
        g.synthesize_scene("대본", "gemini-3.8-flash-tts/Iapetus")
    assert len(calls) == 1


def test_synthesize_scene_retries_rate_limit_and_timeouts_with_backoff(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    waits = []
    monkeypatch.setattr(g.time, "sleep", waits.append)
    seq = [_Resp(429, "RESOURCE_EXHAUSTED per minute"), None, _Resp(200, pcm=b"\x00\x00" * 2400)]

    def post(*a, **k):
        r = seq.pop(0)
        if r is None:
            raise g.requests.Timeout("read timed out")
        return r

    monkeypatch.setattr(g.requests, "post", post)
    pcm, _ = g.synthesize_scene("대본", "gemini-3.8-flash-tts/Iapetus")
    assert len(pcm) == 4800 and waits == [15, 45] and g.usage()["day_requests"] == 3


def test_synthesize_scene_retries_5xx_once(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    seq = [_Resp(503, "busy"), _Resp(200, pcm=b"\x00\x00" * 2400)]
    monkeypatch.setattr(g.requests, "post", lambda *a, **k: seq.pop(0))
    pcm, _ = g.synthesize_scene("대본", "gemini-3.8-flash-tts/Iapetus")
    assert len(pcm) == 4800 and g.usage()["day_requests"] == 2


def _tone(sec, rate=24000, amp=8000):
    return [int(amp * math.sin(2 * math.pi * 220 * t / rate)) for t in range(int(rate * sec))]


def _build(spec, rate=24000):
    """spec: [("t", 초, 진폭?) | ("s", 초)] 를 이어붙인 PCM."""
    a = array("h")
    for item in spec:
        if item[0] == "t":
            a.extend(_tone(item[1], rate, item[2] if len(item) > 2 else 8000))
        else:
            a.extend([0] * int(rate * item[1]))
    return a.tobytes()


def _secs(pieces, rate=24000):
    return [len(p) / 2 / rate for p in pieces]


def test_alignment_prefers_sentence_pause_over_nearer_comma_pause():
    # 문장1 = 1.0 + (쉼표 숨 0.16) + 1.0, 문장 끝 숨 0.5, 문장2 = 1.0. 원고 비례 예상 위치는 쉼표 숨 쪽에 더 가깝다.
    pcm = _build([("s", 0.1), ("t", 1.0), ("s", 0.16), ("t", 1.0), ("s", 0.5), ("t", 1.0), ("s", 0.1)])
    pieces = g.split_sentences(pcm, 24000, [12, 10])
    assert _secs(pieces) == pytest.approx([2.2, 1.04], abs=0.03)


def test_alignment_handles_many_sentences_with_drifting_pace():
    # 8문장, 실제 길이가 원고 비례와 ±40% 어긋나도 숨마다 정확히 자른다
    lens = [1.4, 0.6, 1.1, 0.9, 1.6, 0.5, 1.2, 0.8]
    spec = [("s", 0.1)]
    for k, sec in enumerate(lens):
        spec.append(("t", sec))
        spec.append(("s", 0.4 if k < len(lens) - 1 else 0.1))
    pieces = g.split_sentences(_build(spec), 24000, [10] * 8)
    assert pieces is not None
    got = _secs(pieces)
    assert got[1:-1] == pytest.approx(lens[1:-1], abs=0.03)


def test_paragraph_boundary_prefers_long_pause():
    # 장면 경계(문장 0 뒤)는 긴 숨(0.9초)을, 같은 거리의 짧은 숨(0.2초)보다 고른다
    pcm = _build([("s", 0.1), ("t", 0.9), ("s", 0.2), ("t", 0.3), ("s", 0.9), ("t", 1.0), ("s", 0.1)])
    pieces = g.split_sentences(pcm, 24000, [10, 10], paragraph_after={0})
    assert _secs(pieces)[0] == pytest.approx(1.44, abs=0.03)


def test_edge_artifacts_are_dropped():
    # 앞의 0.15초 딸깍·뒤의 0.2초 잡음은 본 발화와 떨어져 있으면 버린다 — 챕터 경계의 '이상한 소리'
    pcm = _build([("t", 0.15), ("s", 0.4), ("t", 1.0), ("s", 0.4), ("t", 0.2), ("s", 0.1)])
    pieces = g.split_sentences(pcm, 24000, [10])
    assert _secs(pieces) == pytest.approx([1.08], abs=0.03)


def test_pieces_fade_in_and_out():
    pcm = _build([("t", 1.0, 20000)])
    piece = array("h")
    piece.frombytes(g.split_sentences(pcm, 24000, [10])[0])
    assert abs(piece[0]) < 200 and abs(piece[-1]) < 200          # 끝이 0 근처 — 딸깍 없음
    assert max(abs(x) for x in piece[2400:4800]) > 3000


def test_chunk_loudness_is_normalized():
    # 다른 음량으로 생성된 두 묶음도 같은 발화 음량으로 맞춘다 — 묶음 사이 목소리 차이 완화
    def rms(b):
        a = array("h"); a.frombytes(b)
        return math.sqrt(sum(x * x for x in a) / len(a))
    loud = g.split_sentences(_build([("s", 0.1), ("t", 1.0, 16000), ("s", 0.1)]), 24000, [10])[0]
    soft = g.split_sentences(_build([("s", 0.1), ("t", 1.0, 3000), ("s", 0.1)]), 24000, [10])[0]
    assert rms(loud) == pytest.approx(rms(soft), rel=0.05)


def test_implausible_alignment_is_rejected():
    # 3문장인데 원고상 아주 짧아야 할 문장이 소리로는 대부분을 차지하면 경계를 믿지 않는다
    pcm = _build([("s", 0.1), ("t", 0.3), ("s", 0.4), ("t", 3.0), ("s", 0.4), ("t", 0.3), ("s", 0.1)])
    assert g.split_sentences(pcm, 24000, [40, 2, 40]) is None


def test_plan_chunks_balances_and_respects_limit():
    assert g.plan_chunks([35] * 17, 360) == [list(range(8)), list(range(8, 17))]   # 롱폼 → 2요청
    assert g.plan_chunks([7] * 8, 360) == [list(range(8))]                         # 쇼츠 → 1요청
    assert g.plan_chunks([], 360) == []
    chunks = g.plan_chunks([50] * 20, 360)
    assert [i for c in chunks for i in c] == list(range(20)) and len(chunks) == 3


def test_pause_spans_reports_inner_pauses_only():
    pcm = _build([("s", 0.2), ("t", 0.5), ("s", 0.3), ("t", 0.5), ("s", 0.2)])
    spans = g.pause_spans(pcm, 24000, 80)
    assert len(spans) == 1 and spans[0][0] == pytest.approx(0.7, abs=0.02) and spans[0][1] == pytest.approx(1.0, abs=0.02)


def _voiced(f0, seconds=3.0, rate=24000, harmonics=20, bright=1.0):
    """기본 주파수 f0 의 배음 소리(살짝 떨림) + 짧은 쉼 — 목소리 측정 확인용."""
    a = array("h")
    ph = 0.0
    n = int(seconds * rate)
    for i in range(n):
        ph += 2 * math.pi * f0 * (1 + 0.02 * math.sin(2 * math.pi * 3 * i / rate)) / rate
        s = sum((0.6 / h) * bright ** (h / 5) * math.sin(h * ph) for h in range(1, harmonics))
        a.append(int(7000 * s) if (i // (rate // 2)) % 4 != 3 else 0)
    return a.tobytes()


def test_voice_profile_measures_pitch_within_a_fraction_of_a_semitone():
    for f0 in (100.0, 125.0, 160.0):
        prof = g.voice_profile(_voiced(f0), 24000, chars=20)
        assert abs(g._semitones(prof["f0"] / f0)) < 0.15
        assert prof["cps"] > 0


def test_voice_profile_is_none_for_silence():
    assert g.voice_profile(b"\x00\x00" * 24000, 24000, 10) is None


def test_match_filter_deadzone_pitch_tempo_and_tilt():
    ref = {"f0": 120.0, "tilt_db": -18.0, "cps": 7.0}
    assert g.match_filter(ref, dict(ref), 24000) is None                     # 같으면 손대지 않는다
    assert g.match_filter(ref, {**ref, "f0": 120.5}, 24000) is None          # 0.07반음 — 안 들린다
    up = g.match_filter(ref, {**ref, "f0": 127.0}, 24000)
    rate_part, _, rest = up.partition(",aresample=24000,")
    assert rate_part == f"asetrate={round(24000 * 120 / 127)}"
    assert rest == f"atempo={127 / 120:.4f}"                                # 피치만 내리고 빠르기는 되돌림
    faster = g.match_filter(ref, {**ref, "cps": 7.5}, 24000)
    assert faster == f"atempo={7.0 / 7.5:.4f}"                               # 말이 빠르면 늦춘다
    assert g.match_filter(ref, {**ref, "tilt_db": -16.0}, 24000) == "treble=g=-2.0:f=1200"
    # 상한 — 반음 2개·빠르기 8%·밝기 3dB 를 넘겨 비틀지 않는다
    big = g.match_filter(ref, {"f0": 150.0, "tilt_db": -10.0, "cps": 9.0}, 24000)
    assert f"asetrate={round(24000 * 2 ** (-2 / 12))}" in big and "treble=g=-3.0" in big
    # 2차 보정은 밝기만
    assert g.match_filter(ref, {"f0": 127.0, "tilt_db": -16.0, "cps": 7.5}, 24000, tilt_only=True) == "treble=g=-2.0:f=1200"


def test_needs_retry_and_distance():
    ref = {"f0": 120.0, "tilt_db": -18.0, "cps": 7.0}
    assert not g.needs_retry(ref, {**ref, "f0": 124.0})                     # 0.57반음
    assert g.needs_retry(ref, {**ref, "f0": 126.0})                         # 0.84반음
    assert g.voice_distance(ref, {**ref, "f0": 122.0}) < g.voice_distance(ref, {**ref, "f0": 127.0})


def test_head_pcm_takes_leading_share():
    pcm = bytes(range(200))
    assert g.head_pcm(pcm, 0.25) == pcm[:50]
    assert g.head_pcm(pcm, 2.0) == pcm


def test_prepay_depleted_402_is_explained_and_remembered(monkeypatch):
    # 2026-10-06: 선불 크레딧 소진(402)으로 자동 생성 영상이 폴백 음성으로 나왔다 — 이유를 사람 말로, 장부에 남긴다.
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    calls = []
    body = '{"error": {"code": 402, "message": "Your prepayment credits are depleted.", "status": "RESOURCE_EXHAUSTED"}}'
    monkeypatch.setattr(g.requests, "post", lambda *a, **k: calls.append(1) or _Resp(402, body))
    with pytest.raises(g.GeminiTTSError, match="선불 크레딧 소진"):
        g.synthesize_scene("대본", "gemini-3.8-flash-tts/Iapetus")
    assert len(calls) == 1                                       # 다시 보내도 같다
    err = g.usage()["last_error"]
    assert err["message"].startswith("402 선불 크레딧 소진") and "depleted" in err["message"]
    # 다음 성공이 마지막 실패를 지운다
    monkeypatch.setattr(g.requests, "post", lambda *a, **k: _Resp(200, pcm=b"\x00\x00" * 2400))
    g.synthesize_scene("대본", "gemini-3.8-flash-tts/Iapetus")
    assert g.usage()["last_error"] is None


def _speech(sentences, rate=24000, sent_pause=0.5, para_after=(), para_pause=0.6):
    """sentences: [[소리 초, ('s', 숨 초), 소리 초, ...], ...] — 문장 안 숨(쉼표·극적 쉼)도 넣을 수 있다.
    반환: (PCM, 문장별 정답 길이 초)."""
    spec, truth = [("s", 0.1)], []
    for k, parts in enumerate(sentences):
        dur = 0.0
        for p in parts:
            if isinstance(p, tuple):
                spec.append(p); dur += p[1]
            else:
                spec.append(("t", p)); dur += p
        truth.append(dur)
        if k < len(sentences) - 1:
            spec.append(("s", para_pause if k in para_after else sent_pause))
    spec.append(("s", 0.1))
    return _build(spec, rate), truth


def test_alignment_survives_a_slow_intro_without_drifting():
    # 2026-10-09 『칼의 노래』: 도입 장면을 천천히 읽자 예상 위치(글자 비례)가 실제보다 앞서 문장 중간 숨을 문장
    # 끝으로 잡았고, 두 번째 문장부터 자막이 말보다 앞섰다. 장면 1 은 0.12초/자, 장면 2 는 0.08초/자로 읽힌다.
    slow, fast = 0.12, 0.08
    s1 = [[20 * slow], [14 * slow, ("s", 0.3), 16 * slow], [12 * slow, ("s", 0.3), 12 * slow], [22 * slow]]
    s2 = [[18 * fast, ("s", 0.3), 10 * fast], [25 * fast], [12 * fast, ("s", 0.3), 14 * fast], [20 * fast]]
    pcm, truth = _speech(s1 + s2, para_after={3})
    weights = [[20, 30, 24, 22], [28, 25, 26, 20]]
    res = g.split_chunk(pcm, 24000, weights)
    assert res is not None and all(r is not None for r in res)
    got = _secs([p for r in res for p in r])
    want = [t + (0.04 if i in (0, len(truth) - 1) else 0) for i, t in enumerate(truth)]
    assert got == pytest.approx(want, abs=0.03)


def test_alignment_keeps_next_sentence_first_word_after_dramatic_pause():
    # "그런데, … 이 병력을 넘겨받은 사람은" 처럼 다음 문장 첫 단어 뒤에 문장 끝만큼 긴 쉼이 와도, 첫 단어를 앞
    # 문장 끝에 붙이지 않는다(조각 끝의 '긴 숨 + 짧은 한 단어' 는 벌점).
    sents = [[2.4], [0.45, ("s", 0.55), 2.2], [2.0]]
    pcm, truth = _speech(sents, sent_pause=0.5)
    pieces = g.split_sentences(pcm, 24000, [30, 34, 25])
    got = _secs(pieces)
    assert got[1] == pytest.approx(truth[1], abs=0.03)          # 문장 2 = 첫 단어 + 극적 쉼 + 나머지


def test_split_chunk_flags_a_scene_whose_rates_cannot_fit():
    # 장면 2 의 둘째 문장은 원고상 길지만 소리는 아주 짧다(모델이 건너뛰었거나 붙여 읽음) → 그 장면만 다시 합성
    pcm, _ = _speech([[2.0], [2.2], [2.1], [0.3], [2.0]], para_after={1})
    res = g.split_chunk(pcm, 24000, [[25, 27], [26, 30, 25]])
    assert res is not None and res[0] is not None and res[1] is None


def test_sentence_cuts_picks_sentence_pauses_for_whole_audio():
    pcm, truth = _speech([[1.2, ("s", 0.2), 1.0], [1.5]], sent_pause=0.6)
    spans = g.sentence_cuts(pcm, 24000, [28, 19])
    assert len(spans) == 1
    a, b = spans[0]
    assert a == pytest.approx(0.1 + 2.4, abs=0.02) and b - a == pytest.approx(0.6, abs=0.02)
    assert g.sentence_cuts(pcm, 24000, [40]) is None


def test_split_chunk_reports_worst_rate_ratios_for_diagnosis():
    pcm, _ = _speech([[2.0], [2.2], [2.1], [0.3], [2.0]], para_after={1})
    stats = {}
    g.split_chunk(pcm, 24000, [[25, 27], [26, 30, 25]], stats)
    assert stats["min_ratio"] < 0.65 and stats["max_ratio"] >= 1.0      # 0.3초짜리 30자 문장이 가장 벗어난다
