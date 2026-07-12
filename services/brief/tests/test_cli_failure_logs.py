# 각 brief CLI 의 실패 종료 경로가 append_log 로 실패 레코드를 남기는지 검증 (실제 네트워크·메일 발송 없음).
import json
import subprocess
import sys

import pytest

import fetch_subscribers
import generate_brief
import publish_to_portal
import send_gmail
from popory_brief.log import is_failure
from popory_brief.portal_client import PortalError


class Recorder:
    """append_log 대역. (logs_dir, record) 를 그대로 모은다."""

    def __init__(self):
        self.calls: list[tuple] = []

    def __call__(self, logs_dir, record):
        self.calls.append((logs_dir, record))

    def one(self, module) -> dict:
        assert len(self.calls) == 1, f"append_log 호출 1회 기대, 실제 {len(self.calls)}회"
        logs_dir, record = self.calls[0]
        assert logs_dir == module.LOGS_DIR
        assert is_failure(record["status"]), f"{record['status']} 는 is_failure 에 걸리지 않는다"
        return record


def _patch(monkeypatch, module) -> Recorder:
    rec = Recorder()
    monkeypatch.setattr(module, "append_log", rec)
    return rec


def _argv(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["cli"] + list(args))


def _clear_portal_env(monkeypatch):
    monkeypatch.delenv("POPORY_BRIEF_KEY_FILE", raising=False)
    monkeypatch.delenv("POPORY_PORTAL_API_BASE", raising=False)


def _raise(exc):
    def _f(*args, **kwargs):
        raise exc
    return _f


# ---------------- fetch_subscribers ----------------

def test_fetch_subscribers_missing_key_env(monkeypatch):
    rec = _patch(monkeypatch, fetch_subscribers)
    _clear_portal_env(monkeypatch)
    _argv(monkeypatch, "--area", "brief")

    with pytest.raises(SystemExit) as e:
        fetch_subscribers.main()

    assert e.value.code == 2
    r = rec.one(fetch_subscribers)
    assert r["cli"] == "fetch_subscribers"
    assert r["status"] == "init_fail"


def test_fetch_subscribers_missing_key_file_does_not_log_path(monkeypatch, tmp_path):
    """키 파일 경로는 비밀정보 취급 — error 문자열에 넣지 않는다."""
    rec = _patch(monkeypatch, fetch_subscribers)
    secret_path = str(tmp_path / "secrets" / "brief_signing_key.json")
    monkeypatch.setenv("POPORY_BRIEF_KEY_FILE", secret_path)
    monkeypatch.setenv("POPORY_PORTAL_API_BASE", "https://api.popory.test")
    _argv(monkeypatch, "--area", "brief")

    with pytest.raises(SystemExit) as e:
        fetch_subscribers.main()

    assert e.value.code == 2
    r = rec.one(fetch_subscribers)
    assert r["status"] == "init_fail"
    assert secret_path not in json.dumps(r, ensure_ascii=False)


def test_fetch_subscribers_portal_error(monkeypatch):
    rec = _patch(monkeypatch, fetch_subscribers)
    monkeypatch.setattr(fetch_subscribers, "fetch",
                        _raise(PortalError("server 500 after retry: boom", exit_code=5)))
    _argv(monkeypatch, "--area", "brief")

    with pytest.raises(SystemExit) as e:
        fetch_subscribers.main()

    assert e.value.code == 5
    r = rec.one(fetch_subscribers)
    assert r["cli"] == "fetch_subscribers"
    assert r["status"] == "fetch_fail"
    assert "server 500" in r["error"]


def test_init_failure_writes_real_log_without_key(monkeypatch, tmp_path):
    """키·base 가 없는 초기화 실패 경로에서도 진짜 append_log 가 예외 없이 파일을 남긴다 (전송은 건너뜀)."""
    _clear_portal_env(monkeypatch)
    monkeypatch.setattr(fetch_subscribers, "LOGS_DIR", tmp_path)
    _argv(monkeypatch, "--area", "brief")

    with pytest.raises(SystemExit) as e:
        fetch_subscribers.main()

    assert e.value.code == 2
    logfile = next(iter(tmp_path.glob("*.log")))
    rows = [json.loads(l) for l in logfile.read_text().splitlines()]
    assert [r["status"] for r in rows] == ["init_fail"]   # ship_fail 이 붙지 않는다.


