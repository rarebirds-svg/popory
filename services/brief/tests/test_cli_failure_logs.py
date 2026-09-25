# 각 brief CLI 의 실패 종료 경로가 append_log 로 실패 레코드를 남기는지 검증 (실제 네트워크·메일 발송 없음).
import datetime
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


# ---------------- generate_brief · Gemini 공급자 경로 ----------------
#
# 공급자가 갈려도 run_daily.sh·retry_pending.sh 가 읽는 규약은 하나다.
# (exit 6 + __BRIEF_LIMIT_RESET__ / 인증 실패 마커 / 실패 로그 1줄)

from popory_brief import gemini_client   # noqa: E402


def _gemini_argv(monkeypatch, category: str = "realestate", fallback: str = "off"):
    monkeypatch.setenv("BRIEF_BACKOFF_SECONDS", "")   # 재시도 대기 없음
    # 기본은 대체 끔 — 맥미니처럼 claude CLI 가 실제로 있는 곳에서 테스트가 진짜 CLI 를 부르면 안 된다.
    monkeypatch.setenv("BRIEF_FALLBACK_MODEL", fallback)
    _argv(monkeypatch, "--category", category, "--date", "2026-09-15",
          "--model", "gemini-3.8-flash")


def _gemini_raises(monkeypatch, err: gemini_client.GeminiError):
    monkeypatch.setattr(generate_brief.gemini_client, "generate_with_retry", _raise(err))


def test_generate_gemini_failure_logs_gemini_fail(monkeypatch):
    rec = _patch(monkeypatch, generate_brief)
    _gemini_raises(monkeypatch, gemini_client.GeminiError("요청 거부(400)", exit_code=4))
    _gemini_argv(monkeypatch)

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 4
    r = rec.one(generate_brief)
    assert r["cli"] == "generate_brief"
    assert r["status"] == "gemini_fail"
    assert r["category"] == "realestate"


def test_generate_gemini_quota_exits_6_with_reset(monkeypatch, capsys):
    """Gemini 쿼터도 claude 한도와 같은 규약으로 넘어가야 retry 잡이 복구한다."""
    rec = _patch(monkeypatch, generate_brief)
    _gemini_raises(monkeypatch, gemini_client.GeminiError(
        "쿼터 초과(429)", exit_code=6, retryable=True, is_limit=True, reset_epoch=1789000000))
    _gemini_argv(monkeypatch)

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 6
    assert "__BRIEF_LIMIT_RESET__=1789000000" in capsys.readouterr().out
    r = rec.one(generate_brief)
    assert r["status"] == "limit_fail"
    assert r["reset_epoch"] == 1789000000


def test_generate_gemini_auth_failure_prints_marker(monkeypatch, capsys):
    """키 문제는 사람이 고쳐야 풀린다 — run_daily.sh 가 즉시 알림을 걸 마커를 남긴다."""
    rec = _patch(monkeypatch, generate_brief)
    _gemini_raises(monkeypatch, gemini_client.GeminiError("인증 실패(403)", exit_code=3))
    _gemini_argv(monkeypatch)

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 3
    assert "__BRIEF_AUTH_FAIL__=gemini" in capsys.readouterr().out
    assert rec.one(generate_brief)["status"] == "gemini_fail"


def test_generate_gemini_missing_key_is_config_exit_2(monkeypatch):
    """키가 없으면 설정 누락(exit 2) — 재시도 대상이 아니다."""
    rec = _patch(monkeypatch, generate_brief)
    _gemini_raises(monkeypatch, gemini_client.GeminiError("GEMINI_API_KEY 미설정", exit_code=2))
    _gemini_argv(monkeypatch)

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 2
    assert rec.one(generate_brief)["status"] == "gemini_fail"


def test_generate_gemini_does_not_require_claude_cli(monkeypatch, tmp_path):
    """Gemini 경로는 claude CLI 가 없는 머신에서도 돌아야 한다 — init_fail 로 죽지 않는다."""
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setattr(generate_brief, "CLAUDE_BIN", str(tmp_path / "no-claude"))
    _gemini_raises(monkeypatch, gemini_client.GeminiError("여기까지 왔다", exit_code=4))
    _gemini_argv(monkeypatch)

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 4                       # CLI 부재의 exit 2 가 아니다
    assert rec.one(generate_brief)["status"] == "gemini_fail"


