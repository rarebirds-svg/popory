# youtube 작업의 params_json(길이·목소리·배경스타일) 파싱·매핑.
import json

SCENE_COUNT = {"3": 5, "5": 8, "7": 12, "10": 16}
SHORT_SCENE_COUNT = {"15": 3, "30": 5, "60": 8}
# male 은 Chirp3-HD Charon(깊고 무게감 있는 남성). 2026-06-29 b3d3eeb 에서 Neural2-C 로 되돌렸다가
# 2026-08 재적용 — 되돌림 사유는 취향(이전 목소리 복귀)이었고, 그 뒤 Chirp3-HD 고유 발음 문제
# (소수점 흘림·한자 이중발음·앰퍼샌드)를 tts.py 가 모두 잡아 재시도 조건이 달라졌다.
VOICE = {"female-calm": "ko-KR-Chirp3-HD-Aoede", "female-bright": "ko-KR-Chirp3-HD-Leda", "male": "ko-KR-Chirp3-HD-Charon"}
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
