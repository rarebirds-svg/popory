# Google Cloud Text-to-Speech 로 한국어 자연 음성 합성. 키 없거나 실패하면 None(호출측 say 폴백).
import base64
import os

import requests

TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
LANGUAGE = "ko-KR"
VOICE_NAME = "ko-KR-Neural2-C"


def synthesize(text: str) -> bytes | None:
    key = os.environ.get("GOOGLE_TTS_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            f"{TTS_URL}?key={key}",
            json={
                "input": {"text": text},
                "voice": {"languageCode": LANGUAGE, "name": VOICE_NAME},
                "audioConfig": {"audioEncoding": "MP3"},
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