def test_generate_claude_path_still_requires_cli(monkeypatch, tmp_path):
    """반대로 claude 모델을 고른 경우엔 CLI 부재가 그대로 init_fail 이어야 한다."""
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setattr(generate_brief, "CLAUDE_BIN", str(tmp_path / "no-claude"))
    monkeypatch.setenv("BRIEF_BACKOFF_SECONDS", "")
    _argv(monkeypatch, "--category", "realestate", "--date", "2026-09-15",
          "--model", "claude-sonnet-4-6")

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 2
    assert rec.one(generate_brief)["status"] == "init_fail"


# ---------------- generate_brief · 인용 링크 점검 ----------------
#
# grounding 은 존재하지 않는 URL 을 적어 넣는다(2026-09-15 실측: 7개 중 2개 404).
# 기본은 warn(로그만) 이고, strict 로 올리면 발행하지 않는다.

_TAGGED_OK = ('<body_markdown>본문 [t](https://x.test/gone)</body_markdown>'
              '<meta_json>{"title": "제목", "published_at": 1}</meta_json>')


def _claude_returns(monkeypatch, stdout: str):
    monkeypatch.setattr(generate_brief, "CLAUDE_BIN", sys.executable)
    monkeypatch.setattr(generate_brief.subprocess, "run",
                        lambda *a, **k: _Completed(0, stdout=stdout))


def _dead(monkeypatch, pairs):
    monkeypatch.setattr(generate_brief.link_check, "dead_links", lambda body, **k: pairs)


def _link_argv(monkeypatch):
    monkeypatch.setenv("BRIEF_BACKOFF_SECONDS", "")
    _argv(monkeypatch, "--category", "realestate", "--date", "2026-01-02")


def test_generate_strict_mode_refuses_to_publish_dead_links(monkeypatch):
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setenv("BRIEF_LINK_CHECK", "strict")
    _claude_returns(monkeypatch, _TAGGED_OK)
    _dead(monkeypatch, [("https://x.test/gone", 404)])
    _link_argv(monkeypatch)

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 4
    # 제목 정규화 기록이 함께 남으므로 rec.one() 이 아니라 해당 레코드를 찾는다.
    r = next(c[1] for c in rec.calls if c[1]["status"] == "link_fail")
    assert is_failure(r["status"])
    assert r["dead_count"] == 1
    assert "https://x.test/gone" in r["dead"]


def test_generate_warn_mode_publishes_but_logs(monkeypatch):
    """기본 warn — 발행은 계속하고 죽은 링크만 기록한다. 켜는 순간 브리핑이 죽으면 안 된다."""
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setenv("BRIEF_LINK_CHECK", "warn")
    _claude_returns(monkeypatch, _TAGGED_OK)
    _dead(monkeypatch, [("https://x.test/gone", 404)])
    _link_argv(monkeypatch)

    generate_brief.main()   # SystemExit 없이 끝난다

    statuses = [rec_call[1]["status"] for rec_call in rec.calls]
    assert "link_warn" in statuses
    assert "ok" in statuses          # 생성 성공 기록도 남는다


