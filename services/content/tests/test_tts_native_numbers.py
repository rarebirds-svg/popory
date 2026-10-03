# 고유어 수사 — 단위에 따라 "한 권·세 가지·서른일곱 개" 로 읽는다. 대본 34건 스캔(2026-10)에서 나온 실사례와,
# 규칙을 그대로 적용하면 새로 틀리는 경우(개월·대·달러·제N권…)를 함께 고정한다.
import pytest

from popory_content.tts import _native_korean, _to_ssml, _prep_text, spoken_text


@pytest.mark.parametrize("n,want", [
    (1, "한"), (2, "두"), (3, "세"), (4, "네"), (5, "다섯"), (9, "아홉"),
    (10, "열"), (11, "열한"), (12, "열두"), (14, "열네"),
    (20, "스무"), (21, "스물한"), (24, "스물네"), (37, "서른일곱"), (99, "아흔아홉"),
])
def test_native_korean_forms(n, want):
    assert _native_korean(n) == want


@pytest.mark.parametrize("text,want", [
    # 스캔에서 확인된 실사례
    ("1권, 2권을 읽었다.", "한 권, 두 권을 읽었다."),
    ("3가지 원칙", "세 가지 원칙"),
    ("6가지와 7가지", "여섯 가지와 일곱 가지"),
    ("37개의 사례", "서른일곱 개의 사례"),
    ("3~5명이 참석했다.", "세 명에서 다섯 명이 참석했다."),
    # 시각·시간 — 요청서 빈도표엔 없었지만 같은 규칙으로 잡힌다
    ("3시 30분", "세 시 삼십분"),
    ("오전 7시에 일어난다", "오전 일곱 시에 일어난다"),
    ("24시간 동안", "스물네 시간 동안"),
    # 20 은 스무, 21 부터는 스물한
    ("20명과 21명", "스무 명과 스물한 명"),
    # 100 이상은 한자어, 단위와는 띄운다
    ("100개와 1,700명", "백 개와 천칠백 명"),
    ("83살", "여든세 살"),
    ("3번 말했다", "세 번 말했다"),
    ("3번째 시도", "세 번째 시도"),
    ("2달 전", "두 달 전"),
    ("3 가지", "세 가지"),                    # 이미 띄어 있으면 공백을 더 넣지 않는다
    ("10~20개", "열 개에서 스무 개"),
])
def test_native_numerals_before_counting_units(text, want):
    assert spoken_text(text) == want


@pytest.mark.parametrize("text,want", [
    # 월: 6월·10월만 예외, 나머지는 한자어 그대로
    ("6월과 10월 그리고 12월", "유월과 시월 그리고 십이월"),
    ("2025년 9월 5일", "이천이십오년 구월 오일"),
])
def test_months(text, want):
    assert spoken_text(text) == want


@pytest.mark.parametrize("text,want", [
    # 규칙을 그대로 적용하면 새로 틀리는 경우 — 한자어로 남아야 한다
    ("3개월 동안", "삼개월 동안"),               # 개월은 한자어. 고유어는 '달' 일 때만
    ("3개국", "삼개국"),
    ("3대 기업", "삼대 기업"),                   # 대는 목록에서 뺐다
    ("3달러", "삼달러"),                         # '달러' 의 달은 단위가 아니다
    ("1번 항목을 보라", "일번 항목을 보라"),       # 번호 이름
    ("제1권과 제3장", "제일권과 제삼장"),          # 서수(순서)는 한자어
    ("1차 2차 3차", "일차 이차 삼차"),
    ("16년 전", "십육년 전"),
    ("12% 올랐다", "십이퍼센트 올랐다"),
    ("30분 걸렸다", "삼십분 걸렸다"),
    ("83세의 노인", "팔십삼세의 노인"),
    ("3.5개", "삼점오개"),                       # 소수는 기존 규칙 그대로
    ("B2B 2대", "B이B 이대"),                    # 알파벳 바로 뒤 숫자는 기존 동작 유지
])
def test_units_that_must_stay_sino(text, want):
    assert spoken_text(text) == want


def test_zero_stays_sino():
    assert spoken_text("0명") == "영 명"


def test_ssml_path_uses_the_same_rule_as_subtitle_timing():
    """자막 타이밍(spoken_text)과 실제 합성(_to_ssml)이 같은 변환을 써야 길이 계산이 어긋나지 않는다."""
    for text in ("1권과 3가지", "3~5명", "6월 7시에 37개"):
        assert _to_ssml(_prep_text(text)) == f"<speak>{spoken_text(text)}</speak>"
