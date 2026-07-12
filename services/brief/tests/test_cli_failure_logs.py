# 각 brief CLI 의 실패 종료 경로가 append_log 로 실패 레코드를 남기는지 검증 (실제 네트워크·메일 발송 없음).
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import fetch_subscribers
import generate_brief
import publish_to_portal
import send_gmail
from popory_brief.log import is_failure, safe_error
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


# ---------------- 비처리 예외 (run() 래퍼) ----------------
#
# 네 CLI 의 엔트리포인트 run() 은 비처리 예외를 unexpected_fail 로 남긴 뒤 그대로 다시 raise 한다.
# 검증 포인트. (1) unexpected_fail 로 1회 기록 (2) 예외가 그대로 밖으로 나감 (3) error 에 비밀 경로 없음.

def _unexpected(rec, module) -> dict:
    r = rec.one(module)
    assert r["status"] == "unexpected_fail"
    return r


def test_safe_error_masks_path_bearing_exceptions():
    """경로가 메시지에 박히는 예외(OSError·subprocess 계열)는 타입 이름만 남긴다."""
    missing = FileNotFoundError(2, "No such file or directory", "/secret/dir/brief_signing_key.json")
    assert safe_error(missing) == "FileNotFoundError"
    timeout = subprocess.TimeoutExpired(cmd=["/opt/homebrew/bin/claude"], timeout=1)
    assert safe_error(timeout) == "TimeoutExpired"
    assert "/opt/homebrew" not in safe_error(timeout)


def test_safe_error_keeps_message_and_truncates():
    assert safe_error(KeyError("title")) == "KeyError: 'title'"
    long = safe_error(ValueError("x" * 500))
    assert long.startswith("ValueError: xxx")
    assert len(long) == 300


def test_publish_missing_body_file_does_not_log_path(monkeypatch, tmp_path):
    """본문 파일 부재 FileNotFoundError — 경로를 남기지 않고 예외는 그대로 나간다."""
    rec = _patch(monkeypatch, publish_to_portal)
    meta, _ = _publish_files(tmp_path)
    missing = str(tmp_path / "secrets" / "no-body.md")
    _argv(monkeypatch, "--area", "brief", "--meta-file", meta, "--body-file", missing)

    with pytest.raises(FileNotFoundError):
        publish_to_portal.run()

    r = _unexpected(rec, publish_to_portal)
    assert r["cli"] == "publish_to_portal"
    assert r["error"] == "FileNotFoundError"
    assert missing not in json.dumps(r, ensure_ascii=False)


def test_publish_bad_meta_json(monkeypatch, tmp_path):
    rec = _patch(monkeypatch, publish_to_portal)
    meta = tmp_path / "m.json"
    meta.write_text("not json", encoding="utf-8")
    body = tmp_path / "b.md"
    body.write_text("본문", encoding="utf-8")
    _argv(monkeypatch, "--area", "brief", "--meta-file", str(meta), "--body-file", str(body))

    with pytest.raises(json.JSONDecodeError):
        publish_to_portal.run()

    r = _unexpected(rec, publish_to_portal)
    assert r["error"].startswith("JSONDecodeError: ")


def test_publish_meta_without_title(monkeypatch, tmp_path):
    rec = _patch(monkeypatch, publish_to_portal)
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps({"published_at": 1}), encoding="utf-8")
    body = tmp_path / "b.md"
    body.write_text("본문", encoding="utf-8")
    _argv(monkeypatch, "--area", "brief", "--meta-file", str(meta), "--body-file", str(body))

    with pytest.raises(KeyError):
        publish_to_portal.run()

    r = _unexpected(rec, publish_to_portal)
    assert r["error"] == "KeyError: 'title'"


def test_publish_key_material_load_failure_does_not_log_path(monkeypatch, tmp_path):
    """KeyMaterial.load 실패 — 키 파일 경로가 로그에 새면 안 된다."""
    rec = _patch(monkeypatch, publish_to_portal)
    keyfile = tmp_path / "secrets" / "brief_signing_key.json"
    keyfile.parent.mkdir()
    keyfile.write_text("깨진 키파일", encoding="utf-8")
    monkeypatch.setenv("POPORY_BRIEF_KEY_FILE", str(keyfile))
    monkeypatch.setenv("POPORY_PORTAL_API_BASE", "https://api.popory.test")
    meta, body = _publish_files(tmp_path)
    _argv(monkeypatch, "--area", "brief", "--meta-file", meta, "--body-file", body)

    with pytest.raises(Exception):
        publish_to_portal.run()

    r = _unexpected(rec, publish_to_portal)
    assert str(keyfile) not in json.dumps(r, ensure_ascii=False)


