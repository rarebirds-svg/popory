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


def test_normalize_strips_non_hangul_paren_gloss():
    from popory_content.tts import _normalize_for_tts
    # 한자·영어 괄호 주석은 앞말과 같은 독음으로 다시 읽혀 이중 발음 → 통째 제거(한 번만 읽음)
    assert _normalize_for_tts("구방심(求放心)을 되찾다.") == "구방심을 되찾다."
    assert _normalize_for_tts("생어우환(生於憂患).") == "생어우환."
    assert _normalize_for_tts("인공지능(AI)이 온다.") == "인공지능이 온다."
    # 한글이 든 괄호는 내용 유지(괄호만 벗김) — 기존 동작 보존
    assert _normalize_for_tts("그는(웃으며) 말했다.") == "그는 웃으며 말했다."


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


def test_sino_korean_readings():
    from popory_content.tts import _sino_korean
    assert _sino_korean(0) == "영"
    assert _sino_korean(1) == "일"
    assert _sino_korean(16) == "십육"
    assert _sino_korean(100) == "백"
    assert _sino_korean(1700) == "천칠백"
    assert _sino_korean(1976) == "천구백칠십육"
    assert _sino_korean(2024) == "이천이십사"
    assert _sino_korean(10000) == "만"          # '일만' → '만'
    assert _sino_korean(21700) == "이만천칠백"


def test_to_ssml_converts_integer_to_hangul():
    from popory_content.tts import _to_ssml
    # 정수를 한자어 수사 평문으로 — 16을 "십육"으로
    out = _to_ssml("16년 전 이야기")
    assert out == "<speak>십육년 전 이야기</speak>"


def test_to_ssml_number_glued_to_hangul_has_no_break():
    from popory_content.tts import _to_ssml
    # 숫자+한글이 붙으면 say-as 경계 없이 매끄럽게 — "일차 이차 삼차"
    out = _to_ssml("1차 2차 3차")
    assert out == "<speak>일차 이차 삼차</speak>"
    assert "say-as" not in out and "<break" not in out


def test_to_ssml_converts_thousands():
    from popory_content.tts import _to_ssml
    out = _to_ssml("회원이 1700명 늘었다.")
    assert "천칠백명" in out


def test_to_ssml_converts_sentence_final_integer():
    from popory_content.tts import _to_ssml
    # 문장 끝 마침표가 붙은 정수도 변환(소수점과 구분)
    out = _to_ssml("그는 1976.")
    assert "천구백칠십육." in out


def test_to_ssml_skips_decimal():
    from popory_content.tts import _to_ssml
    # 소수는 변환하지 않고 모델에 맡긴다(삼점오)
    out = _to_ssml("3.5% 상승")
    assert out == "<speak>3.5% 상승</speak>"


def test_to_ssml_skips_time_and_date():
    from popory_content.tts import _to_ssml
    # 시간(3:00)·날짜(2024/06/21) 형식은 숫자 가드로 건드리지 않고 원문 유지
    assert "3:00" in _to_ssml("오후 3:00에 만난다.")
    assert "2024/06/21" in _to_ssml("2024/06/21 발표")


def test_to_ssml_converts_date_components():
    from popory_content.tts import _to_ssml
    # 한국식 날짜는 숫자가 단위로 분리돼 각각 변환
    out = _to_ssml("2024년 6월 21일")
    assert "이천이십사년" in out
    assert "육월" in out
    assert "이십일일" in out


def test_to_ssml_inserts_break_after_multisyllable_comma():
    from popory_content.tts import _to_ssml
    # 다음절 나열 항목 뒤엔 호흡(<break>) — Chirp3-HD가 콤마를 급히 넘어가는 문제 보정
    out = _to_ssml("사과, 바나나, 감을 샀다.")
    assert out.count("<break") == 2
    assert "사과,<break" in out  # 콤마는 보존하고 그 뒤에 무음 삽입


def test_to_ssml_skips_break_for_single_syllable_list():
    from popory_content.tts import _to_ssml
    # 한 글자 나열(밥, 꽃, 산…)엔 break를 넣지 않는다 — 고립 단음절 받침이 뭉개짐
    out = _to_ssml("밥, 꽃, 산, 강, 땀.")
    assert "<break" not in out
    assert out == "<speak>밥, 꽃, 산, 강, 땀.</speak>"


def test_to_ssml_break_only_after_multisyllable_in_mixed_list():
    from popory_content.tts import _to_ssml
    # 섞인 나열: 단음절 뒤엔 없음, 다음절 뒤엔 break
    out = _to_ssml("밥, 사과, 산.")
    assert "밥, 사과,<break" in out
    assert out.count("<break") == 1


def test_to_ssml_break_and_number_coexist():
    from popory_content.tts import _to_ssml
    out = _to_ssml("16년, 그리고 17년.")
    assert '십육년,<break time="175ms"/>' in out
    assert "십칠년." in out


def test_to_ssml_escapes_xml():
    from popory_content.tts import _to_ssml
    out = _to_ssml("5 < 10 & 자유")
    assert "&lt;" in out and "&amp;" in out
    assert "오 " in out and "십 " in out


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
    assert "십육" in ssml  # 숫자를 한자어 수사 평문으로 변환
    assert "markup" not in payload["input"]
    assert payload["audioConfig"]["speakingRate"] == 1.0
    assert payload["voice"]["name"] == "ko-KR-Chirp3-HD-Aoede"
