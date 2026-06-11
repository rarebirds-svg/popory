# generic_brief.already_published_today 멱등성 가드 단위 테스트.
"""커스텀 주제 브리핑이 같은 날 중복 발행되지 않도록 막는 가드 검증."""
from __future__ import annotations
import datetime
import json

import generic_brief

KST = datetime.timezone(datetime.timedelta(hours=9))


class _FakeResp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _opener_with(items):
    payload = json.dumps({"items": items}).encode()

    def _open(url, timeout=0):
        return _FakeResp(payload)

    return _open


def _ts_on(day: datetime.date) -> int:
    return int(datetime.datetime(day.year, day.month, day.day, 9, 0, tzinfo=KST).timestamp())


def test_skips_when_today_already_published():
    today = datetime.datetime.now(KST).date()
    opener = _opener_with([{"published_at": _ts_on(today)}])
    assert generic_brief.already_published_today("https://api.example.com", "abc123", today, opener=opener) is True


def test_proceeds_when_last_published_yesterday():
    today = datetime.datetime.now(KST).date()
    yesterday = today - datetime.timedelta(days=1)
    opener = _opener_with([{"published_at": _ts_on(yesterday)}])
    assert generic_brief.already_published_today("https://api.example.com", "abc123", today, opener=opener) is False


def test_proceeds_when_no_items():
    today = datetime.datetime.now(KST).date()
    opener = _opener_with([])
    assert generic_brief.already_published_today("https://api.example.com", "abc123", today, opener=opener) is False


def test_failopen_when_base_missing():
    today = datetime.datetime.now(KST).date()
    assert generic_brief.already_published_today("", "abc123", today) is False


def test_failopen_when_opener_raises():
    today = datetime.datetime.now(KST).date()

    def _boom(url, timeout=0):
        raise OSError("network down")

    assert generic_brief.already_published_today("https://api.example.com", "abc123", today, opener=_boom) is False
