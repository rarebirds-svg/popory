# claude CLI 경로 탐색 — 기본 경로가 사라져도 알려진 설치 위치에서 찾는다.
from popory_brief import claude_bin


def _exe(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def test_override_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("BRIEF_CLAUDE_BIN", "/stub/claude")
    assert claude_bin.find_claude_bin() == "/stub/claude"


def test_falls_back_to_native_install(monkeypatch, tmp_path):
    monkeypatch.delenv("BRIEF_CLAUDE_BIN", raising=False)
    monkeypatch.setattr(claude_bin, "DEFAULT_CLAUDE_BIN", str(tmp_path / "gone" / "claude"))
    monkeypatch.setenv("HOME", str(tmp_path))
    native = _exe(tmp_path / ".local" / "bin" / "claude")
    assert claude_bin.find_claude_bin() == str(native)


def test_nothing_found_returns_default(monkeypatch, tmp_path):
    monkeypatch.delenv("BRIEF_CLAUDE_BIN", raising=False)
    monkeypatch.setattr(claude_bin, "DEFAULT_CLAUDE_BIN", str(tmp_path / "gone" / "claude"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert claude_bin.find_claude_bin() == str(tmp_path / "gone" / "claude")
