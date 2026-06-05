# claude CLI 출력에서 draft_markdown·meta_json 두 XML 태그를 추출·파싱.
import json
import re
from typing import Any


class ContractError(Exception):
    """출력 계약 위반(태그 없음/JSON 파싱 실패)."""


def parse_generation(text: str) -> tuple[str, dict[str, Any]]:
    body_m = re.search(r"<draft_markdown>(.*?)</draft_markdown>", text, re.DOTALL)
    meta_m = re.search(r"<meta_json>\s*(\{.*?\})\s*</meta_json>", text, re.DOTALL)
    if not body_m or not meta_m:
        raise ContractError("draft_markdown/meta_json 태그를 찾지 못함")
    draft = body_m.group(1).strip()
    try:
        meta = json.loads(meta_m.group(1).strip())
    except json.JSONDecodeError as e:
        raise ContractError(f"meta_json 파싱 실패: {e}") from e
    return draft, meta
