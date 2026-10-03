# generic_brief — already_published_today 멱등성 가드, Gemini 실패 시 claude 대체 단위 테스트.
"""커스텀 주제 브리핑이 같은 날 중복 발행되지 않도록 막는 가드 검증."""
from __future__ import annotations
import datetime
import json
import sys
from pathlib import Path

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


_TAGGED = ('<body_markdown>본문</body_markdown>'
           '<meta_json>{"title": "제목", "published_at": 1}</meta_json>')


def test_gemini_failure_falls_back_to_claude_prompts(monkeypatch):
    calls = _fallback_env(monkeypatch, _Done(0, stdout=_TAGGED))
    err = gemini_client.GeminiError("빈 응답", exit_code=5, retryable=True)

    body, meta = generic_brief._gemini_failed(err, _prompts, "t1", "2026-09-25")

    assert (body, meta["title"]) == ("본문", "제목")
    assert calls == [{"model": "claude-sonnet-4-6", "user": "claude-user"}]


@pytest.mark.parametrize("claude_result", [
    _Done(1, stderr="boom"),                 # 비정상 종료
    _Done(0, stdout="태그 없는 응답"),         # 정상 종료지만 형식 불량
])
def test_gemini_quota_keeps_retry_contract_whatever_way_fallback_fails(monkeypatch, capsys, claude_result):
    """대체가 어떻게 실패하든 Gemini 쿼터면 exit 6 — 아니면 retry 잡 대상에서 빠진다."""
    _fallback_env(monkeypatch, claude_result)
    err = gemini_client.GeminiError("쿼터", exit_code=6, retryable=True, is_limit=True,
                                    reset_epoch=1789000000)

    with pytest.raises(SystemExit) as e:
        generic_brief._gemini_failed(err, _prompts, "t1", "2026-09-25")

    assert e.value.code == 6
    assert "__BRIEF_LIMIT_RESET__=1789000000" in capsys.readouterr().out


def test_main_wires_gemini_failure_to_claude_with_claude_prompts(monkeypatch, capsys, tmp_path):
    """main() 을 거쳐도 대체가 claude 용 프롬프트(WebSearch·WebFetch 도구 이름)로 가는지."""
    monkeypatch.setattr(generic_brief, "CLAUDE_BIN", sys.executable)
    monkeypatch.setenv("BRIEF_FALLBACK_MODEL", "claude-sonnet-4-6")
    monkeypatch.setattr(generic_brief, "BACKOFF_SECONDS", [])
    monkeypatch.setattr(generic_brief, "already_published_today", lambda *a, **k: False)
    monkeypatch.setattr(generic_brief.link_check, "dead_links", lambda body, **k: [])
    monkeypatch.setattr(generic_brief.gemini_client, "generate_with_retry",
                        lambda **k: "태그 없는 Gemini 응답")      # 형식 불량도 대체 대상
    claude = {}

    def _run(cmd, input=None, **kwargs):
        if "--system-prompt-file" in cmd:
            claude["system"] = Path(cmd[cmd.index("--system-prompt-file") + 1]).read_text(encoding="utf-8")
            claude["user"] = input
            return _Done(0, stdout=_TAGGED)
        return _Done(0, stdout='{"status": "ok", "id": "p1"}')    # publish_to_portal

    monkeypatch.setattr(generic_brief.subprocess, "run", _run)
    monkeypatch.setattr(sys, "argv", ["generic_brief", "--topic-id", "t1", "--name", "금리",
                                      "--date", "2026-09-25", "--model", "gemini-3.8-flash"])

    generic_brief.main()

    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (out["status"], out["published_id"]) == ("ok", "p1")
    assert "WebSearch와 WebFetch 도구로" in claude["system"]
    assert "WebSearch 도구로" in claude["user"]


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
