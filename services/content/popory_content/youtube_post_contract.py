# claude 출력에서 post_markdown·post_meta 두 태그를 추출·파싱하는 게시물 계약.
import json
import re
from typing import Any

from popory_content.contract import ContractError


def parse_youtube_post(text: str) -> tuple[str, dict[str, Any]]:
    body_m = re.search(r"<post_markdown>(.*?)</post_markdown>", text, re.DOTALL)
    meta_m = re.search(r"<post_meta>\s*(\{.*?\})\s*</post_meta>", text, re.DOTALL)
    if not body_m or not meta_m:
        raise ContractError("post_markdown/post_meta 태그를 찾지 못함")
    post = body_m.group(1).strip()
    if not post:
        raise ContractError("post_markdown 이 비어있음")
    try:
        meta = json.loads(meta_m.group(1).strip())
    except json.JSONDecodeError as e:
        raise ContractError(f"post_meta 파싱 실패: {e}") from e
    return post, meta
