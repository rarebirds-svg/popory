# Google Cloud Text-to-Speech 로 한국어 자연 음성 합성. 키 없거나 실패하면 None(호출측 say 폴백).
import base64
import os
import re

import requests

TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
LANGUAGE = "ko-KR"

_SENT = re.compile(r"(?<=[.?!])\s+")


def _split_for_pauses(text: str) -> str:
    """문장 사이에 Chirp3-HD 네이티브 [pause short] 마크업을 끼워 호흡을 만든다.
    리터럴 대괄호는 마크업 오인을 막기 위해 제거한다."""
    text = text.replace("[", "").replace("]", "")
    parts = [p.strip() for p in _SENT.split(text.strip()) if p.strip()]
    return " [pause short] ".join(parts) if parts else text.strip()


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
