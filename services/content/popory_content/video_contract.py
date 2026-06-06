# claude 출력에서 scenes_json·video_meta 두 태그를 추출·파싱. ContractError 는 contract 모듈 재사용.
import json
import re
from typing import Any

from popory_content.contract import ContractError


def parse_video(text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    scenes_m = re.search(r"<scenes_json>\s*(\[.*\])\s*</scenes_json>", text, re.DOTALL)
    meta_m = re.search(r"<video_meta>\s*(\{.*?\})\s*</video_meta>", text, re.DOTALL)
    if not scenes_m or not meta_m:
        raise ContractError("scenes_json/video_meta 태그를 찾지 못함")
    try:
        scenes = json.loads(scenes_m.group(1).strip())
        meta = json.loads(meta_m.group(1).strip())
    except json.JSONDecodeError as e:
        raise ContractError(f"video JSON 파싱 실패: {e}") from e
    if not isinstance(scenes, list) or not scenes:
        raise ContractError("scenes 가 비어있음")
    for s in scenes:
        if not s.get("caption") or not s.get("narration"):
            raise ContractError("scene 에 caption/narration 누락")
    return scenes, meta