def test_generate_off_mode_skips_the_check(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("off 면 링크 점검을 하지 않아야 한다")
    _patch(monkeypatch, generate_brief)
    monkeypatch.setenv("BRIEF_LINK_CHECK", "off")
    monkeypatch.setattr(generate_brief.link_check, "dead_links", _boom)
    _claude_returns(monkeypatch, _TAGGED_OK)
    _link_argv(monkeypatch)

    generate_brief.main()


def test_generate_clean_links_leave_no_warning(monkeypatch):
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setenv("BRIEF_LINK_CHECK", "strict")
    _claude_returns(monkeypatch, _TAGGED_OK)
    _dead(monkeypatch, [])
    _link_argv(monkeypatch)

    generate_brief.main()

    statuses = [c[1]["status"] for c in rec.calls]
    assert "link_fail" not in statuses and "link_warn" not in statuses


def test_generate_degrade_mode_strips_links_and_publishes(monkeypatch):
    """degrade — 죽은 링크만 벗기고 발행은 계속한다. 본문 파일에 그 URL 이 남지 않아야 한다."""
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setenv("BRIEF_LINK_CHECK", "degrade")
    tagged = ('<body_markdown>본문 [법률신문 — 제목](https://x.test/gone)</body_markdown>'
              '<meta_json>{"title": "제목", "published_at": 1}</meta_json>')
    _claude_returns(monkeypatch, tagged)
    _dead(monkeypatch, [("https://x.test/gone", 404)])
    _link_argv(monkeypatch)

    generate_brief.main()

    r = next(c[1] for c in rec.calls if c[1]["status"] == "link_degraded")
    assert r["stripped"] == 1
    assert r["dead_count"] == 1
    written = Path("/tmp/brief_realestate_2026-01-02.md").read_text(encoding="utf-8")
    assert "https://x.test/gone" not in written
    assert "법률신문 — 제목" in written      # 출처 텍스트는 남는다


# ---------------- generate_brief · Gemini 실패 → claude 대체 ----------------
#
# 2026-09-25 부동산 PICK 5 두 카테고리가 Gemini 빈 응답으로 그날 유실됐다. 이제 Gemini 가
# 재시도까지 실패하면 claude CLI 로 한 번 더 쓴다.

class _ClaudeStub:
    """subprocess.run 대역. 호출 때마다 넘어온 모델·시스템 프롬프트·user 메시지를 기록한다."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls: list[dict] = []

    def __call__(self, cmd, input=None, **kwargs):
        sys_file = cmd[cmd.index("--system-prompt-file") + 1]
        self.calls.append({"model": cmd[cmd.index("--model") + 1],
                           "system": Path(sys_file).read_text(encoding="utf-8"),
                           "user": input})
        return self.results.pop(0)


def _gemini_then_claude(monkeypatch, err, *claude_results):
    monkeypatch.setattr(generate_brief, "CLAUDE_BIN", sys.executable)
    seen = {}

    def _gen(**kwargs):
        seen.update(kwargs)
        raise err

    monkeypatch.setattr(generate_brief.gemini_client, "generate_with_retry", _gen)
    stub = _ClaudeStub(*claude_results)
    monkeypatch.setattr(generate_brief.subprocess, "run", stub)
    _dead(monkeypatch, [])
    return seen, stub


def _statuses(rec: Recorder) -> list[str]:
    # 제목 보정 기록은 픽스처 제목("제목") 때문에 끼는 것이라 뺀다.
    return [r["status"] for _d, r in rec.calls if r["status"] != "title_normalized"]


def test_generate_gemini_empty_response_falls_back_to_claude(monkeypatch, capsys):
    rec = _patch(monkeypatch, generate_brief)
    err = gemini_client.GeminiError("Gemini 응답에 candidates 없음 — usage=…", exit_code=5,
                                    retryable=True, diag={"usage": {"thoughtsTokenCount": 1}})
    seen, stub = _gemini_then_claude(monkeypatch, err, _Completed(0, stdout=_TAGGED_OK))
    _gemini_argv(monkeypatch, fallback="claude-sonnet-4-6")

    generate_brief.main()    # 예외 없이 끝나야 발행 단계로 넘어간다

    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["status"] == "ok"
    assert _statuses(rec) == ["gemini_fail", "ok"]
    # 헬스체크는 "대체 시도" 가 아니라 ok 레코드의 fallback 으로 "대체 발행" 을 가른다.
    assert rec.calls[-1][1]["fallback"] == "claude-sonnet-4-6"
    fail = rec.calls[0][1]
    assert fail["fallback"] == "claude-sonnet-4-6"
    assert fail["exit_code"] == 5
    assert fail["diag"] == {"usage": {"thoughtsTokenCount": 1}}
    # 공급자별 프롬프트 — Gemini 에는 실행 환경 안내, claude 에는 원래 매뉴얼과 도구 이름.
    assert "실행 환경 안내" in seen["system_prompt"]
    assert "웹 검색(Google Search)으로" in seen["user_msg"]
    assert stub.calls[0]["model"] == "claude-sonnet-4-6"
    assert "실행 환경 안내" not in stub.calls[0]["system"]
    assert "WebSearch 도구로" in stub.calls[0]["user"]


def test_generate_gemini_auth_rescued_by_claude_raises_no_auth_alarm(monkeypatch, capsys):
    """대체로 발행됐으면 run_daily 의 인증 실패 목록에 오르면 안 된다(헬스체크가 대체를 띄운다)."""
    rec = _patch(monkeypatch, generate_brief)
    _gemini_then_claude(monkeypatch, gemini_client.GeminiError("쿼터 미할당(429)", exit_code=3),
                        _Completed(0, stdout=_TAGGED_OK))
    _gemini_argv(monkeypatch, fallback="claude-sonnet-4-6")

    generate_brief.main()

    assert "__BRIEF_AUTH_FAIL__" not in capsys.readouterr().out
    assert _statuses(rec) == ["gemini_fail", "ok"]


def test_generate_gemini_auth_and_claude_fail_keeps_auth_marker(monkeypatch, capsys):
    """둘 다 실패하면 Gemini 키·결제는 여전히 사람이 고쳐야 한다 — 즉시 알림 마커를 남긴다."""
    rec = _patch(monkeypatch, generate_brief)
    _gemini_then_claude(monkeypatch, gemini_client.GeminiError("인증 실패(403)", exit_code=3),
                        _Completed(1, stderr="boom"))
    _gemini_argv(monkeypatch, fallback="claude-sonnet-4-6")

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 5
    assert "__BRIEF_AUTH_FAIL__=gemini" in capsys.readouterr().out
    assert _statuses(rec) == ["gemini_fail", "claude_fail"]


def test_generate_gemini_quota_and_claude_fail_waits_for_retry(monkeypatch, capsys):
    """Gemini 쿼터 + claude 실패면 exit 6 으로 끝내 retry 잡이 쿼터 회복 뒤 다시 돌게 한다."""
    rec = _patch(monkeypatch, generate_brief)
    _gemini_then_claude(monkeypatch, gemini_client.GeminiError(
        "쿼터 초과(429)", exit_code=6, retryable=True, is_limit=True, reset_epoch=1789000000),
        _Completed(1, stderr="boom"))
    _gemini_argv(monkeypatch, fallback="claude-sonnet-4-6")

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 6
    assert "__BRIEF_LIMIT_RESET__=1789000000" in capsys.readouterr().out
    assert _statuses(rec) == ["gemini_fail", "claude_fail"]


def test_generate_claude_limit_during_fallback_keeps_claude_reset(monkeypatch, capsys):
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setattr(generate_brief.limit_detect, "is_limit_message", lambda s: True)
    monkeypatch.setattr(generate_brief.limit_detect, "reset_epoch_or_fallback", lambda s, n: 1770000000)
    _gemini_then_claude(monkeypatch, gemini_client.GeminiError("빈 응답", exit_code=5, retryable=True),
                        _Completed(1, stdout="limit"))
    _gemini_argv(monkeypatch, fallback="claude-sonnet-4-6")

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 6
    out = capsys.readouterr().out
    assert out.count("__BRIEF_LIMIT_RESET__=") == 1
    assert "__BRIEF_LIMIT_RESET__=1770000000" in out
    assert _statuses(rec) == ["gemini_fail", "limit_fail"]


def test_generate_gemini_failure_without_cli_does_not_try_fallback(monkeypatch, tmp_path):
    """대체 모델이 켜져 있어도 CLI 가 없으면 원래 Gemini 오류 그대로 끝난다."""
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setattr(generate_brief, "CLAUDE_BIN", str(tmp_path / "no-claude"))
    _gemini_raises(monkeypatch, gemini_client.GeminiError("빈 응답", exit_code=5, retryable=True))
    _gemini_argv(monkeypatch, fallback="claude-sonnet-4-6")

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 5
    r = rec.one(generate_brief)
    assert r["status"] == "gemini_fail"
    assert "fallback" not in r


def test_generate_past_date_tells_model_the_day_is_over(monkeypatch):
    """자정을 넘긴 재시도(run_daily --date=전날)는 그날이 다 지난 시점으로 알린다.

    0시로 알리면 모델이 그날 기사는 아직 없다고 보고 전일 기사로 채운다."""
    _patch(monkeypatch, generate_brief)
    seen, _stub = _gemini_then_claude(monkeypatch, gemini_client.GeminiError("x", exit_code=4),
                                      _Completed(0, stdout=_TAGGED_OK))
    _gemini_argv(monkeypatch)   # --date 2026-09-15, 대체 끔

    with pytest.raises(SystemExit):
        generate_brief.main()

    assert "지금은 2026-09-15 23:59 (KST)" in seen["user_msg"]


@pytest.mark.parametrize("err,code,marker", [
    (gemini_client.GeminiError("쿼터 초과(429)", exit_code=6, retryable=True, is_limit=True,
                               reset_epoch=1789000000), 6, "__BRIEF_LIMIT_RESET__=1789000000"),
    (gemini_client.GeminiError("인증 실패(403)", exit_code=3), 4, "__BRIEF_AUTH_FAIL__=gemini"),
])
def test_generate_fallback_untagged_output_keeps_gemini_contract(monkeypatch, capsys, err, code, marker):
    """대체 claude 가 exit 0 이지만 태그 없는 응답을 내도 Gemini 쪽 복구 규약(쿼터 6·인증 마커)은 남는다."""
    rec = _patch(monkeypatch, generate_brief)
    _gemini_then_claude(monkeypatch, err, _Completed(0, stdout="태그 없는 응답"))
    _gemini_argv(monkeypatch, fallback="claude-sonnet-4-6")

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == code
    assert marker in capsys.readouterr().out
    assert _statuses(rec) == ["gemini_fail", "parse_fail"]


def test_generate_fallback_exception_keeps_gemini_quota_contract(monkeypatch, capsys):
    """대체 실행이 예외(예: CLI 실행 권한)로 죽어도 쿼터 실패는 exit 6 으로 retry 잡에 실린다."""
    rec = _patch(monkeypatch, generate_brief)
    _gemini_then_claude(monkeypatch, gemini_client.GeminiError(
        "쿼터 초과(429)", exit_code=6, retryable=True, is_limit=True, reset_epoch=1789000000))
    monkeypatch.setattr(generate_brief.subprocess, "run", _raise(PermissionError("denied")))
    _gemini_argv(monkeypatch, fallback="claude-sonnet-4-6")

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 6
    assert "__BRIEF_LIMIT_RESET__=1789000000" in capsys.readouterr().out
    assert _statuses(rec) == ["gemini_fail", "claude_fail"]


def test_generate_untagged_gemini_output_falls_back_to_claude(monkeypatch, capsys):
    """Gemini 가 답은 했지만 태그를 빠뜨렸거나 잘린 경우도 대체 대상이다(예전엔 parse_fail 로 유실)."""
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setattr(generate_brief, "CLAUDE_BIN", sys.executable)
    monkeypatch.setattr(generate_brief.gemini_client, "generate_with_retry",
                        lambda **k: "<body_markdown>잘린 본문")
    monkeypatch.setattr(generate_brief.subprocess, "run", _ClaudeStub(_Completed(0, stdout=_TAGGED_OK)))
    _dead(monkeypatch, [])
    _gemini_argv(monkeypatch, fallback="claude-sonnet-4-6")

    generate_brief.main()

    assert _statuses(rec) == ["gemini_fail", "ok"]
    assert rec.calls[0][1]["error"].startswith("Gemini 응답 형식 오류")
    assert rec.calls[-1][1]["fallback"] == "claude-sonnet-4-6"


def test_generate_untagged_gemini_output_without_fallback_exits_4(monkeypatch):
    rec = _patch(monkeypatch, generate_brief)
    monkeypatch.setattr(generate_brief.gemini_client, "generate_with_retry", lambda **k: "태그 없음")
    _gemini_argv(monkeypatch)   # 대체 끔

    with pytest.raises(SystemExit) as e:
        generate_brief.main()

    assert e.value.code == 4
    r = rec.one(generate_brief)
    assert r["status"] == "gemini_fail"
    assert r["error"].startswith("Gemini 응답 형식 오류")


def test_generate_todays_date_keeps_run_time(monkeypatch):
    """run_daily 는 날짜를 항상 --date 로 고정해 넘긴다. 오늘 날짜면 예전처럼 실행 시각 기준이어야
    한다 — 0시로 두면 published_at 과 프롬프트의 "지금" 이 0시로 바뀐다."""
    _patch(monkeypatch, generate_brief)
    seen, _stub = _gemini_then_claude(monkeypatch, gemini_client.GeminiError("x", exit_code=4),
                                      _Completed(0, stdout=_TAGGED_OK))
    now = datetime.datetime.now(generate_brief.KST)
    monkeypatch.setenv("BRIEF_BACKOFF_SECONDS", "")
    monkeypatch.setenv("BRIEF_FALLBACK_MODEL", "off")
    _argv(monkeypatch, "--category", "realestate", "--date", now.strftime("%Y-%m-%d"),
          "--model", "gemini-3.8-flash")

    with pytest.raises(SystemExit):
        generate_brief.main()

    published_at = int(seen["user_msg"].split("published_at은 ")[1].split("을")[0])
    assert abs(published_at - now.timestamp()) < 60
