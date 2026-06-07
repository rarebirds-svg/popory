# claude 출력에서 slides_json·carousel_meta 두 태그를 추출·파싱.
import json
import re
from typing import Any

from popory_content.contract import ContractError


def parse_carousel(text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    slides_m = re.search(r"<slides_json>\s*(\[.*\])\s*</slides_json>", text, re.DOTALL)
    meta_m = re.search(r"<carousel_meta>\s*(\{.*?\})\s*</carousel_meta>", text, re.DOTALL)
    if not slides_m or not meta_m:
        raise ContractError("slides_json/carousel_meta 태그를 찾지 못함")
    try:
        slides = json.loads(slides_m.group(1).strip())
        meta = json.loads(meta_m.group(1).strip())
    except json.JSONDecodeError as e:
        raise ContractError(f"carousel JSON 파싱 실패: {e}") from e
    if not isinstance(slides, list) or not slides:
        raise ContractError("slides 가 비어있음")
    for s in slides:
        if not s.get("title") or not s.get("body"):
            raise ContractError("slide 에 title/body 누락")
    return slides, meta
