# keychain 토큰 파싱과 oauth/usage 응답 해석 단위 테스트.
import json
import os
import time

import responses
from popory_healthcheck import claude_auth


def test_parse_refresh_expiry_reads_millis_as_seconds():
    raw = json.dumps({"claudeAiOauth": {"refreshTokenExpiresAt": 1_800_000_000_000}})
    assert claude_auth.parse_refresh_expiry(raw) == 1_800_000_000.0


def test_parse_refresh_expiry_none_on_broken_json():
    assert claude_auth.parse_refresh_expiry("not json") is None


def test_parse_refresh_expiry_none_when_field_missing():
    assert claude_auth.parse_refresh_expiry(json.dumps({"claudeAiOauth": {}})) is None


@responses.activate
def test_authorized_true_on_200():
    responses.add(responses.GET, claude_auth.USAGE_URL, status=200, json={"limits": []})
    assert claude_auth.probe_authorized("tok") is True


@responses.activate
def test_authorized_false_on_401():
    responses.add(responses.GET, claude_auth.USAGE_URL, status=401)
    assert claude_auth.probe_authorized("tok") is False


@responses.activate
def test_authorized_unknown_on_500():
    """서버 오류는 인증 만료가 아니다 — 단정하지 않고 None 을 돌려 오경보를 막는다."""
    responses.add(responses.GET, claude_auth.USAGE_URL, status=500)
    assert claude_auth.probe_authorized("tok") is None


def test_authorized_unknown_without_token():
    assert claude_auth.probe_authorized(None) is None


def test_exit_code_maps_status():
    """셸 스크립트가 분기할 수 있게 점검 status 를 종료코드로 바꾼다."""
    assert claude_auth.exit_code_for("ok") == 0
    assert claude_auth.exit_code_for("fail") == 1
    assert claude_auth.exit_code_for("warn") == 2


# ───────── 장기 토큰 모드 ─────────

def test_token_mode_follows_env(monkeypatch):
    assert claude_auth.token_mode() is False
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "  ")
    assert claude_auth.token_mode() is False  # 공백뿐인 값은 토큰이 아니다
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-x")
    assert claude_auth.token_mode() is True


def test_token_issued_at_reads_file_mtime(monkeypatch, tmp_path):
    f = tmp_path / "tok"
    f.write_text("x")
    os.utime(f, (1_700_000_000, 1_700_000_000))
    monkeypatch.setenv("POPORY_CLAUDE_TOKEN_FILE", str(f))
    assert claude_auth.token_issued_at() == 1_700_000_000


def test_token_issued_at_none_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("POPORY_CLAUDE_TOKEN_FILE", str(tmp_path / "nope"))
    assert claude_auth.token_issued_at() is None


def test_main_in_token_mode_ignores_keychain(monkeypatch, tmp_path, capsys):
    """retry_pending.sh 가 이 종료코드로 재시도를 보류한다 — 토큰 모드에서 keychain(만료)을 보면
    토큰이 멀쩡해도 재시도가 영구 보류된다. 이 회귀를 막는 핵심 테스트."""
    f = tmp_path / "tok"
    f.write_text("x")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-x")
    monkeypatch.setenv("POPORY_CLAUDE_TOKEN_FILE", str(f))
    # keychain 은 "refresh 만료됨" 상태 — 종전 로직이면 fail(종료코드 1)이었을 상황.
    monkeypatch.setattr(claude_auth, "current_state", lambda: (False, 1.0))
    assert claude_auth.main([]) == 0
    assert "장기 토큰 정상" in capsys.readouterr().out


def test_main_in_token_mode_fails_after_lifetime(monkeypatch, tmp_path):
    f = tmp_path / "tok"
    f.write_text("x")
    old = time.time() - 400 * 86400
    os.utime(f, (old, old))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setenv("POPORY_CLAUDE_TOKEN_FILE", str(f))
    assert claude_auth.main([]) == 1


def test_main_without_token_mode_still_uses_keychain(monkeypatch):
    monkeypatch.setattr(claude_auth, "current_state", lambda: (False, None))
    assert claude_auth.main([]) == 1  # 종전 동작 불변: 만료 → fail


@responses.activate
def test_usage_status_flag_prints_code_never_token(monkeypatch, capsys):
    responses.add(responses.GET, claude_auth.USAGE_URL, status=403)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-SECRET")
    assert claude_auth.main(["--usage-status"]) == 0
    out = capsys.readouterr().out
    assert out.strip() == "usage_endpoint_http=403"
    assert "SECRET" not in out


def test_probe_status_none_without_token():
    assert claude_auth.probe_status(None) is None
