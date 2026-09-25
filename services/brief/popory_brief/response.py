# LLM 응답에서 브리핑 본문·메타를 꺼낸다 — 공급자·CLI 가 같은 규칙으로 판정해야 대체 여부가 한 곳에서 갈린다.
from __future__ import annotations

import json
import re

_BODY_RE = re.compile(r"<body_markdown>(.*?)</body_markdown>", re.DOTALL)
_META_RE = re.compile(r"<meta_json>\s*(\{.*?\})\s*</meta_json>", re.DOTALL)


class ResponseFormatError(ValueError):
    """태그 누락·meta_json 파싱 실패. detail 은 stderr 진단용 원문 조각(로그 파일엔 싣지 않는다)."""

    def __init__(self, message: str, detail: str):
        super().__init__(message)
        self.detail = detail


def parse_response(text: str) -> tuple[str, dict]:
    """(body, meta). 형식이 깨졌으면 ResponseFormatError."""
    body_m = _BODY_RE.search(text)
    meta_m = _META_RE.search(text)
    if not body_m or not meta_m:
        raise ResponseFormatError("응답에서 body_markdown/meta_json 태그를 찾지 못함", text[-1000:])
    try:
        meta = json.loads(meta_m.group(1).strip())
    except json.JSONDecodeError as e:
        raise ResponseFormatError(f"meta_json 파싱 실패: {e}", meta_m.group(1)) from None
    return body_m.group(1).strip(), meta
