# limit_detect 한도 메시지 감지·리셋 시각 파싱 단위 테스트.
"""Claude Max 세션 한도 메시지를 감지하고 리셋 시각을 파싱하는 유틸 검증."""
from __future__ import annotations

import datetime

from popory_brief import limit_detect

KST = datetime.timezone(datetime.timedelta(hours=9))

# 2026-06-13 실제 실패 메시지 (회귀 방지)
REAL_MSG = "You've hit your session limit · resets 11:10am (Asia/Seoul)"


def test_detects_real_session_limit_message():
    assert limit_detect.is_limit_message(REAL_MSG) is True


def test_detects_legacy_markers():
    assert limit_detect.is_limit_message("Error: usage limit reached") is True
    assert limit_detect.is_limit_message("429 too many requests") is True


def test_non_limit_message_is_false():
    assert limit_detect.is_limit_message("error: connection refused") is False
    assert limit_detect.is_limit_message("tag <body_markdown> not found") is False


def test_parse_reset_epoch_am():
    # 실패 시각 08:48 KST → 같은 날 11:10 KST 리셋
    now = datetime.datetime(2026, 6, 13, 8, 48, tzinfo=KST)
    epoch = limit_detect.parse_reset_epoch(REAL_MSG, now)
    expected = int(datetime.datetime(2026, 6, 13, 11, 10, tzinfo=KST).timestamp())
    assert epoch == expected


def test_parse_reset_epoch_pm():
    now = datetime.datetime(2026, 6, 13, 9, 0, tzinfo=KST)
    epoch = limit_detect.parse_reset_epoch("resets 11pm (Asia/Seoul)", now)
    expected = int(datetime.datetime(2026, 6, 13, 23, 0, tzinfo=KST).timestamp())
    assert epoch == expected


def test_parse_reset_rolls_to_next_day_when_past():
    # 현재 22:00, 리셋 표기 1:00am → 이미 지난 시각이므로 익일 01:00
    now = datetime.datetime(2026, 6, 13, 22, 0, tzinfo=KST)
    epoch = limit_detect.parse_reset_epoch("resets 1:00am", now)
    expected = int(datetime.datetime(2026, 6, 14, 1, 0, tzinfo=KST).timestamp())
    assert epoch == expected


def test_parse_reset_returns_none_when_absent():
    assert limit_detect.parse_reset_epoch("usage limit reached", now=datetime.datetime.now(KST)) is None


def test_fallback_when_unparseable():
    now = datetime.datetime(2026, 6, 13, 8, 48, tzinfo=KST)
    epoch = limit_detect.reset_epoch_or_fallback("usage limit reached", now)
    assert epoch == int(now.timestamp()) + limit_detect.FALLBACK_RESET_SECONDS


def test_fallback_uses_parsed_when_available():
    now = datetime.datetime(2026, 6, 13, 8, 48, tzinfo=KST)
    epoch = limit_detect.reset_epoch_or_fallback(REAL_MSG, now)
    expected = int(datetime.datetime(2026, 6, 13, 11, 10, tzinfo=KST).timestamp())
    assert epoch == expected
