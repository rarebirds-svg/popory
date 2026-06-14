# Google Cloud Text-to-Speech 로 한국어 자연 음성 합성. 키 없거나 실패하면 None(호출측 say 폴백).
import base64
import os
import re

import requests

TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
LANGUAGE = "ko-KR"

_SENT = re.compile(r"(?<=[.?!])\s+")
_COMMA = re.compile(r"\s*[,，]\s*")
# 문장 앞 의미 없는 간투사/추임새: 음·흠(허밍, 공백만으로도) 또는 어·아·에(쉼표 동반 시)
_FILLER = re.compile(r"^\s*(?:음+|흠+|어+|아+|에+)\s*,\s*|^\s*(?:음+|흠+)\s+")


def _split_for_pauses(text: str) -> str:
    """문장 끝은 [pause long], 쉼표 뒤는 [pause]로 한 템포 쉬게 한다(급하게 안 읽도록).
    문장 앞 간투사(음·어·아…)는 제거. 리터럴 대괄호는 제거(마크업 오인 방지)."""
    text = text.replace("[", "").replace("]", "")
    parts = [p.strip() for p in _SENT.split(text.strip()) if p.strip()]
    if not parts:
        return text.strip()
    out = []
    for p in parts:
        p = (_FILLER.sub("", p).strip() or p)   # 간투사 제거(전부 지워지면 원문 유지)
        p = _COMMA.sub(", [pause] ", p)          # 쉼표 뒤 호흡
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