# ---------------- publish_to_portal ----------------

def _publish_files(tmp_path) -> tuple[str, str]:
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps({"title": "t", "published_at": 1}), encoding="utf-8")
    body = tmp_path / "b.md"
    body.write_text("본문", encoding="utf-8")
    return str(meta), str(body)


def test_publish_missing_key_env(monkeypatch, tmp_path):
    rec = _patch(monkeypatch, publish_to_portal)
    _clear_portal_env(monkeypatch)
    meta, body = _publish_files(tmp_path)
    _argv(monkeypatch, "--area", "brief", "--meta-file", meta, "--body-file", body)

    with pytest.raises(SystemExit) as e:
        publish_to_portal.main()

    assert e.value.code == 2
    r = rec.one(publish_to_portal)
    assert r["cli"] == "publish_to_portal"
    assert r["status"] == "init_fail"


def test_publish_missing_portal_base(monkeypatch, tmp_path):
    rec = _patch(monkeypatch, publish_to_portal)
    keyfile = tmp_path / "key.json"
    keyfile.write_text("{}")
    monkeypatch.setenv("POPORY_BRIEF_KEY_FILE", str(keyfile))
    monkeypatch.delenv("POPORY_PORTAL_API_BASE", raising=False)
    monkeypatch.setattr(publish_to_portal.KeyMaterial, "load", staticmethod(lambda p: object()))
    meta, body = _publish_files(tmp_path)
    _argv(monkeypatch, "--area", "brief", "--meta-file", meta, "--body-file", body)

    with pytest.raises(SystemExit) as e:
        publish_to_portal.main()

    assert e.value.code == 2
    r = rec.one(publish_to_portal)
    assert r["status"] == "init_fail"


def test_publish_portal_error(monkeypatch, tmp_path):
    rec = _patch(monkeypatch, publish_to_portal)
    monkeypatch.setattr(publish_to_portal, "publish",
                        _raise(PortalError("client 400: bad title", exit_code=4)))
    meta, body = _publish_files(tmp_path)
    _argv(monkeypatch, "--area", "brief", "--meta-file", meta, "--body-file", body)

    with pytest.raises(SystemExit) as e:
        publish_to_portal.main()

    assert e.value.code == 4
    r = rec.one(publish_to_portal)
    assert r["cli"] == "publish_to_portal"
    assert r["status"] == "publish_fail"
    assert r["area"] == "brief"
    assert "client 400" in r["error"]


# ---------------- send_gmail ----------------

def _gmail_argv(monkeypatch, tmp_path):
    body = tmp_path / "body.md"
    body.write_text("본문", encoding="utf-8")
    _argv(monkeypatch, "--to", "a@b.com", "--subject", "제목", "--body-file", str(body))


def test_send_gmail_missing_token_does_not_log_path(monkeypatch, tmp_path):
    """token.json 경로는 자격증명 위치 — error 문자열에 넣지 않는다."""
    rec = _patch(monkeypatch, send_gmail)
    token = tmp_path / "secrets" / "token.json"
    monkeypatch.setattr(send_gmail, "TOKEN_FILE", token)
    _gmail_argv(monkeypatch, tmp_path)

    with pytest.raises(SystemExit) as e:
        send_gmail.main()

    assert e.value.code == 2
    r = rec.one(send_gmail)
    assert r["cli"] == "send_gmail"
    assert r["status"] == "auth_fail"
    assert str(token) not in json.dumps(r, ensure_ascii=False)


def _stub_gmail_service(monkeypatch):
    monkeypatch.setattr(send_gmail, "load_credentials", lambda: object())
    monkeypatch.setattr(send_gmail, "build", lambda *a, **k: object())


class _Resp:
    """googleapiclient HttpError 가 요구하는 최소 응답 (status·reason)."""

    def __init__(self, status: int, reason: str = "Bad Request"):
        self.status = status
        self.reason = reason


def test_send_gmail_http_4xx(monkeypatch, tmp_path):
    from googleapiclient.errors import HttpError
    rec = _patch(monkeypatch, send_gmail)
    _stub_gmail_service(monkeypatch)
    monkeypatch.setattr(send_gmail, "send_with_retry",
                        _raise(HttpError(_Resp(400), b'{"error":"invalid to"}')))
    _gmail_argv(monkeypatch, tmp_path)

    with pytest.raises(SystemExit) as e:
        send_gmail.main()

    assert e.value.code == 4
    r = rec.one(send_gmail)
    assert r["cli"] == "send_gmail"
    assert r["status"] == "send_fail"
    assert r["to"] == "a@b.com"


