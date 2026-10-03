# 발음 사전 — TTS 가 잘못 읽거나 그대로 흘리는 영문 약어·고유명사를 합성 직전에 한글 독음으로 바꾼다.
#
# 왜 SSML <sub> 가 아니라 텍스트 치환인가: Chirp3-HD 가 <sub> 를 받는지 확인할 수 없고, 텍스트 치환은 모든 음성에서
# 동작한다. 치환은 tts._prep_text 안(합성 직전)에서만 하므로 **자막에는 원문(CEO)이 그대로 남고 음성만 "씨이오"** 가 된다.
# 자막 타이밍 계산(spoken_text)도 같은 경로라 독음 길이로 계산된다.
#
# 규칙 — 키는 **대본에 나오는 표기**, 값은 **읽어야 할 한글 독음**이다. names.py 와 같은 규율을 따른다:
# 새 항목은 **대본에서 실제로 그 뜻으로 쓰였는지 확인한 뒤에만** 넣는다. 추측으로 넣으면 맞게 읽던 것을 틀리게 바꾼다.
# (SAVERS·AA 는 책의 용어/뜻 확인 전이라 아직 넣지 않았다.)
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
}
# 대소문자를 가리지 않는 항목(Vs., VS). 나머지는 정확히 일치할 때만.
IGNORE_CASE = {"vs"}
# 뒤에 마침표가 붙을 수 있는 약어(vs.). 마침표까지 함께 치환해야 "A vs. B" 가 문장 끝으로 오해되지 않는다.
OPTIONAL_DOT = {"vs"}


def _compile() -> list[tuple[re.Pattern[str], str]]:
    # 긴 키 먼저 — 짧은 키가 긴 키의 일부를 먼저 먹는 걸 막는다.
    out = []
    for term in sorted(PRONUNCIATIONS, key=len, reverse=True):
        pat = r"(?<![A-Za-z])" + re.escape(term) + (r"\.?" if term in OPTIONAL_DOT else "") + r"(?![A-Za-z])"
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
