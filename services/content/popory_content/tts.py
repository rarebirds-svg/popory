# Google Cloud Text-to-Speech 로 한국어 자연 음성 합성. 키 없거나 실패하면 None(호출측 say 폴백).
import base64
import os
import re

import requests

TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
LANGUAGE = "ko-KR"

_SENT = re.compile(r"(?<=[.?!])\s+")
# 천 단위 구분 콤마(숫자-콤마-숫자)는 쉼표 호흡 대상이 아니다 — 1,700 을 통째로(천칠백) 읽게 제거
_GROUP_COMMA = re.compile(r"(?<=\d)[,，](?=\d)")
# 문장 앞 의미 없는 간투사/추임새: 음·흠(허밍, 공백만으로도) 또는 어·아·에(쉼표 동반 시)
_FILLER = re.compile(r"^\s*(?:음+|흠+|어+|아+|에+)\s*,\s*|^\s*(?:음+|흠+)\s+")

# --- TTS 직전 특수문자 정규화 ---
# Chirp3-HD는 문장부호를 운율로 해석한다(하이픈="갑작스러운 끊김", 말줄임표="망설임").
# 운율 목록에 없는 기호는 그대로 읽히거나 튄다. [pause] 토큰은 새로 넣지 않고
# (콤마마다 토큰은 "어/으/응" 추임새 유발) 진짜 문장부호로 치환해 정상 운율을 타게 한다.
_QUOTES = re.compile(r"[\"'‘’“”「」『』《》〈〉]")           # 따옴표류 → 제거(내용 유지)
_ELLIPSIS = re.compile(r"\.{3,}|…+")                       # 말줄임표 → 쉼표
_DASH_SEP = re.compile(r"\s*[—–]\s*|\s+-\s+")              # 구분용 대시 → 쉼표
_TILDE_RANGE = re.compile(r"(?<=\d)\s*[~〜]\s*(?=\d)")     # 숫자 범위 틸드 → "에서"
_TILDE = re.compile(r"[~〜]")                              # 그 외 틸드 → 제거
_MIDDOT = re.compile(r"\s*·\s*")                           # 가운뎃점(나열) → 쉼표
_COLON = re.compile(r"(?<!\d)\s*[:;]\s*|\s*[:;]\s*(?!\d)")  # 숫자 사이 아닌 콜론·세미콜론 → 쉼표
_SLASH = re.compile(r"(?<!\d)\s*/\s*|\s*/\s*(?!\d)")       # 숫자 사이 아닌 슬래시 → 공백
_AMP = re.compile(r"\s*&\s*")                              # 앰퍼샌드 → 공백
_OPEN_PAREN = re.compile(r"\s*[(（]\s*")                    # 여는 괄호 → 공백(앞말과 띄움)
_CLOSE_PAREN = re.compile(r"\s*[)）]")                      # 닫는 괄호 → 제거(뒤 조사 붙임)
_SYMBOLS = re.compile(r"[*#`>_|→⇒↔•]")                     # 마크다운·기호 잔여물 → 제거
_MULTI_COMMA = re.compile(r"\s*,(?:\s*,)+")                # 중복 쉼표 → 하나
_SPACE_COMMA = re.compile(r"\s+,")                         # 쉼표 앞 공백 제거
_MULTI_SPACE = re.compile(r"[ \t]{2,}")                    # 중복 공백 → 하나


def _normalize_for_tts(text: str) -> str:
    """합성 직전 특수문자를 자연스러운 한국어 운율로 정규화한다."""
    text = _QUOTES.sub("", text)
    text = _ELLIPSIS.sub(", ", text)
    text = _DASH_SEP.sub(", ", text)
    text = _TILDE_RANGE.sub("에서 ", text)
    text = _TILDE.sub("", text)
    text = _MIDDOT.sub(", ", text)
    text = _COLON.sub(", ", text)
    text = _SLASH.sub(" ", text)
    text = _AMP.sub(" ", text)
    text = _OPEN_PAREN.sub(" ", text)
    text = _CLOSE_PAREN.sub("", text)
    text = _SYMBOLS.sub("", text)
    # 치환으로 생긴 중복 부호·공백 정리
    text = _MULTI_COMMA.sub(",", text)
    text = _SPACE_COMMA.sub(",", text)
    text = _MULTI_SPACE.sub(" ", text)
    return text.strip(" ,")


# 숫자 토큰 = 정수, 또는 .:/로 이어진 복합수(소수 3.5·시간 3:00·날짜 2024/06).
# 토큰에 .:/가 섞였으면 소수·시간·날짜이므로 모델에 맡기고, 순수 정수만 카디널로 감싼다.
# (구분자가 숫자 사이일 때만 토큰에 포함되므로 문장 끝 마침표 "1976."은 정수로 인식.)
_NUM_TOKEN = re.compile(r"\d+(?:[.:/]\d+)*")

