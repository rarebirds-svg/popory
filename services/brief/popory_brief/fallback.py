# Gemini 경로가 실패했을 때 대신 쓸 claude 모델을 고른다 — 카테고리가 그날 통째로 빠지지 않게 하는 안전망.
"""공급자 대체 정책.

2026-09-25 부동산 PICK 5 두 카테고리가 Gemini 빈 응답(candidates 없음)으로 그날 유실됐다.
빈 응답은 재시도 대상도 아니었고(exit 4), 재시도 잡도 한도·인증 실패만 다시 돌리므로
사람이 손으로 다시 돌리기 전까지 복구 경로가 없었다. claude CLI(Max 구독)는 맥미니에 이미
로그인돼 있어 추가 비용 없이 대체 생성이 된다.

    BRIEF_FALLBACK_MODEL   미설정  → claude-sonnet-4-6 로 대체
                           claude-* → 그 모델로 대체
                           off     → 대체 안 함 (예전 동작)
"""
from __future__ import annotations

import os
from pathlib import Path

from popory_brief import gemini_client

DEFAULT_FALLBACK_MODEL = "claude-sonnet-4-6"
_OFF = frozenset({"", "off", "none", "0", "false"})


def fallback_model(claude_bin: str) -> str | None:
    """대체 생성에 쓸 claude 모델. 끌 수 없거나 쓸 수 없으면 None.

    Gemini 모델을 적으면 대체가 아니라 같은 공급자 재호출이라 None 으로 본다.
    claude CLI 가 없는 머신(개발 환경·CI)에서도 None — 없는 바이너리를 부르다 init 실패로
    원래 Gemini 오류를 덮으면 안 된다."""
    raw = os.environ.get("BRIEF_FALLBACK_MODEL")
    model = DEFAULT_FALLBACK_MODEL if raw is None else raw.strip()
    if model.lower() in _OFF or gemini_client.is_gemini_model(model):
        return None
    if not Path(claude_bin).exists():
        return None
    return model
