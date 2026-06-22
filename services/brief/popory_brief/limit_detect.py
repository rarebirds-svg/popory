# Claude Max 사용량 한도 메시지 감지와 리셋 시각 파싱을 담당
from __future__ import annotations

import datetime
import re

KST = datetime.timezone(datetime.timedelta(hours=9))

# claude CLI가 사용량 한도로 끝날 때 stdout/stderr에 남기는 메시지 조각.
# 소문자 비교. 과거 포맷 + 2026-06 "You've hit your session limit · resets 11:10am" 포맷 포함.
LIMIT_MARKERS = (
    "usage limit",
    "rate limit",
    "limit reached",
    "too many requests",
    "session limit",
    "resets at",
    "resets ",
)

# claude CLI가 Anthropic 서버 일시 과부하(API 529 Overloaded)로 끝날 때의 메시지 조각.
# 실패(비정상 종료) 출력에만 적용되므로 본문에 섞인 숫자 오탐 걱정은 없다.
OVERLOAD_MARKERS = (
    "overloaded",
    "overload_error",
)

# 인-프로세스 백오프 소진 후 한도 리셋 시각을 못 구할 때 쓰는 폴백(롤링 윈도우 상한).
FALLBACK_RESET_SECONDS = 5 * 60 * 60


def is_limit_message(text: str) -> bool:
    """claude CLI 출력이 사용량 한도 때문인지 판정한다."""
    t = text.lower()
    return any(m in t for m in LIMIT_MARKERS)


def is_overload_message(text: str) -> bool:
    """claude CLI 출력이 일시적 서버 과부하(529) 때문인지 판정한다."""
    t = text.lower()
    return any(m in t for m in OVERLOAD_MARKERS)


def parse_reset_epoch(text: str, now: datetime.datetime) -> int | None:
    """'resets 11:10am (Asia/Seoul)' / 'resets at 11pm' 등에서 KST 리셋 epoch를 뽑는다.

    파싱 실패 시 None. 추출한 시각이 이미 지났으면 익일로 넘긴다.
    """
    m = re.search(r"resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text, re.IGNORECASE)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    now_kst = now.astimezone(KST)
    reset = now_kst.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if reset <= now_kst:
        reset += datetime.timedelta(days=1)
    return int(reset.timestamp())


def reset_epoch_or_fallback(text: str, now: datetime.datetime) -> int:
    """리셋 시각을 파싱하되 실패하면 now + 5h를 돌려준다."""
    parsed = parse_reset_epoch(text, now)
    if parsed is not None:
        return parsed
    return int(now.timestamp()) + FALLBACK_RESET_SECONDS
