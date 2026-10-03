# 워커가 **지금 어떤 코드로 돌고 있는지** — 시작할 때 읽은 커밋, 지금 디스크의 커밋, origin/main 과의 거리.
#
# 왜 필요한가: 2026-09-10 에 고친 발행 수정(#53)이 10-03 까지 한 번도 실행되지 않았다. 워커가 옛 코드로 계속 돌았는데
# (pull 만 하고 재시작을 안 했거나, 엉뚱한 서비스를 재시작했거나, 옛 브랜치였거나) 아무도 몰랐고, 그동안 같은 오류가
# 44건 쌓였다. 코드를 고쳐도 워커가 그 코드를 쓰는지 알 수 없으면 "고쳤다" 는 말이 검증되지 않는다.
#
# 세 가지를 가른다:
#   1) pull 은 됐는데 재시작 안 됨 — 시작할 때 읽은 커밋(LOADED_COMMIT) != 지금 디스크의 HEAD
#   2) pull 자체를 안 함            — origin/main 이 로컬 HEAD 의 조상이 아님
#   3) main 이 아닌 브랜치           — 옛 브랜치에서 돌고 있을 수 있다
# 모든 git 호출은 실패해도 None 을 돌려준다 — 부가 정보가 워커를 죽이거나 하트비트를 막으면 안 된다.
# origin 확인은 ls-remote(읽기 전용)만 쓴다: fetch 는 사용자가 쓰는 저장소의 refs 를 바꾸기 때문이다.
import subprocess
import time
from pathlib import Path

# popory_content/ → services/content/ → services/ → 저장소 루트
REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_BRANCH = "main"
GIT_TIMEOUT = 10
REMOTE_TIMEOUT = 15


def _git(*args: str, timeout: int = GIT_TIMEOUT) -> "subprocess.CompletedProcess[str] | None":
    try:
        return subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def _out(*args: str, timeout: int = GIT_TIMEOUT) -> "str | None":
    r = _git(*args, timeout=timeout)
    if r is None or r.returncode != 0:
        return None
    return r.stdout.strip() or None


# 프로세스가 이 모듈을 불러온 시점의 커밋 = 이 프로세스가 실제로 실행 중인 코드의 버전이다.
LOADED_COMMIT = _out("rev-parse", "HEAD")
STARTED_AT = int(time.time())


def _short(sha: "str | None") -> "str | None":
    return sha[:7] if sha else None


def _behind_origin(head: "str | None") -> dict:
    """origin/main 과 비교. state: up_to_date | behind | unknown. count 는 객체를 아는 경우에만."""
    unknown = {"state": "unknown", "count": None}
    if not head:
        return unknown
    r = _git("ls-remote", "origin", f"refs/heads/{BASE_BRANCH}", timeout=REMOTE_TIMEOUT)
    if r is None or r.returncode != 0 or not r.stdout.strip():
        return unknown
    remote = r.stdout.split()[0]
    if remote == head:
        return {"state": "up_to_date", "count": 0}
    have = _git("cat-file", "-e", f"{remote}^{{commit}}")
    if have is None or have.returncode != 0:
        return {"state": "behind", "count": None}     # 원격 커밋을 로컬이 모른다 = 가져오지 않았다 = 뒤처짐
    anc = _git("merge-base", "--is-ancestor", remote, head)
    if anc is not None and anc.returncode == 0:
        return {"state": "up_to_date", "count": 0}      # 로컬이 원격을 포함한다(앞서 있거나 같음)
    n = _out("rev-list", "--count", f"{head}..{remote}")
    return {"state": "behind", "count": int(n) if n and n.isdigit() else None}


def runtime_snapshot() -> dict:
    """어드민 화면용 실행 버전 정보. 실패한 항목은 None."""
    head = _out("rev-parse", "HEAD")
    subject = _out("log", "-1", "--format=%s", LOADED_COMMIT) if LOADED_COMMIT else None
    return {
        "loaded_commit": _short(LOADED_COMMIT),
        "loaded_subject": subject[:80] if subject else None,
        "head_commit": _short(head),
        "branch": _out("rev-parse", "--abbrev-ref", "HEAD"),
        "started_at": STARTED_AT,
        "pulled_not_restarted": bool(LOADED_COMMIT and head and LOADED_COMMIT != head),
        "behind": _behind_origin(head),
    }
