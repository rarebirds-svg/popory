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
        return ("ok", {"session": {"percent": 1}})

    monkeypatch.setattr(usage, "_fetch_with_status", fake_fetch)
    usage._cache["at"] = 0.0
    usage._cache["val"] = None
    a = usage.cached_claude_usage(ttl=300)
    b = usage.cached_claude_usage(ttl=300)
    assert a == b == {"session": {"percent": 1}}
    assert calls["n"] == 1  # ttl 내 재호출 안 함


def test_cached_keeps_prior_on_failure(monkeypatch):
    """네트워크·서버 오류는 만료가 아니므로 직전 값을 유지한다 (401 과 대비)."""
    usage._cache["val"] = {"session": {"percent": 5}}
    usage._cache["at"] = _time.monotonic() - 1000  # 만료
    monkeypatch.setattr(usage, "_fetch_with_status", lambda: ("error", None))
    assert usage.cached_claude_usage(ttl=300) == {"session": {"percent": 5}}


def test_cached_drops_cache_when_unauthorized(monkeypatch):
    """OAuth 만료(401)면 직전 캐시를 버린다 — 옛 사용량을 계속 보여주면 만료가 은폐된다."""
    usage._cache["val"] = {"session": {"percent": 5}}
    usage._cache["at"] = _time.monotonic() - 1000  # ttl 만료시켜 재취득 경로로
    monkeypatch.setattr(usage, "_fetch_with_status", lambda: ("unauthorized", None))

    assert usage.cached_claude_usage() is None
    assert usage._cache["val"] is None


def test_fetch_with_status_reports_unauthorized_on_401(monkeypatch):
    monkeypatch.setattr(usage, "_keychain_access_token", lambda: "tok")

    class Resp:
        status_code = 401

    monkeypatch.setattr(usage.requests, "get", lambda *a, **k: Resp())
    assert usage._fetch_with_status() == ("unauthorized", None)


def test_fetch_with_status_reports_error_on_500(monkeypatch):
    """서버 오류는 만료가 아니다 — 캐시를 버리면 안 되므로 error 로 구분한다."""
    monkeypatch.setattr(usage, "_keychain_access_token", lambda: "tok")

    class Resp:
        status_code = 500

    monkeypatch.setattr(usage.requests, "get", lambda *a, **k: Resp())
    assert usage._fetch_with_status() == ("error", None)
