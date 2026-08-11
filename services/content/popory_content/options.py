# youtube 작업의 params_json(길이·목소리·배경스타일) 파싱·매핑.
import json

SCENE_COUNT = {"3": 5, "5": 8, "7": 12, "10": 16}
SHORT_SCENE_COUNT = {"15": 3, "30": 5, "60": 8}
# male 은 Neural2-C. Charon(초기 목소리)은 2026-06-29 b3d3eeb 와 2026-08-11 두 번 취향 사유로
# 기각됐다 — 발음 문제를 tts.py 가 잡아도 판단이 바뀌지 않았으므로 다시 올리지 않는다.
VOICE = {"female-calm": "ko-KR-Chirp3-HD-Aoede", "female-bright": "ko-KR-Chirp3-HD-Leda", "male": "ko-KR-Neural2-C"}
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
            opts["upload_targets"] = [t for t in targets if t in ("youtube", "instagram")]
    return opts
