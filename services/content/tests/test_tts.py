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
    assert "[pause long]" in out  # 문장 구분 pause(한 템포)


def test_split_for_pauses_inserts_pause_markup():
    from popory_content.tts import _split_for_pauses
    out = _split_for_pauses("첫째 문장입니다. 둘째 문장이에요!")
    assert out == "첫째 문장입니다. [pause long] 둘째 문장이에요!"


def test_split_for_pauses_comma_is_plain_not_filler():
    from popory_content.tts import _split_for_pauses
    out = _split_for_pauses("사과와, 배 그리고, 감을 샀습니다.")
    # 문장 안의 쉼표는 콤마 그대로 둬 자연스러운 짧은 호흡만 — 강제 쉼 토큰([pause]) 삽입 금지
    # (강제 [pause]는 Chirp3-HD가 "어/으/응" 추임새로 채우는 원인)
    assert "[pause]" not in out
    assert "사과와, 배 그리고, 감을 샀습니다." in out


def test_split_for_pauses_comma_plain_but_sentence_break_pauses():
    from popory_content.tts import _split_for_pauses
    out = _split_for_pauses("그는, 천천히 말했다. 그리고 떠났다.")
    # 쉼표는 마크업 없이 콤마 그대로, 문장 끝에서만 [pause long]
    assert "그는, 천천히 말했다." in out
    assert "[pause long]" in out
    assert "[pause]" not in out and "[pause short]" not in out


def test_split_for_pauses_strips_leading_filler():
    from popory_content.tts import _split_for_pauses
    # 문장 앞 간투사(음·어·아) 제거
    assert _split_for_pauses("음, 그러니까 중요합니다.").startswith("그러니까")
    assert "음" not in _split_for_pauses("음 그래서 떠났다.")
    out = _split_for_pauses("첫 문장이다. 어, 둘째 문장이다.")
    assert "어," not in out and "둘째 문장이다" in out
    # 진짜 단어는 보존(어머니·아침)
    assert "어머니" in _split_for_pauses("어머니가 오셨다.")
    assert "아침" in _split_for_pauses("아침에 일어났다.")


def test_split_for_pauses_keeps_grouped_number_together():
    from popory_content.tts import _split_for_pauses
    # 천 단위 콤마(숫자-콤마-숫자)는 호흡을 넣지 않고 붙여 읽는다: 1,700 → 1700(천칠백)
    out = _split_for_pauses("회원이 1,700명 늘었다.")
    assert "1700명" in out
    assert "[pause]" not in out  # 천 단위 콤마는 쉼표 호흡 대상이 아니다


def test_split_for_pauses_grouped_number_multiple_commas():
    from popory_content.tts import _split_for_pauses
    out = _split_for_pauses("매출은 1,234,567원이다.")
    assert "1234567원" in out
    assert "[pause]" not in out


def test_split_for_pauses_list_comma_stays_plain():
    from popory_content.tts import _split_for_pauses
    # 나열 쉼표는 콤마 그대로(짧은 호흡) — 강제 쉼 토큰 없음
    out = _split_for_pauses("사과, 배를 샀다.")
    assert "사과, 배를 샀다." in out
    assert "[pause]" not in out


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
    assert "[pause long]" in payload["input"]["markup"]  # 문장 사이 pause
    assert payload["audioConfig"]["speakingRate"] == 0.96
    assert payload["voice"]["name"] == "ko-KR-Chirp3-HD-Aoede"
