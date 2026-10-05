# 발음 사전 — TTS 가 잘못 읽거나 그대로 흘리는 영문 약어·고유명사를 합성 직전에 한글 독음으로 바꾼다.
#
# 왜 SSML <sub> 가 아니라 텍스트 치환인가: Chirp3-HD 가 <sub> 를 받는지 확인할 수 없고, 텍스트 치환은 모든 음성에서
# 동작한다. 치환은 tts._prep_text 안(합성 직전)에서만 하므로 **자막에는 원문(CEO)이 그대로 남고 음성만 "씨이오"** 가 된다.
# 자막 타이밍 계산(spoken_text)도 같은 경로라 독음 길이로 계산된다.
#
# 규칙 — 키는 **대본에 나오는 표기**, 값은 **읽어야 할 한글 독음**이다. names.py 와 같은 규율을 따른다:
# 새 항목은 **대본에서 실제로 그 뜻으로 쓰였는지 확인한 뒤에만** 넣는다. 추측으로 넣으면 맞게 읽던 것을 틀리게 바꾼다.
# 확인 근거: SAVERS 는 대본이 스스로 "각 단어의 앞 글자를 따서 세이버스, 곧 SAVERS" 라고 읽는 법을 알려 준다(미라클 모닝, 5회).
# AA 는 "익명의 알코올중독자들 모임, 이른바 AA"(Alcoholics Anonymous) — 단, 채권 신용등급 AA 는 "더블에이" 라 제외한다(아래).
#
# 영문 약어는 대소문자를 구분한다(SAT 와 sat). 앞뒤가 영문자이면 다른 단어의 일부라 치환하지 않는다 —
# 뒤에 한글 조사가 붙는 건(CEO가) 영문자가 아니므로 치환한다. "&" 가 든 항목(S&P)은 tts 의 특수문자 정규화
# ("&" → "앤")보다 **먼저** 적용돼야 "에스앤피" 가 된다(안 그러면 "S앤P" 가 된다) — 그래서 _prep_text 맨 앞에서 부른다.
import re

PRONUNCIATIONS: dict[str, str] = {
    "CEO": "씨이오",
    "SAT": "에스에이티",
    "MIT": "엠아이티",
    "TBWA": "티비더블유에이",
    "S&P": "에스앤피",
    "R&D": "알앤디",
    "vs": "대",
    "SAVERS": "세이버스",
    "AA": "에이에이",
}
# 대소문자를 가리지 않는 항목(Vs., VS). 나머지는 정확히 일치할 때만.
IGNORE_CASE = {"vs"}
# 뒤에 마침표가 붙을 수 있는 약어(vs.). 마침표까지 함께 치환해야 "A vs. B" 가 문장 끝으로 오해되지 않는다.
OPTIONAL_DOT = {"vs"}


# 뒤따르는 말이 이것이면 치환하지 않는다. AA 는 단체명(에이에이)이지만 신용등급 AA(AA 등급·AA급·AA+)는 "더블에이" 로 읽는다 —
# 이 채널은 투자 책도 다뤄서 등급 표기가 나올 수 있다. 모든 AA 를 에이에이로 고정하면 그때 틀린다.
NOT_FOLLOWED_BY = {"AA": r"\s*(?:등급|급|\+|-)"}
# 화면(어드민)에 보여 줄 비고.
NOTES = {
    "vs": "대소문자 무시 · vs. 의 마침표 포함",
    "AA": "익명의 알코올중독자들 모임. 신용등급(AA 등급·AA급·AA+)은 제외",
    "SAVERS": "미라클 모닝의 여섯 가지 습관(대본이 세이버스로 읽는다고 밝힘)",
}


def _compile() -> list[tuple[re.Pattern[str], str]]:
    # 긴 키 먼저 — 짧은 키가 긴 키의 일부를 먼저 먹는 걸 막는다.
    out = []
    for term in sorted(PRONUNCIATIONS, key=len, reverse=True):
        pat = (r"(?<![A-Za-z])" + re.escape(term) + (r"\.?" if term in OPTIONAL_DOT else "") + r"(?![A-Za-z])"
               + (f"(?!{NOT_FOLLOWED_BY[term]})" if term in NOT_FOLLOWED_BY else ""))
        out.append((re.compile(pat, re.IGNORECASE if term in IGNORE_CASE else 0), PRONUNCIATIONS[term]))
    return out


_PATTERNS = _compile()


def apply_pronunciations(text: str) -> str:
    """사전에 있는 표기를 독음으로 바꾼다. 매칭이 없으면 원문 그대로."""
    if not text:
        return text
    for pat, reading in _PATTERNS:
        text = pat.sub(reading, text)
    return text


# --- 사람 이름 이니셜(E.H. 카·피터 F. 드러커·J.R.R. 톨킨) ---
# 사전 항목이 아니라 규칙이다 — 대문자 한 글자 + 마침표가 이름(한글, 또는 영문 대문자로 시작하는 단어) 앞에 오면
# 이니셜로 보고 알파벳 이름으로 읽는다("이 에이치 카"). 마침표를 남기면 TTS 가 문장 끝으로 읽어 이름 중간에서
# 끊긴 억양·숨이 생기고, 문장 분리(video._split_sentences)와 자막 싱크도 함께 어긋났다(2026-10-05 E.H. 카 영상).
LETTER_NAMES = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프", "G": "지", "H": "에이치",
    "I": "아이", "J": "제이", "K": "케이", "L": "엘", "M": "엠", "N": "엔", "O": "오", "P": "피",
    "Q": "큐", "R": "알", "S": "에스", "T": "티", "U": "유", "V": "브이", "W": "더블유", "X": "엑스",
    "Y": "와이", "Z": "제트",
}
_INITIALS = re.compile(r"(?<![A-Za-z.])((?:[A-Z]\.\s?){1,4})(?=\s*(?:[가-힣]|[A-Z][a-z]))")


def read_initials(text: str) -> str:
    """"E.H. 카는" → "이 에이치 카는". 이니셜이 아니면 그대로."""
    if not text:
        return text
    return _INITIALS.sub(lambda m: " ".join(LETTER_NAMES[c] for c in re.findall(r"[A-Z]", m.group(1))) + " ",
                         text).replace("  ", " ")