def test_send_gmail_unexpected_error(monkeypatch, tmp_path):
    rec = _patch(monkeypatch, send_gmail)
    _stub_gmail_service(monkeypatch)
    monkeypatch.setattr(send_gmail, "send_with_retry", _raise(RuntimeError("network down")))
    _gmail_argv(monkeypatch, tmp_path)

    with pytest.raises(SystemExit) as e:
        send_gmail.main()

    assert e.value.code == 5
    r = rec.one(send_gmail)
    assert r["status"] == "send_fail"
    assert "network down" in r["error"]


# ---------------- generate_brief ----------------

class _Completed:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _gen_argv(monkeypatch, category: str = "realestate"):
    monkeypatch.setenv("BRIEF_BACKOFF_SECONDS", "")   # 재시도 대기 없음
    _argv(monkeypatch, "--category", category, "--date", "2026-07-12")


def test_generate_missing_claude_bin(monkeypatch, tmp_path):
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setattr(generate_brief, "CLAUDE_BIN", str(tmp_path / "no-claude"))
    _gen_argv(monkeypatch)

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 2
    r = rec.one(generate_brief)
    assert r["cli"] == "generate_brief"
    assert r["status"] == "init_fail"


def test_generate_unknown_category(monkeypatch):
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setattr(generate_brief, "CLAUDE_BIN", sys.executable)
    _gen_argv(monkeypatch, category="nope-nope")

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 2
    r = rec.one(generate_brief)
    assert r["status"] == "init_fail"
    assert r["category"] == "nope-nope"


def test_generate_claude_nonzero_exit(monkeypatch):
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setattr(generate_brief, "CLAUDE_BIN", sys.executable)
    monkeypatch.setattr(generate_brief.subprocess, "run",
                        lambda *a, **k: _Completed(1, stdout="", stderr="boom"))
    _gen_argv(monkeypatch)

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 5
    r = rec.one(generate_brief)
    assert r["cli"] == "generate_brief"
    assert r["status"] == "claude_fail"
    assert r["category"] == "realestate"


def test_generate_claude_timeout(monkeypatch):
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setattr(generate_brief, "CLAUDE_BIN", sys.executable)
    monkeypatch.setattr(generate_brief.subprocess, "run",
                        _raise(subprocess.TimeoutExpired(cmd="claude", timeout=1800)))
    _gen_argv(monkeypatch)

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 5
    r = rec.one(generate_brief)
    assert r["status"] == "claude_fail"


def test_generate_usage_limit(monkeypatch):
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setattr(generate_brief, "CLAUDE_BIN", sys.executable)
    monkeypatch.setattr(generate_brief.subprocess, "run",
                        lambda *a, **k: _Completed(1, stdout="limit", stderr=""))
    monkeypatch.setattr(generate_brief.limit_detect, "is_limit_message", lambda s: True)
    monkeypatch.setattr(generate_brief.limit_detect, "reset_epoch_or_fallback", lambda s, n: 1770000000)
    _gen_argv(monkeypatch)

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 6
    r = rec.one(generate_brief)
    assert r["status"] == "limit_fail"
    assert r["reset_epoch"] == 1770000000


def test_generate_missing_tags(monkeypatch):
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setattr(generate_brief, "CLAUDE_BIN", sys.executable)
    monkeypatch.setattr(generate_brief.subprocess, "run",
                        lambda *a, **k: _Completed(0, stdout="태그 없는 응답"))
    _gen_argv(monkeypatch)

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 4
    r = rec.one(generate_brief)
    assert r["status"] == "parse_fail"


def test_generate_bad_meta_json(monkeypatch):
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setattr(generate_brief, "CLAUDE_BIN", sys.executable)
    out = "<body_markdown>본문</body_markdown><meta_json>{not json}</meta_json>"
    monkeypatch.setattr(generate_brief.subprocess, "run",
                        lambda *a, **k: _Completed(0, stdout=out))
    _gen_argv(monkeypatch)

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 4
    r = rec.one(generate_brief)
    assert r["status"] == "parse_fail"
