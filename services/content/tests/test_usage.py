# Claude 사용량 파싱·캐시 단위 테스트.
import time as _time

from popory_content import usage

FIXTURE = {"limits": [
    {"kind": "session", "group": "session", "percent": 38, "severity": "normal",
     "resets_at": "2026-07-04T21:19:59+00:00", "scope": None, "is_active": False},
    {"kind": "weekly_all", "group": "weekly", "percent": 50, "severity": "normal",
     "resets_at": "2026-07-06T15:59:59+00:00", "scope": None, "is_active": True},
    {"kind": "weekly_scoped", "group": "weekly", "percent": 21, "severity": "normal",
     "resets_at": "2026-07-06T15:59:59+00:00",
     "scope": {"model": {"id": None, "display_name": "Fable"}}, "is_active": False},
]}


def test_parse_limits_extracts_three():
    out = usage._parse_limits(FIXTURE)
    assert out["session"] == {"percent": 38, "resets_at": "2026-07-04T21:19:59+00:00", "severity": "normal"}
    assert out["weekly_all"]["percent"] == 50
    assert out["weekly_fable"]["percent"] == 21
    assert out["weekly_fable"]["resets_at"] == "2026-07-06T15:59:59+00:00"


def test_parse_limits_ignores_non_fable_scoped():
    data = {"limits": [{"kind": "weekly_scoped", "percent": 9, "severity": "normal", "resets_at": "x",
                        "scope": {"model": {"display_name": "Sonnet"}}}]}
    assert usage._parse_limits(data) is None


def test_parse_limits_none_when_empty():
    assert usage._parse_limits({"limits": []}) is None
    assert usage._parse_limits({}) is None


def test_cached_uses_cache_within_ttl(monkeypatch):
    calls = {"n": 0}

    def fake_fetch():
        calls["n"] += 1
        return {"session": {"percent": 1}}

    monkeypatch.setattr(usage, "fetch_claude_usage", fake_fetch)
    usage._cache["at"] = 0.0
    usage._cache["val"] = None
    a = usage.cached_claude_usage(ttl=300)
    b = usage.cached_claude_usage(ttl=300)
    assert a == b == {"session": {"percent": 1}}
    assert calls["n"] == 1  # ttl 내 재호출 안 함


def test_cached_keeps_prior_on_failure(monkeypatch):
    usage._cache["val"] = {"session": {"percent": 5}}
    usage._cache["at"] = _time.monotonic() - 1000  # 만료
    monkeypatch.setattr(usage, "fetch_claude_usage", lambda: None)
    assert usage.cached_claude_usage(ttl=300) == {"session": {"percent": 5}}
