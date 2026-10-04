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
    (cwd / name).parent.mkdir(parents=True, exist_ok=True)
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
    assert s["behind"] == {"state": "up_to_date", "count": 0, "worker_files": 0}
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


def _push_from_other(origin, tmp_path, *names: str) -> None:
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(origin), str(other))
    for n in names:
        commit(other, n)
    git(other, "push", "-q", "origin", "main")


def test_not_pulled_is_detected_with_commit_count(repos, tmp_path):
    origin, work, _ = repos
    _push_from_other(origin, tmp_path, "x", "y")
    git(work, "fetch", "-q", "origin")                    # 객체는 알지만 아직 병합 안 함 → 개수를 셀 수 있다
    s = runtime_info.runtime_snapshot()
    assert s["behind"]["state"] == "behind" and s["behind"]["count"] == 2
    assert s["pulled_not_restarted"] is False


def test_portal_only_commits_do_not_touch_worker_code(repos, tmp_path):
    """포털·API·문서만 바뀐 새 커밋 — 뒤처지긴 했지만 워커 코드는 그대로라 재시작이 필요 없다(경고 소음 방지)."""
    origin, work, _ = repos
    _push_from_other(origin, tmp_path, "apps/portal/src/page.tsx", "workers/api/src/a.ts", "README.md")
    s = runtime_info.runtime_snapshot()                   # 일부러 fetch 안 함 — 워커가 스스로 받아 본다
    assert s["behind"] == {"state": "behind", "count": 3, "worker_files": 0}


def test_worker_code_commits_are_counted(repos, tmp_path):
    origin, _, _ = repos
    _push_from_other(origin, tmp_path, "services/content/popory_content/video.py",
                     "services/content/popory_content/tts.py", "apps/portal/x.tsx")
    s = runtime_info.runtime_snapshot()
    assert s["behind"] == {"state": "behind", "count": 3, "worker_files": 2}


def test_tests_tools_and_logs_under_services_content_are_not_worker_code(repos, tmp_path):
    origin, _, _ = repos
    _push_from_other(origin, tmp_path, "services/content/tests/test_x.py", "services/content/tools/t.py",
                     "services/content/logs/2026-10-04.log")
    assert runtime_info.runtime_snapshot()["behind"]["worker_files"] == 0


def test_other_services_content_files_count_as_worker_code(repos, tmp_path):
    origin, _, _ = repos
    _push_from_other(origin, tmp_path, "services/content/requirements.txt", "services/content/assets/logo.png")
    assert runtime_info.runtime_snapshot()["behind"]["worker_files"] == 2


def test_checking_does_not_touch_the_users_refs(repos, tmp_path):
    """워커가 새 커밋을 받아 보더라도 origin/main·FETCH_HEAD 는 그대로다 — 사용자의 git pull 이 예전처럼 동작해야 한다."""
    origin, work, first = repos
    before = git(work, "rev-parse", "origin/main")
    _push_from_other(origin, tmp_path, "services/content/popory_content/video.py")
    runtime_info.runtime_snapshot()
    assert git(work, "rev-parse", "origin/main") == before == first       # 원격 추적 ref 불변
    assert not (work / ".git" / "FETCH_HEAD").exists()
    assert git(work, "rev-parse", runtime_info.PRIVATE_REF)               # 객체는 전용 ref 로만 받았다


def test_fetch_failure_leaves_worker_files_unknown(repos, tmp_path, monkeypatch):
    """받아 올 수 없으면 개수도 변경 파일도 모른다 — 화면은 예전처럼 '뒤처짐' 으로 경고한다(과소 경고보다 낫다)."""
    origin, _, _ = repos
    _push_from_other(origin, tmp_path, "x")
    real = runtime_info._git

    def no_fetch(*args, **kw):
        return None if args and args[0] == "fetch" else real(*args, **kw)
    monkeypatch.setattr(runtime_info, "_git", no_fetch)
    assert runtime_info.runtime_snapshot()["behind"] == {"state": "behind", "count": None, "worker_files": None}


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
    assert runtime_info.runtime_snapshot()["behind"] == {"state": "unknown", "count": None, "worker_files": None}


def test_not_a_git_checkout_returns_nones_without_raising(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_info, "REPO_ROOT", tmp_path)       # git 저장소가 아니다
    monkeypatch.setattr(runtime_info, "LOADED_COMMIT", None)
    s = runtime_info.runtime_snapshot()
    assert s["head_commit"] is None and s["branch"] is None and s["loaded_commit"] is None
    assert s["pulled_not_restarted"] is False
    assert s["behind"] == {"state": "unknown", "count": None, "worker_files": None}


def test_missing_git_binary_does_not_raise(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(subprocess, "run", boom)
    assert runtime_info._out("rev-parse", "HEAD") is None
