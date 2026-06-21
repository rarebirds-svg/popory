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


def test_normalize_dash_separator_to_comma():
    from popory_content.tts import _normalize_for_tts
    # 구분용 하이픈(앞뒤 공백)을 Chirp3-HD가 "갑작스러운 끊김"으로 읽어 어색 → 쉼표로
    assert _normalize_for_tts("현명한 투자자 - 벤저민 그레이엄") == "현명한 투자자, 벤저민 그레이엄"
    # em·en 대시도 동일
    assert _normalize_for_tts("투자—위험") == "투자, 위험"
    assert _normalize_for_tts("투자–위험") == "투자, 위험"


def test_normalize_ellipsis_to_comma():
    from popory_content.tts import _normalize_for_tts
    # 말줄임표를 과한 "망설임"으로 연기 → 쉼표 한 박자로
    assert _normalize_for_tts("그래서… 결국 투자했다.") == "그래서, 결국 투자했다."
    assert _normalize_for_tts("그래서... 결국 투자했다.") == "그래서, 결국 투자했다."


def test_normalize_strips_quotes_keep_content():
    from popory_content.tts import _normalize_for_tts
    assert _normalize_for_tts('그는 "투자하라"고 했다.') == "그는 투자하라고 했다."
    assert _normalize_for_tts("「현명한 투자자」를 읽다.") == "현명한 투자자를 읽다."
    assert _normalize_for_tts("‘안전마진’이 핵심이다.") == "안전마진이 핵심이다."


def test_normalize_colon_semicolon_not_between_digits():
    from popory_content.tts import _normalize_for_tts
    assert _normalize_for_tts("결론: 투자하라.") == "결론, 투자하라."
    assert _normalize_for_tts("이유는 셋이다; 첫째.") == "이유는 셋이다, 첫째."
    # 숫자 사이 콜론(시간·비율)은 보존
    assert _normalize_for_tts("오후 3:00에 만난다.") == "오후 3:00에 만난다."
    assert _normalize_for_tts("비율은 2:1이다.") == "비율은 2:1이다."


def test_normalize_slash_not_between_digits():
    from popory_content.tts import _normalize_for_tts
    assert _normalize_for_tts("주식/채권 비중") == "주식 채권 비중"
    # 숫자 사이 슬래시(날짜·분수)는 보존
    assert _normalize_for_tts("2024/06/21 발표") == "2024/06/21 발표"


def test_normalize_middot_and_ampersand():
    from popory_content.tts import _normalize_for_tts
    assert _normalize_for_tts("투자·금융 시장") == "투자, 금융 시장"
    assert _normalize_for_tts("리스크 & 리턴") == "리스크 리턴"


def test_normalize_tilde_range_and_plain():
    from popory_content.tts import _normalize_for_tts
    # 숫자 범위 틸드 → "에서", 그 외 틸드는 제거
    assert _normalize_for_tts("3~5년 투자") == "3에서 5년 투자"
    assert _normalize_for_tts("좋아요~ 시작합니다.") == "좋아요 시작합니다."


def test_normalize_parens_drop_keep_particle():
    from popory_content.tts import _normalize_for_tts
    # 괄호 제거: 여는 괄호 앞은 띄우고, 닫는 괄호 뒤 조사는 앞말에 붙여 읽게
    assert _normalize_for_tts("투자(주식)는 위험하다.") == "투자 주식는 위험하다."


def test_normalize_strips_markdown_symbols():
    from popory_content.tts import _normalize_for_tts
    assert _normalize_for_tts("**중요** 핵심 #포인트 > 인용") == "중요 핵심 포인트 인용"


def test_normalize_leaves_plain_text_and_commas():
    from popory_content.tts import _normalize_for_tts
    # 일반 문장·나열 쉼표·마침표·물음표는 그대로
    assert _normalize_for_tts("안녕하세요. 반갑습니다?") == "안녕하세요. 반갑습니다?"
    assert _normalize_for_tts("사과, 배, 감을 샀다.") == "사과, 배, 감을 샀다."


def test_split_for_pauses_applies_normalization():
    from popory_content.tts import _split_for_pauses
    # 정규화가 합성 파이프라인에 실제로 적용된다 + 천 단위 콤마 보존과 공존
    out = _split_for_pauses("현명한 투자자 - 그레이엄. 회원이 1,700명 늘었다.")
    assert "투자자, 그레이엄." in out
    assert "1700명" in out
    assert "[pause long]" in out
    assert " - " not in out


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
