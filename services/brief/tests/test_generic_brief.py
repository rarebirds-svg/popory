# generic_brief — already_published_today 멱등성 가드, Gemini 실패 시 claude 대체 단위 테스트.
"""커스텀 주제 브리핑이 같은 날 중복 발행되지 않도록 막는 가드 검증."""
from __future__ import annotations
import datetime
import json
import sys

import pytest

import generic_brief
from popory_brief import gemini_client

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


# ---------------- Gemini 실패 → claude 대체 (커스텀 주제) ----------------

class _Done:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _fallback_env(monkeypatch, result, fallback="claude-sonnet-4-6"):
    monkeypatch.setattr(generic_brief, "CLAUDE_BIN", sys.executable)
    monkeypatch.setenv("BRIEF_FALLBACK_MODEL", fallback)
    monkeypatch.setattr(generic_brief, "BACKOFF_SECONDS", [])
    calls = []

    def _run(cmd, input=None, **kwargs):
        calls.append({"model": cmd[cmd.index("--model") + 1], "user": input})
        return result

    monkeypatch.setattr(generic_brief.subprocess, "run", _run)
    return calls


def _prompts(gemini):
    return ("gemini-sys", "gemini-user") if gemini else ("claude-sys", "claude-user")


def test_gemini_failure_falls_back_to_claude_prompts(monkeypatch):
    calls = _fallback_env(monkeypatch, _Done(0, stdout="본문"))
    err = gemini_client.GeminiError("빈 응답", exit_code=5, retryable=True)

    out = generic_brief._gemini_failed(err, _prompts, "t1", "2026-09-25")

    assert out == "본문"
    assert calls == [{"model": "claude-sonnet-4-6", "user": "claude-user"}]


def test_gemini_quota_with_failed_fallback_exits_6(monkeypatch, capsys):
    _fallback_env(monkeypatch, _Done(1, stderr="boom"))
    err = gemini_client.GeminiError("쿼터", exit_code=6, retryable=True, is_limit=True,
                                    reset_epoch=1789000000)

    with pytest.raises(SystemExit) as e:
        generic_brief._gemini_failed(err, _prompts, "t1", "2026-09-25")

    assert e.value.code == 6
    assert "__BRIEF_LIMIT_RESET__=1789000000" in capsys.readouterr().out


@pytest.mark.parametrize("exit_code,marker", [(3, True), (4, False), (5, False)])
def test_gemini_failure_without_fallback_keeps_contract(monkeypatch, capsys, exit_code, marker):
    _fallback_env(monkeypatch, _Done(0, stdout="쓰이면 안 됨"), fallback="off")
    err = gemini_client.GeminiError("x", exit_code=exit_code)

    with pytest.raises(SystemExit) as e:
        generic_brief._gemini_failed(err, _prompts, "t1", "2026-09-25")

    assert e.value.code == exit_code
    assert ("__BRIEF_AUTH_FAIL__=gemini" in capsys.readouterr().out) is marker
