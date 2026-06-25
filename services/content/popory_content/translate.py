# 한국어 자막 문장을 EN/ZH/JA로 1:1 정렬 번역하는 claude CLI 래퍼.
from __future__ import annotations

import json
import re
from typing import Callable

from popory_content.generate import run_claude_cli, GenerateError

LANGS = ("en", "zh", "ja")

_SYSTEM = (
    "당신은 자막 번역가입니다. 한국어 문장 목록을 받아 각 언어로 번역합니다. "
    "규칙. 입력 문장 수와 출력 배열 길이를 정확히 같게 유지합니다. "
    "문장을 합치거나 나누지 않습니다. 자연스러운 구어체로 번역하고 고유명사·인용은 보존합니다. "
    "광고·구독·홍보 문구를 추가하지 않습니다. "
    'JSON 객체 하나만 출력합니다. 형식 {"en":[...],"zh":[...],"ja":[...]}. 코드블록 표시 금지.'
)


def _build_parse(n: int, langs) -> Callable[[str], dict[str, list[str]]]:
    def parse(stdout: str) -> dict[str, list[str]]:
        m = re.search(r"\{.*\}", stdout, re.S)
        if not m:
            raise ValueError("번역 JSON 없음")
        data = json.loads(m.group(0))
        out: dict[str, list[str]] = {}
        for lang in langs:
            arr = data.get(lang)
            if not isinstance(arr, list) or len(arr) != n:
                got = len(arr) if isinstance(arr, list) else "none"
                raise ValueError(f"{lang} 길이 불일치: {got} != {n}")
            out[lang] = [str(x) for x in arr]
        return out
    return parse


def translate_lines(ko_lines: list[str], langs=LANGS, *, job_id: str = "adhoc",
                    runner=run_claude_cli) -> dict[str, list[str]] | None:
    """한국어 문장 배열 → {lang: 번역 배열}. 1:1 정렬을 보장 못 하면 None."""
    if not ko_lines:
        return {lang: [] for lang in langs}
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(ko_lines))
    user_msg = (
        f"다음 한국어 문장 {len(ko_lines)}개를 {', '.join(langs)}로 번역하세요. "
        "각 배열 길이는 정확히 입력 수와 같아야 합니다.\n\n" + numbered
    )
    try:
        return runner(system_prompt=_SYSTEM, user_msg=user_msg,
                      parse=_build_parse(len(ko_lines), langs), job_id=job_id)
    except GenerateError:
        return None
