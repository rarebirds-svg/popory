# youtube 작업의 params_json(길이·목소리·배경스타일) 파싱·매핑.
import json

SCENE_COUNT = {"3": 5, "5": 8, "7": 12, "10": 16}
SHORT_SCENE_COUNT = {"15": 3, "30": 5, "60": 8}
# male 은 Gemini 3.8 Flash TTS · Voice design 으로 만든 설계 음성(voice_…). "모델/화자" 형식이면
# gemini_tts 로 장면 단위 합성한다. 실패·월 상한 초과 시 영상 전체가 FALLBACK_VOICE(이전 기본 Neural2-C)로 간다.
# 이력 — Iapetus(2026-10-05, 화자 비교 도구로 사용자가 직접 고름) → 설계 음성 voice_s8vzho2m0lq6(2026-11-08).
# 프리셋 Iapetus 는 화자 이름만 고정하고 합성할 때마다 목소리를 새로 만들어 챕터마다 목소리가 바뀌었다.
# 실험(같은 쇼츠 원고, tools/voice_ab.py) — 장면 사이 폭 2.66→1.36반음, 테이크 간 2.1→1.1반음, 필요 보정량 0.58→0.38반음.
# 되돌리려면 male 값을 "gemini-3.8-flash-tts/Iapetus" 로 한 줄 바꾸고 워커를 재시작한다.
# Charon(초기 목소리)은 2026-06-29 b3d3eeb 와 2026-08-11 두 번 취향 사유로 기각됐다 — 다시 올리지 않는다.
VOICE = {"female-calm": "ko-KR-Chirp3-HD-Aoede", "female-bright": "ko-KR-Chirp3-HD-Leda",
         "male": "gemini-3.8-flash-tts/voice_s8vzho2m0lq6"}
FALLBACK_VOICE = "ko-KR-Neural2-C"
STYLE = {
    "photo": "photorealistic, cinematic",
    "illust": "digital illustration, clean",
    "watercolor": "watercolor painting",
    "minimal": "minimalist flat design",
}
DEFAULTS = {"length": "10", "voice": "male", "image_style": "photo"}
SHORTS_DEFAULTS = {"length": "60", "voice": "male", "image_style": "photo", "upload_targets": []}


def parse_options(params_json: str | None) -> dict:
    opts = dict(DEFAULTS)
    if not params_json:
        return opts
    try:
        data = json.loads(params_json)
    except (json.JSONDecodeError, TypeError):
        return opts
    if isinstance(data, dict):
        if data.get("length") in SCENE_COUNT:
            opts["length"] = data["length"]
        if data.get("voice") in VOICE:
            opts["voice"] = data["voice"]
        if data.get("image_style") in STYLE:
            opts["image_style"] = data["image_style"]
    return opts


def parse_shorts_options(params_json: str | None) -> dict:
    opts = dict(SHORTS_DEFAULTS)
    opts["upload_targets"] = []
    if not params_json:
        return opts
    try:
        data = json.loads(params_json)
    except (json.JSONDecodeError, TypeError):
        return opts
    if isinstance(data, dict):
        if data.get("length") in SHORT_SCENE_COUNT:
            opts["length"] = data["length"]
        if data.get("voice") in VOICE:
            opts["voice"] = data["voice"]
        if data.get("image_style") in STYLE:
            opts["image_style"] = data["image_style"]
        targets = data.get("upload_targets", [])
        if isinstance(targets, list):
            opts["upload_targets"] = [t for t in targets if t in ("youtube", "instagram", "facebook")]
    return opts
