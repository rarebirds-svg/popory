# claude_token.sh(토큰 주입 헬퍼)와 install_claude_token.sh(검증 후 설치)를 실제 bash 로 실행해 검증한다.
# 설치 스크립트는 가짜 claude 바이너리를 CLAUDE_BIN 으로 주입한다 — 실제 인증·네트워크를 쓰지 않는다.
import os
import stat
import subprocess
from pathlib import Path

HC = Path(__file__).resolve().parent.parent
HELPER = HC / "claude_token.sh"
INSTALLER = HC / "install_claude_token.sh"


def _source_helper(env_extra: dict, prelude: str = "") -> dict:
    """헬퍼를 source 한 뒤 내보낸 값을 key=value 로 돌려받는다. set -eu 아래에서도 안전해야 한다."""
    env = {"PATH": os.environ["PATH"], **env_extra}
    script = (f"set -eu\n{prelude}\nsource '{HELPER}'\n"
              'echo "TOKEN=${CLAUDE_CODE_OAUTH_TOKEN:-<unset>}"\n'
              'echo "HINT=${POPORY_CLAUDE_AUTH_HINT:-<unset>}"\n'
              'echo "FILE=${POPORY_CLAUDE_TOKEN_FILE:-<unset>}"\n')
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, check=True)
    return dict(line.split("=", 1) for line in r.stdout.strip().splitlines())


def test_helper_noop_without_token_file(tmp_path):
    """토큰 파일이 없으면 종전 keychain 로그인 방식 그대로 — 환경변수를 만들지 않는다(안전한 점진 전환)."""
    out = _source_helper({"HOME": str(tmp_path)})
    assert out["TOKEN"] == "<unset>"
    assert "claude /login" in out["HINT"]


def test_helper_exports_trimmed_token_and_switches_hint(tmp_path):
    f = tmp_path / "tok"
    f.write_text("  sk-ant-oat01-abc \n")
    out = _source_helper({"HOME": str(tmp_path), "POPORY_CLAUDE_TOKEN_FILE": str(f)})
    assert out["TOKEN"] == "sk-ant-oat01-abc"
    # 토큰 모드에서 /login 은 소용없다 — 알림이 틀린 처방을 내면 안 된다.
    assert "setup-token" in out["HINT"] and "소용없음" in out["HINT"]
    assert out["FILE"] == str(f)


def test_helper_ignores_empty_file(tmp_path):
    f = tmp_path / "tok"
    f.write_text("\n  \n")
    out = _source_helper({"HOME": str(tmp_path), "POPORY_CLAUDE_TOKEN_FILE": str(f)})
    assert out["TOKEN"] == "<unset>"


def test_helper_does_not_override_existing_env_token(tmp_path):
    f = tmp_path / "tok"
    f.write_text("from-file")
    out = _source_helper({"HOME": str(tmp_path), "POPORY_CLAUDE_TOKEN_FILE": str(f),
                          "CLAUDE_CODE_OAUTH_TOKEN": "preset"})
    assert out["TOKEN"] == "preset"


def test_helper_default_path_is_under_home(tmp_path):
    (tmp_path / ".popory").mkdir()
    (tmp_path / ".popory" / "claude_oauth_token").write_text("home-token\n")
    out = _source_helper({"HOME": str(tmp_path)})
    assert out["TOKEN"] == "home-token"


# ───────── 설치 스크립트 ─────────

def _fake_claude(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "fake-claude"
    p.write_text("#!/bin/bash\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


# 정상 동작: 'good-token' 만 통과, 그 외는 401 문구.
_FAKE_OK = '''case "${CLAUDE_CODE_OAUTH_TOKEN:-}" in
  good-token) echo "pong"; exit 0;;
  *) echo "Failed to authenticate. API Error: 401 invalid bearer token"; exit 1;;
esac'''


def _install(tmp_path: Path, token_input: str, fake_body: str):
    token_file = tmp_path / "home" / ".popory" / "claude_oauth_token"
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path / "home"),
           "POPORY_CLAUDE_TOKEN_FILE": str(token_file),
           "CLAUDE_BIN": str(_fake_claude(tmp_path, fake_body)),
           "POPORY_USAGE_PROBE": "0"}
    r = subprocess.run(["bash", str(INSTALLER)], input=token_input, capture_output=True, text=True, env=env)
    return r, token_file


def test_installer_installs_valid_token_with_safe_permissions(tmp_path):
    r, f = _install(tmp_path, "good-token\n", _FAKE_OK)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f.read_text() == "good-token\n"
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert stat.S_IMODE(f.parent.stat().st_mode) == 0o700
    assert "control=REJECTED" in r.stdout
    assert "good-token" not in r.stdout.replace("setup-token", "")  # 토큰은 어디에도 출력되지 않는다


def test_installer_rejects_bad_token_and_writes_nothing(tmp_path):
    """검증 실패 시 설치하지 않는다 — 동작 중인 설치를 잘못된 토큰으로 덮어쓰지 않기 위해서다."""
    r, f = _install(tmp_path, "bad-token\n", _FAKE_OK)
    assert r.returncode == 1
    assert not f.exists()
    assert "설치하지 않았습니다" in r.stdout


def test_installer_does_not_overwrite_existing_token_on_failure(tmp_path):
    f = tmp_path / "home" / ".popory" / "claude_oauth_token"
    f.parent.mkdir(parents=True)
    f.write_text("good-token\n")
    r, _ = _install(tmp_path, "bad-token\n", _FAKE_OK)
    assert r.returncode == 1
    assert f.read_text() == "good-token\n"


def test_installer_aborts_when_env_token_is_ignored(tmp_path):
    """대조군: 틀린 토큰으로도 성공하면 환경변수 토큰이 적용되지 않은 것 — [1] 의 성공은 증거가 아니다."""
    r, f = _install(tmp_path, "good-token\n", 'echo "pong"; exit 0')
    assert r.returncode == 1
    assert not f.exists()
    assert "적용되지 않고" in r.stdout


def test_installer_accepts_pasted_export_line(tmp_path):
    r, f = _install(tmp_path, "export CLAUDE_CODE_OAUTH_TOKEN=good-token\n", _FAKE_OK)
    assert r.returncode == 0, r.stdout
    assert f.read_text() == "good-token\n"


def test_installer_rejects_empty_input(tmp_path):
    r, f = _install(tmp_path, "\n", _FAKE_OK)
    assert r.returncode == 1 and not f.exists()