def test_fetch_subscribers_key_material_load_failure_does_not_log_path(monkeypatch, tmp_path):
    rec = _patch(monkeypatch, fetch_subscribers)
    keyfile = tmp_path / "secrets" / "brief_signing_key.json"
    keyfile.parent.mkdir()
    keyfile.write_text(json.dumps({"public_jwk": {}}), encoding="utf-8")   # kid 없음 → KeyError
    monkeypatch.setenv("POPORY_BRIEF_KEY_FILE", str(keyfile))
    monkeypatch.setenv("POPORY_PORTAL_API_BASE", "https://api.popory.test")
    _argv(monkeypatch, "--area", "brief")

    with pytest.raises(KeyError):
        fetch_subscribers.run()

    r = _unexpected(rec, fetch_subscribers)
    assert r["cli"] == "fetch_subscribers"
    assert str(keyfile) not in json.dumps(r, ensure_ascii=False)


def test_send_gmail_missing_body_file_does_not_log_path(monkeypatch, tmp_path):
    rec = _patch(monkeypatch, send_gmail)
    missing = str(tmp_path / "secrets" / "no-body.md")
    _argv(monkeypatch, "--to", "a@b.com", "--subject", "제목", "--body-file", missing)

    with pytest.raises(FileNotFoundError):
        send_gmail.run()

    r = _unexpected(rec, send_gmail)
    assert r["cli"] == "send_gmail"
    assert r["error"] == "FileNotFoundError"
    assert missing not in json.dumps(r, ensure_ascii=False)


def test_send_gmail_broken_token_file(monkeypatch, tmp_path):
    """token.json 이 있으나 형식이 깨진 경우 — Credentials 파싱 예외가 로그되고 그대로 나간다."""
    rec = _patch(monkeypatch, send_gmail)
    token = tmp_path / "secrets" / "token.json"
    token.parent.mkdir()
    token.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(send_gmail, "TOKEN_FILE", token)
    _gmail_argv(monkeypatch, tmp_path)

    with pytest.raises(ValueError):
        send_gmail.run()

    r = _unexpected(rec, send_gmail)
    assert r["error"].startswith("ValueError: ")
    assert str(token) not in json.dumps(r, ensure_ascii=False)


def test_generate_bad_date_argument(monkeypatch):
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setattr(generate_brief, "CLAUDE_BIN", sys.executable)
    monkeypatch.setenv("BRIEF_BACKOFF_SECONDS", "")
    _argv(monkeypatch, "--category", "realestate", "--date", "2026-13-99")

    with pytest.raises(ValueError):
        generate_brief.run()

    r = _unexpected(rec, generate_brief)
    assert r["cli"] == "generate_brief"
    assert r["error"].startswith("ValueError: ")


@pytest.mark.parametrize("module", [fetch_subscribers, publish_to_portal, send_gmail, generate_brief])
def test_run_wrapper_does_not_double_log_sys_exit(monkeypatch, module, tmp_path):
    """SystemExit 은 Exception 을 상속하지 않는다 — 명시적 실패 경로가 래퍼에 이중 기록되면 안 된다."""
    rec = _patch(monkeypatch, module)
    monkeypatch.setattr(module, "main", _raise(SystemExit(2)))

    with pytest.raises(SystemExit) as e:
        module.run()

    assert e.value.code == 2
    assert rec.calls == []   # run() 은 SystemExit 을 잡지 않는다.


def test_unexpected_exception_keeps_exit_code_and_traceback(tmp_path):
    """엔트리포인트를 그대로 실행했을 때 exit code 1 + traceback 이 유지되고 로그 1줄만 남는다."""
    brief_dir = Path(publish_to_portal.__file__).resolve().parent
    logs_dir = tmp_path / "logs"
    meta, _ = _publish_files(tmp_path)
    script = "\n".join([
        f"import sys; sys.path.insert(0, {str(brief_dir)!r})",
        "from pathlib import Path",
        "import publish_to_portal",
        f"publish_to_portal.LOGS_DIR = Path({str(logs_dir)!r})",
        f"sys.argv = ['cli', '--meta-file', {meta!r}, '--body-file', {str(tmp_path / 'no-body.md')!r}]",
        "publish_to_portal.run()",
    ])
    env = {k: v for k, v in os.environ.items()
           if k not in ("POPORY_BRIEF_KEY_FILE", "POPORY_PORTAL_API_BASE")}
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env)

    assert proc.returncode == 1
    assert "Traceback" in proc.stderr
    assert "FileNotFoundError" in proc.stderr
    rows = [json.loads(l) for l in next(iter(logs_dir.glob("*.log"))).read_text().splitlines()]
    assert [r["status"] for r in rows] == ["unexpected_fail"]
    assert rows[0]["error"] == "FileNotFoundError"
