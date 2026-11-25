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

import datetime
import os
import sys
from pathlib import Path

from popory_brief import gemini_client

DEFAULT_FALLBACK_MODEL = "claude-sonnet-4-6"
KST = datetime.timezone(datetime.timedelta(hours=9))
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


def fallback_skip_reason(claude_bin: str) -> str:
    """fallback_model 이 None 일 때 왜 대체를 못 하는지 — 로그·알림용 한 줄.

    2026-11-07 대체 claude 가 조용히 꺼져(이유 기록 없음) 7개 카테고리가 Gemini 402 로만 실패했다.
    대체가 왜 안 됐는지 남아 있어야 "Gemini 결제" 가 아니라 "claude 경로" 를 고치러 간다."""
    raw = os.environ.get("BRIEF_FALLBACK_MODEL")
    model = DEFAULT_FALLBACK_MODEL if raw is None else raw.strip()
    if model.lower() in _OFF:
        return "BRIEF_FALLBACK_MODEL=off 로 꺼 둠"
    if gemini_client.is_gemini_model(model):
        return f"BRIEF_FALLBACK_MODEL 이 Gemini 모델({model})"
    if not Path(claude_bin).exists():
        return f"claude CLI 없음({claude_bin})"
    return ""


def restore_gemini_contract(err: "gemini_client.GeminiError", fallback_code: int) -> None:
    """대체까지 실패했을 때 원래 Gemini 실패의 복구 경로를 되살린다.

    대체가 어떤 식으로 실패하든(비정상 종료·형식 불량·예외) 같은 규칙이어야 한다 — 하나라도
    빠지면 Gemini 쿼터 실패가 exit 6 대신 exit 4 로 끝나 retry 잡 대상에서 빠진다.
    - 키·결제(exit 3): 인증 마커를 남긴다 → run_daily 즉시 알림·pending.
    - 쿼터(is_limit): 대체 쪽이 한도(6)가 아니면 Gemini 리셋 epoch 로 exit 6 → retry 잡.
    exit 6 이 필요하면 여기서 끝낸다. 아니면 돌아와서 호출부가 대체 쪽 exit code 로 끝낸다."""
    if err.exit_code == 3:
        print("__BRIEF_AUTH_FAIL__=gemini")
    if err.is_limit and fallback_code != 6:
        reset_epoch = err.reset_epoch or int(datetime.datetime.now(KST).timestamp())
        print(f"__BRIEF_LIMIT_RESET__={reset_epoch}")
        sys.exit(6)
