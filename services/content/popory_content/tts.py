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


def _split_for_pauses(text: str) -> str:
    """문장 끝은 [pause long]로 한 템포 쉬게 한다. 문장 안의 쉼표는 콤마 그대로 둬
    자연스러운 짧은 호흡만 만들고 강제 쉼 토큰은 넣지 않는다(강제 [pause]는 Chirp3-HD가
    "어·으·응" 추임새로 채우는 원인). 문장 앞 간투사(음·어·아…)는 제거.
    리터럴 대괄호는 제거(마크업 오인 방지)."""
    text = text.replace("[", "").replace("]", "")
    text = _GROUP_COMMA.sub("", text)             # 천 단위 콤마 제거(1,700 → 1700)
    text = _normalize_for_tts(text)               # 특수문자 → 자연 운율(대시·말줄임표·따옴표 등)
    parts = [p.strip() for p in _SENT.split(text.strip()) if p.strip()]
    if not parts:
        return text.strip()
    out = []
    for p in parts:
        p = (_FILLER.sub("", p).strip() or p)   # 문장 앞 간투사 제거(전부 지워지면 원문 유지)
        out.append(p)
    return " [pause long] ".join(out)             # 문장 끝 더 긴 호흡


def synthesize(text: str, voice: str = "ko-KR-Chirp3-HD-Aoede") -> bytes | None:
    key = os.environ.get("GOOGLE_TTS_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            f"{TTS_URL}?key={key}",
            json={
                "input": {"markup": _split_for_pauses(text)},
                "voice": {"languageCode": LANGUAGE, "name": voice},
                "audioConfig": {"audioEncoding": "MP3", "speakingRate": 0.96},
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
