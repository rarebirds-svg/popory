# retry_pending.sh — 처리할 pending 고르기(전날 포함)와 원래 날짜로 재시도하는지 검증.
"""run_daily.sh·write_pending.py·healthcheck 는 스텁으로 바꿔 끼우고 셸 스크립트만 실제로 돌린다.

2026-09-14 09:27 claude 한도로 7개 카테고리가 실패했고 리셋이 09-15 01:00 이었다. retry_pending 은
오늘 날짜 pending 파일만 봐서 자정 뒤엔 전날 파일을 못 찾았고, 그날 브리핑이 통째로 유실됐다."""
from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "retry_pending.sh"
KST = datetime.timezone(datetime.timedelta(hours=9))


def _day(offset: int) -> str:
    return (datetime.datetime.now(KST) + datetime.timedelta(days=offset)).strftime("%Y-%m-%d")


_RESULT_MARKERS = ("echo '__RUN_LIMIT_FAIL_CATS__='\n"
                   "echo '__RUN_AUTH_FAIL_CATS__='\n"
                   "echo '__RUN_LIMIT_RESET__=0'\n")


def _stub_run_daily(brief: Path, calls: Path, body: str = _RESULT_MARKERS):
    """run_daily 스텁 — 받은 인자를 기록하고 body 를 실행한다(기본은 전건 성공 보고)."""
    (brief / "run_daily.sh").write_text("#!/bin/bash\n" f"echo \"$*\" >> '{calls}'\n" + body)


@pytest.fixture
def env(tmp_path):
    brief = tmp_path / "brief"
    (brief / "logs").mkdir(parents=True)
    (brief / "secrets").mkdir()
    (brief / "secrets" / "portal_endpoints.env").write_text("POPORY_PORTAL_API_BASE=http://x.invalid\n")
    shutil.copy(Path(__file__).resolve().parent.parent / "write_pending.py", brief / "write_pending.py")
    calls = tmp_path / "calls.txt"
    _stub_run_daily(brief, calls)
    pending = tmp_path / "pending"
    pending.mkdir()
    e = {
        **os.environ,
        "BRIEF_DIR": str(brief),
        "BRIEF_VENV_PY": sys.executable,
        "BRIEF_PENDING_DIR": str(pending),
        "BRIEF_HC_DIR": str(tmp_path / "no-healthcheck"),   # 인증 프로브 없음
    }
    return {"brief": brief, "pending": pending, "calls": calls, "env": e}


def _write_pending(env, date: str, reset_at: int, cats=("naver",), retry_count=0):
    path = env["pending"] / f"brief_pending_{date}.json"
    path.write_text(json.dumps({"date": date, "reset_at": reset_at, "categories": list(cats),
                                "custom_topics": [], "retry_count": retry_count}))
    return path


def _run(env):
    r = subprocess.run(["bash", str(SCRIPT)], env=env["env"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return env["calls"].read_text().splitlines() if env["calls"].exists() else []


def test_retries_yesterdays_pending_for_its_own_date(env):
    """자정을 넘겨 한도가 풀린 전날 항목은 원래 날짜로 재시도한다."""
    yday = _day(-1)
    path = _write_pending(env, yday, reset_at=0, cats=("naver", "realestate-pick5"))

    calls = _run(env)

    assert calls == [f"--now --only=(naver|realestate-pick5) --date={yday}"]
    assert not path.exists()                                # 전건 복구 → pending 삭제
    log = (env["brief"] / "logs" / f"{yday}.log").read_text()
    assert "retry complete" in log                          # 로그도 원래 날짜 파일에


def test_todays_pending_is_pinned_to_its_date(env):
    """오늘 항목도 날짜를 고정한다 — 23시대 재시도가 자정을 넘기면 파일 날짜가 갈려 발행이 빠진다.
    (날짜가 오늘이면 generate 는 published_at 을 실행 시각으로 둔다.)"""
    _write_pending(env, _day(0), reset_at=0)

    assert _run(env) == [f"--now --only=(naver) --date={_day(0)}"]


def test_run_daily_abort_keeps_pending(env):
    """run_daily 가 결과 마커 전에 죽으면(카테고리 스캔 중단 등) 복구가 아니다 — pending 을 지우지 않는다."""
    _stub_run_daily(env["brief"], env["calls"], "echo 'boom' >&2\nexit 1\n")
    path = _write_pending(env, _day(0), reset_at=0, cats=("naver", "realestate-pick5"), retry_count=2)

    _run(env)

    kept = json.loads(path.read_text())
    assert kept["categories"] == ["naver", "realestate-pick5"]
    assert kept["retry_count"] == 2                     # 사람이 고쳐야 풀리는 원인 — 횟수를 태우지 않는다
    assert kept["reset_at"] > int(datetime.datetime.now().timestamp())   # 바로 다시 돌지 않게 미룬다
    assert "retry aborted" in (env["brief"] / "logs" / f"{_day(0)}.log").read_text()


def test_run_daily_clean_exit_without_markers_still_clears(env):
    """정상 종료인데 마커가 없으면(대상 카테고리가 비활성·삭제) 예전처럼 지운다."""
    _stub_run_daily(env["brief"], env["calls"], "exit 0\n")
    path = _write_pending(env, _day(0), reset_at=0)

    _run(env)

    assert not path.exists()


def test_not_yet_reset_yesterday_does_not_block_today(env):
    """전날 항목이 아직 리셋 전이면 건드리지 않고 오늘 항목을 처리한다."""
    far = int(datetime.datetime.now().timestamp()) + 3600
    yday_path = _write_pending(env, _day(-1), reset_at=far)
    _write_pending(env, _day(0), reset_at=0, cats=("legal-ai",))

    assert _run(env) == [f"--now --only=(legal-ai) --date={_day(0)}"]
    assert yday_path.exists()


def test_nothing_due_does_nothing(env):
    far = int(datetime.datetime.now().timestamp()) + 3600
    _write_pending(env, _day(0), reset_at=far)

    assert _run(env) == []


def test_older_than_yesterday_is_ignored(env):
    _write_pending(env, _day(-2), reset_at=0)

    assert _run(env) == []