# 콤마 뒤 호흡(무음) 길이(ms). Chirp3-HD가 콤마를 너무 급히 넘어가 SSML <break>로 강제한다.
# <break>는 실제 무음 삽입이라 과거 [pause] 마크업의 "어/으/응" 추임새 부작용이 없다.
# POPORY_TTS_COMMA_BREAK_MS로 튜닝(0이면 비활성).
COMMA_BREAK_MS = int(os.environ.get("POPORY_TTS_COMMA_BREAK_MS", "175"))
_COMMA = re.compile(r",\s*")


_SINO_DIGITS = "영일이삼사오육칠팔구"
_SINO_SMALL = ["", "십", "백", "천"]      # 4자리 그룹 내 자리 단위
_SINO_BIG = ["", "만", "억", "조", "경"]   # 4자리 그룹 단위


def _sino_4(n: int) -> str:
    """0~9999 → 한자어 수사. 십·백·천 앞의 '일'은 생략(일십→십)."""
    out = []
    for pos in range(3, -1, -1):
        d = (n // (10 ** pos)) % 10
        if d == 0:
            continue
        if d == 1 and pos >= 1:
            out.append(_SINO_SMALL[pos])
        else:
            out.append(_SINO_DIGITS[d] + _SINO_SMALL[pos])
    return "".join(out)


def _sino_korean(n: int) -> str:
    """비음수 정수 → 한자어 수사 평문(16→십육, 1700→천칠백). 0은 '영'."""
    if n == 0:
        return "영"
    groups = []
    i = 0
    while n > 0:
        groups.append((n % 10000, i))
        n //= 10000
        i += 1
    parts = []
    for val, gi in reversed(groups):
        if val == 0:
            continue
        chunk = _sino_4(val)
        if val == 1 and gi == 1:      # '일만'은 '만'으로 줄인다(억·조 이상은 일 유지)
            chunk = ""
        parts.append(chunk + _SINO_BIG[gi])
    return "".join(parts)


def _read_number(m: "re.Match[str]") -> str:
    """숫자 토큰을 한자어 수사 평문으로 치환. say-as 경계가 없어 뒤 글자와 끊기지 않는다.
    소수·시간·날짜(. : /)와 변환기 범위 밖은 원문 유지(모델 정규화에 맡김)."""
    tok = m.group()
    if any(c in tok for c in ".:/"):
        return tok
    try:
        n = int(tok)
    except ValueError:
        return tok
    if n >= 10 ** 20:                 # 경 그룹 초과 → 변환 생략
        return tok
    return _sino_korean(n)


def _prep_text(text: str) -> str:
    """합성 직전 텍스트 정리 — 리터럴 대괄호·천 단위 콤마·특수문자·문장 앞 간투사를
    제거/정규화하고, 문장은 공백으로 잇는다. 문장 사이 호흡은 video.py의 무음 갭이
    담당하므로 pause 토큰은 넣지 않는다(markup→ssml 전환)."""
    text = text.replace("[", "").replace("]", "")
    text = _GROUP_COMMA.sub("", text)             # 천 단위 콤마 제거(1,700 → 1700)
    text = _normalize_for_tts(text)               # 특수문자 → 자연 운율(대시·말줄임표·따옴표 등)
    parts = [p.strip() for p in _SENT.split(text.strip()) if p.strip()]
    if not parts:
        return text.strip()
    out = [(_FILLER.sub("", p).strip() or p) for p in parts]  # 문장 앞 간투사 제거
    return " ".join(out)


def _to_ssml(text: str) -> str:
    """정리된 텍스트를 SSML로 감싼다. XML 이스케이프 후 순수 정수를 한자어 수사 평문으로
    바꾼다(16→십육). say-as 태그를 쓰지 않아 "1차"가 "일 (끊김) 차"로 갈라지지 않고
    "일차"로 매끄럽게 이어진다."""
    esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    esc = _NUM_TOKEN.sub(_read_number, esc)
    if COMMA_BREAK_MS > 0:
        # 콤마는 보존하고 그 뒤에 무음을 넣어 한 박자 호흡하게 한다.
        esc = _COMMA.sub(f',<break time="{COMMA_BREAK_MS}ms"/> ', esc)
    return f"<speak>{esc}</speak>"


def synthesize(text: str, voice: str = "ko-KR-Chirp3-HD-Aoede") -> bytes | None:
    key = os.environ.get("GOOGLE_TTS_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            f"{TTS_URL}?key={key}",
            json={
                "input": {"ssml": _to_ssml(_prep_text(text))},
                "voice": {"languageCode": LANGUAGE, "name": voice},
                "audioConfig": {"audioEncoding": "MP3", "speakingRate": 1.06},
            },
            timeout=30,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    audio = resp.json().get("audioContent")
    if not audio:
        return None
    return base64.b64decode(audio)
