# 워커 실행 버전 — pull 만 하고 재시작 안 함 / pull 안 함 / main 아닌 브랜치를 가른다. 임시 git 저장소로 실제 git 을 돌려 검증한다.
import os
import subprocess
from pathlib import Path

import pytest

from popory_content import runtime_info

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
       "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True, env=ENV).stdout.strip()


def commit(cwd: Path, name: str) -> str:
    (cwd / name).write_text(name)
    git(cwd, "add", name)
    git(cwd, "commit", "-q", "-m", f"add {name}")
    return git(cwd, "rev-parse", "HEAD")


@pytest.fixture
def repos(tmp_path, monkeypatch):
    """origin(bare) 과 그 clone(워커가 도는 저장소). 환경변수로 git 설정을 격리한다."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(work))
    git(work, "checkout", "-q", "-b", "main")
    first = commit(work, "a")
    git(work, "push", "-q", "origin", "main")
    monkeypatch.setattr(runtime_info, "REPO_ROOT", work)
    monkeypatch.setattr(runtime_info, "LOADED_COMMIT", first)
    return origin, work, first


def test_up_to_date_worker_reports_no_problem(repos):
    _, _, first = repos
    s = runtime_info.runtime_snapshot()
    assert s["loaded_commit"] == s["head_commit"] == first[:7]
    assert s["pulled_not_restarted"] is False
    assert s["behind"] == {"state": "up_to_date", "count": 0}
    assert s["branch"] == "main"


def test_pulled_but_not_restarted_is_detected(repos):
    """디스크의 HEAD 는 앞으로 갔는데 프로세스는 시작할 때 읽은 코드 그대로 — 이번 사고의 형태."""
    _, work, first = repos
    new = commit(work, "b")
    git(work, "push", "-q", "origin", "main")
    s = runtime_info.runtime_snapshot()
    assert s["pulled_not_restarted"] is True
    assert s["loaded_commit"] == first[:7] and s["head_commit"] == new[:7]
    assert s["behind"]["state"] == "up_to_date"          # pull 은 했으니 origin 과는 같다


def test_not_pulled_is_detected_with_commit_count(repos, tmp_path):
    origin, work, _ = repos
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(origin), str(other))
    commit(other, "x")
    commit(other, "y")
    git(other, "push", "-q", "origin", "main")
    git(work, "fetch", "-q", "origin")                    # 객체는 알지만 아직 병합 안 함 → 개수를 셀 수 있다
    s = runtime_info.runtime_snapshot()
    assert s["behind"] == {"state": "behind", "count": 2}
    assert s["pulled_not_restarted"] is False


def test_not_pulled_and_not_fetched_is_still_behind_without_a_count(repos, tmp_path):
    origin, _, _ = repos
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(origin), str(other))
    commit(other, "x")
    git(other, "push", "-q", "origin", "main")
    s = runtime_info.runtime_snapshot()                   # 로컬은 새 커밋 객체 자체를 모른다
    assert s["behind"] == {"state": "behind", "count": None}


def test_other_branch_is_reported(repos):
    _, work, _ = repos
    git(work, "checkout", "-q", "-b", "old-feature")
    assert runtime_info.runtime_snapshot()["branch"] == "old-feature"


def test_local_ahead_of_origin_is_not_behind(repos):
    _, work, _ = repos
    commit(work, "local-only")                            # push 안 한 로컬 커밋
    assert runtime_info.runtime_snapshot()["behind"]["state"] == "up_to_date"


def test_unreachable_origin_is_unknown_not_an_error(repos):
    _, work, _ = repos
    git(work, "remote", "set-url", "origin", "/nonexistent/path.git")
    assert runtime_info.runtime_snapshot()["behind"] == {"state": "unknown", "count": None}


def test_not_a_git_checkout_returns_nones_without_raising(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_info, "REPO_ROOT", tmp_path)       # git 저장소가 아니다
    monkeypatch.setattr(runtime_info, "LOADED_COMMIT", None)
    s = runtime_info.runtime_snapshot()
    assert s["head_commit"] is None and s["branch"] is None and s["loaded_commit"] is None
    assert s["pulled_not_restarted"] is False
    assert s["behind"] == {"state": "unknown", "count": None}


def test_missing_git_binary_does_not_raise(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(subprocess, "run", boom)
    assert runtime_info._out("rev-parse", "HEAD") is None
