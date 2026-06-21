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


def test_prep_text_strips_literal_brackets():
    from popory_content.tts import _prep_text
    out = _prep_text("[단독] 첫 문장입니다. 둘째 문장이에요.")
    # 내레이션의 리터럴 대괄호는 제거. pause 토큰은 더 이상 넣지 않는다(ssml 전환).
    assert "[단독]" not in out
    assert "단독 첫 문장입니다." in out
    assert "pause" not in out


def test_prep_text_joins_sentences_plain():
    from popory_content.tts import _prep_text
    # 문장 사이 호흡은 video.py의 무음 갭이 담당 — 텍스트엔 pause 토큰 없이 공백만
    out = _prep_text("첫째 문장입니다. 둘째 문장이에요!")
    assert out == "첫째 문장입니다. 둘째 문장이에요!"


def test_prep_text_comma_stays_plain():
    from popory_content.tts import _prep_text
    # 문장 안 쉼표는 콤마 그대로(짧은 호흡). 강제 쉼 토큰은 넣지 않는다.
    out = _prep_text("사과와, 배 그리고, 감을 샀습니다.")
    assert "pause" not in out
    assert "사과와, 배 그리고, 감을 샀습니다." in out


def test_prep_text_strips_leading_filler():
    from popory_content.tts import _prep_text
    # 문장 앞 간투사(음·어·아) 제거
    assert _prep_text("음, 그러니까 중요합니다.").startswith("그러니까")
    assert "음" not in _prep_text("음 그래서 떠났다.")
    out = _prep_text("첫 문장이다. 어, 둘째 문장이다.")
    assert "어," not in out and "둘째 문장이다" in out
    # 진짜 단어는 보존(어머니·아침)
    assert "어머니" in _prep_text("어머니가 오셨다.")
    assert "아침" in _prep_text("아침에 일어났다.")


def test_prep_text_keeps_grouped_number_together():
    from popory_content.tts import _prep_text
    # 천 단위 콤마(숫자-콤마-숫자)는 붙여 읽게 제거: 1,700 → 1700(천칠백)
    out = _prep_text("회원이 1,700명 늘었다.")
    assert "1700명" in out
    assert "pause" not in out


def test_prep_text_grouped_number_multiple_commas():
    from popory_content.tts import _prep_text
    out = _prep_text("매출은 1,234,567원이다.")
    assert "1234567원" in out


def test_prep_text_list_comma_stays_plain():
    from popory_content.tts import _prep_text
    out = _prep_text("사과, 배를 샀다.")
    assert "사과, 배를 샀다." in out


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


def test_prep_text_applies_normalization():
    from popory_content.tts import _prep_text
    # 정규화가 합성 파이프라인에 실제로 적용된다 + 천 단위 콤마 보존과 공존
    out = _prep_text("현명한 투자자 - 그레이엄. 회원이 1,700명 늘었다.")
    assert "투자자, 그레이엄." in out
    assert "1700명" in out
    assert " - " not in out


def test_to_ssml_wraps_integer_cardinal():
    from popory_content.tts import _to_ssml
    # 정수는 카디널(한자어 수사)로 강제 — 16을 "일육"이 아니라 "십육"으로 읽게
    out = _to_ssml("16년 전 이야기")
    assert out == '<speak><say-as interpret-as="cardinal">16</say-as>년 전 이야기</speak>'


def test_to_ssml_wraps_thousands():
    from popory_content.tts import _to_ssml
    out = _to_ssml("회원이 1700명 늘었다.")
    assert '<say-as interpret-as="cardinal">1700</say-as>명' in out


def test_to_ssml_wraps_sentence_final_integer():
    from popory_content.tts import _to_ssml
    # 문장 끝 마침표가 붙은 정수도 카디널로 감싼다(소수점과 구분)
    out = _to_ssml("그는 1976.")
    assert '<say-as interpret-as="cardinal">1976</say-as>.' in out


def test_to_ssml_skips_decimal():
    from popory_content.tts import _to_ssml
    # 소수는 say-as로 감싸면 깨지므로 모델에 맡긴다(삼점오)
    out = _to_ssml("3.5% 상승")
    assert "say-as" not in out
    assert out == "<speak>3.5% 상승</speak>"


def test_to_ssml_skips_time_and_date():
    from popory_content.tts import _to_ssml
    # 시간(3:00)·날짜(2024/06/21) 형식은 숫자 가드로 건드리지 않는다
    assert "say-as" not in _to_ssml("오후 3:00에 만난다.")
    assert "say-as" not in _to_ssml("2024/06/21 발표")


def test_to_ssml_wraps_date_components():
    from popory_content.tts import _to_ssml
    # 한국식 날짜는 숫자가 단위로 분리돼 각각 카디널로 정상 처리
    out = _to_ssml("2024년 6월 21일")
    assert '<say-as interpret-as="cardinal">2024</say-as>년' in out
    assert '<say-as interpret-as="cardinal">6</say-as>월' in out
    assert '<say-as interpret-as="cardinal">21</say-as>일' in out


def test_to_ssml_escapes_xml():
    from popory_content.tts import _to_ssml
    out = _to_ssml("5 < 10 & 자유")
    assert "&lt;" in out and "&amp;" in out
    assert '<say-as interpret-as="cardinal">5</say-as>' in out
    assert '<say-as interpret-as="cardinal">10</say-as>' in out


@responses.activate
def test_synthesize_uses_ssml_and_rate(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    responses.add(responses.POST, tts.TTS_URL,
                  json={"audioContent": base64.b64encode(b"x").decode()}, status=200)
    tts.synthesize("16년 동안 투자했다.", voice="ko-KR-Chirp3-HD-Aoede")
    import json as _json
    body = responses.calls[0].request.body
    payload = _json.loads(body if isinstance(body, str) else body.decode())
    ssml = payload["input"].get("ssml")  # markup 아니라 ssml 사용
    assert ssml and ssml.startswith("<speak>")
    assert '<say-as interpret-as="cardinal">16</say-as>' in ssml  # 숫자 카디널 강제
    assert "markup" not in payload["input"]
    assert payload["audioConfig"]["speakingRate"] == 0.96
    assert payload["voice"]["name"] == "ko-KR-Chirp3-HD-Aoede"
