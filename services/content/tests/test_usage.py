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


# ───────── 장기 토큰(환경변수) 모드 ─────────

class _Resp:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


_LIMITS_OK = {"limits": [{"kind": "session", "percent": 12, "resets_at": "x", "severity": "ok"}]}


def test_candidates_env_token_first_then_keychain(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "env-tok")
    monkeypatch.setattr(usage, "_keychain_access_token", lambda: "kc-tok")
    assert usage._candidate_tokens() == ["env-tok", "kc-tok"]


def test_candidates_dedupes_identical_tokens(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "same")
    monkeypatch.setattr(usage, "_keychain_access_token", lambda: "same")
    assert usage._candidate_tokens() == ["same"]


def test_fetch_falls_back_to_keychain_when_env_token_lacks_scope(monkeypatch):
    """장기 토큰이 사용량 조회 권한을 갖는지 미확인 — 거절돼도 keychain 으로 폴백해 표시를 유지한다."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "env-tok")
    monkeypatch.setattr(usage, "_keychain_access_token", lambda: "kc-tok")
    seen = []

    def fake_get(url, headers=None, timeout=None):
        seen.append(headers["Authorization"])
        return _Resp(403) if headers["Authorization"].endswith("env-tok") else _Resp(200, _LIMITS_OK)

    monkeypatch.setattr(usage.requests, "get", fake_get)
    status, val = usage._fetch_with_status()
    assert status == "ok" and val["session"]["percent"] == 12
    assert seen == ["Bearer env-tok", "Bearer kc-tok"]


def test_fetch_stops_at_first_success(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "env-tok")
    monkeypatch.setattr(usage, "_keychain_access_token", lambda: "kc-tok")
    calls = []
    monkeypatch.setattr(usage.requests, "get",
                        lambda url, headers=None, timeout=None: calls.append(1) or _Resp(200, _LIMITS_OK))
    assert usage._fetch_with_status()[0] == "ok"
    assert len(calls) == 1  # 성공했으면 폴백 호출을 하지 않는다


def test_fetch_unauthorized_only_when_every_token_is_401(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "env-tok")
    monkeypatch.setattr(usage, "_keychain_access_token", lambda: "kc-tok")
    monkeypatch.setattr(usage.requests, "get", lambda url, headers=None, timeout=None: _Resp(401))
    assert usage._fetch_with_status() == ("unauthorized", None)


def test_fetch_mixed_401_and_error_keeps_prior_cache(monkeypatch):
    """한쪽만 401 이면 만료로 단정하지 않는다 — 캐시를 비우면 정상 값이 사라진다."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "env-tok")
    monkeypatch.setattr(usage, "_keychain_access_token", lambda: "kc-tok")
    monkeypatch.setattr(usage.requests, "get",
                        lambda url, headers=None, timeout=None:
                        _Resp(401) if headers["Authorization"].endswith("env-tok") else _Resp(500))
    assert usage._fetch_with_status() == ("error", None)


def test_fetch_no_tokens_is_error(monkeypatch):
    monkeypatch.setattr(usage, "_keychain_access_token", lambda: None)
    assert usage._fetch_with_status() == ("error", None)
