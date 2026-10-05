# 발음 사전 — 확인된 영문 약어만 독음으로 바꾸고, 다른 단어의 일부는 건드리지 않으며, 자막(원문)은 그대로 둔다.
import pytest

from popory_content import pronunciation
from popory_content.tts import _prep_text, _to_ssml, spoken_text
from popory_content.video import _split_sentences


@pytest.mark.parametrize("text,want", [
    ("CEO 가 말했다", "씨이오 가 말했다"),
    ("CEO가 말했다", "씨이오가 말했다"),                 # 한글 조사가 붙어도 치환한다
    ("SAT 점수", "에스에이티 점수"),
    ("MIT 출신", "엠아이티 출신"),
    ("TBWA 의 광고", "티비더블유에이 의 광고"),
    ("A vs B", "A 대 B"),
])
def test_dictionary_terms_are_read_as_hangul(text, want):
    assert spoken_text(text) == want


def test_ampersand_terms_are_replaced_before_the_ampersand_becomes_aen():
    """회귀: 사전이 "&" 정규화보다 늦으면 "S앤P" 가 된다(tts.py 주석은 에스앤피를 기대했다)."""
    assert spoken_text("S&P 500 과 R&D 비중") == "에스앤피 오백 과 알앤디 비중"
    assert spoken_text("S&P500 지수") == "에스앤피오백 지수"


def test_ampersand_terms_not_in_the_dictionary_keep_the_generic_rule():
    assert spoken_text("AT&T 와 Q&A") == "AT앤T 와 Q앤A"


@pytest.mark.parametrize("text", ["AAA 등급", "CEOS 가 모였다", "ACEO", "SATURN", "MITT", "ADVS"])
def test_terms_inside_other_words_are_left_alone(text):
    assert spoken_text(text) == text


def test_acronyms_are_case_sensitive_but_vs_is_not():
    assert spoken_text("ceo 와 sat") == "ceo 와 sat"          # 소문자 sat 는 영어 단어일 수 있다
    assert spoken_text("A VS B, a Vs b, c vs d") == "A 대 B, a 대 b, c 대 d"


def test_vs_with_period_does_not_split_the_sentence():
    """vs. 의 마침표를 문장 끝으로 보면 클립이 둘로 갈라지고 0.7초 정적이 들어간다."""
    assert _split_sentences("A vs. B 의 대결입니다. 다음 문장입니다.") == ["A vs. B 의 대결입니다.", "다음 문장입니다."]
    assert spoken_text("A vs. B 의 대결입니다.") == "A 대 B 의 대결입니다."     # 마침표까지 함께 치환
    assert _split_sentences("끝입니다. 다음 문장.") == ["끝입니다.", "다음 문장."]   # 일반 문장 분리는 그대로


def test_subtitles_keep_the_original_text_only_the_voice_changes():
    """사전은 합성 직전(_prep_text)에서만 적용한다 — 문장 원문(자막)은 건드리지 않는다."""
    sent = "CEO가 S&P 지수를 봤다."
    assert _split_sentences(sent) == [sent]
    assert "씨이오가 에스앤피" in spoken_text(sent)


def test_ssml_path_uses_the_same_dictionary():
    assert _to_ssml(_prep_text("CEO와 S&P")) == "<speak>씨이오와 에스앤피</speak>"


def test_every_entry_is_actually_applied_and_longer_keys_win():
    for term, reading in pronunciation.PRONUNCIATIONS.items():
        assert pronunciation.apply_pronunciations(f"x {term} y") == f"x {reading} y"
    assert pronunciation.apply_pronunciations("") == ""


# --- SAVERS·AA: 실제 대본(scripts_34.json)의 문장으로 확인 -------------------------------------------------------
@pytest.mark.parametrize("text,want", [
    ("투병 중에도 그는 할 수 있는 만큼 SAVERS 루틴을 이어갔습니다.", "투병 중에도 그는 할 수 있는 만큼 세이버스 루틴을 이어갔습니다."),
    ("핵심은 SAVERS, 침묵과 확언, 시각화와 운동, 독서와 쓰기 여섯 가지인데요.",
     "핵심은 세이버스, 침묵과 확언, 시각화와 운동, 독서와 쓰기 여섯 가지인데요."),
    ("두히그는 익명의 알코올중독자들 모임, 이른바 AA의 사례로 이 믿음의 힘을 설명합니다.",
     "두히그는 익명의 알코올중독자들 모임, 이른바 에이에이의 사례로 이 믿음의 힘을 설명합니다."),
    ("AA의 프로그램 자체는 과학적으로 완벽하지 않습니다.", "에이에이의 프로그램 자체는 과학적으로 완벽하지 않습니다."),
])
def test_savers_and_aa_from_real_scripts(text, want):
    assert spoken_text(text) == want


def test_savers_intro_sentence_is_redundant_but_not_wrong():
    """대본이 스스로 "세이버스, 곧 SAVERS" 라고 소개하는 문장 — 사전 적용 뒤 "세이버스, 곧 세이버스" 가 된다.
    어색하지만 틀린 소리는 아니다(읽는 법은 이미 같다). 대본 생성 쪽에서 줄일 문제라 여기선 동작만 고정한다."""
    assert spoken_text("각 단어의 앞 글자를 따서 세이버스, 곧 SAVERS라는 이름을 붙였습니다.") \
        == "각 단어의 앞 글자를 따서 세이버스, 곧 세이버스라는 이름을 붙였습니다."


@pytest.mark.parametrize("text", [
    "AA 등급 회사채", "AA등급 채권", "AA급 신용", "신용등급은 AA+ 입니다", "AA- 로 강등", "AAA 등급",
])
def test_aa_credit_ratings_are_not_read_as_the_organization(text):
    """채권 신용등급 AA 는 "더블에이" 라 단체명 독음(에이에이)을 붙이면 틀린다 — 이 채널은 투자 책도 다룬다."""
    assert "에이에이" not in spoken_text(text)


def test_aa_group_is_read_even_next_to_a_particle_or_comma():
    assert spoken_text("AA, 즉 모임") == "에이에이, 즉 모임"
    assert spoken_text("AA가 시작됐다") == "에이에이가 시작됐다"


def test_read_initials_spells_name_initials():
    from popory_content.pronunciation import read_initials
    assert read_initials("E.H. 카는") == "이 에이치 카는"
    assert read_initials("피터 F. 드러커") == "피터 에프 드러커"
    assert read_initials("J.R.R. 톨킨과 C. S. 루이스") == "제이 알 알 톨킨과 씨 에스 루이스"
    assert read_initials("J.K. Rowling") == "제이 케이 Rowling"
    # 이니셜이 아니면 그대로 — 약어(CEO.)·문장 끝 대문자 뒤 영문 소문자·숫자
    assert read_initials("그는 CEO. 그리고") == "그는 CEO. 그리고"
    assert read_initials("A. 1번") == "A. 1번"


def test_spoken_text_reads_initials_without_sentence_break():
    from popory_content.tts import spoken_text
    assert spoken_text("E.H. 카는 말했습니다.") == "이 에이치 카는 말했습니다."
