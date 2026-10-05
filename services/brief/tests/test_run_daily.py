# run_daily.sh — 포털 발행 실패를 재시도에 올리는지, 메일 스위치가 발송 단계를 막는지 검증.
"""generate·publish·send CLI 와 카테고리 목록은 스텁으로 바꿔 끼우고 셸 스크립트만 실제로 돌린다.

2026-10 전 카테고리를 portal_only 로 돌린 뒤로 포털 발행이 유일한 전달 경로다. 그런데 run_daily 는
발행 실패를 로그에만 남겨 done 이 failed=none 으로 끝났고, pending·재시도가 없어 그날 브리핑이
빠질 수 있었다."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "run_daily.sh"
DATE = "2026-10-05"

_CATEGORIES_PY = '''
import json, os
class _C:
    def __init__(self, slug, mode):
        self.slug, self.delivery_mode = slug, mode
    def runs_on(self, d):
        return True
def list_categories():
    return [_C(s, m) for s, m in json.loads(os.environ["STUB_CATEGORIES"])]
'''

# 생성 스텁 — 실제 generate_brief 처럼 /tmp 에 본문·메타를 남긴다.
_GENERATE_PY = '''
import os, sys
slug = sys.argv[sys.argv.index("--category") + 1]
date = sys.argv[sys.argv.index("--date") + 1]
with open(os.environ["STUB_CALLS"], "a") as f:
    f.write(f"generate {slug}\\n")
open(f"/tmp/brief_{slug}_{date}.md", "w").write("본문")
open(f"/tmp/brief_{slug}_{date}.meta.json", "w").write("{}")
'''

# 발행 스텁 — STUB_PUBLISH_FAIL 에 든 카테고리는 401(exit 3).
_PUBLISH_PY = '''
import os, sys
area = sys.argv[sys.argv.index("--area") + 1]
with open(os.environ["STUB_CALLS"], "a") as f:
    f.write(f"publish {area}\\n")
sys.exit(3 if area.removeprefix("brief-") in os.environ.get("STUB_PUBLISH_FAIL", "").split(",") else 0)
'''

_SEND_PY = '''
import os
with open(os.environ["STUB_CALLS"], "a") as f:
    f.write("send\\n")
'''


@pytest.fixture
def env(tmp_path):
    brief = tmp_path / "brief"
    (brief / "logs").mkdir(parents=True)
    (brief / "secrets").mkdir()
    (brief / "secrets" / "portal_endpoints.env").write_text("POPORY_PORTAL_API_BASE=http://x.invalid\n")
    (brief / "popory_brief").mkdir()
    (brief / "popory_brief" / "__init__.py").write_text("")
    (brief / "popory_brief" / "categories.py").write_text(_CATEGORIES_PY)
    (brief / "generate_brief.py").write_text(_GENERATE_PY)
    (brief / "publish_to_portal.py").write_text(_PUBLISH_PY)
    (brief / "send_gmail.py").write_text(_SEND_PY)
    (brief / "fetch_subscribers.py").write_text(_SEND_PY)
    (brief / "fetch_custom_topics.py").write_text("")   # 활성 커스텀 주제 없음
    (brief / "write_pending.py").write_text(
        (Path(__file__).resolve().parent.parent / "write_pending.py").read_text())
    pending = tmp_path / "pending"
    pending.mkdir()
    # /tmp 산출 파일이 다른 테스트·실제 실행과 섞이지 않게 슬러그를 매번 새로 만든다.
    tag = uuid.uuid4().hex[:8]
    slugs = {"a": f"ta{tag}", "b": f"tb{tag}"}
    e = {
        **os.environ,
        "BRIEF_DIR": str(brief),
        "BRIEF_VENV_PY": sys.executable,
        "BRIEF_PENDING_DIR": str(pending),
        "PYTHONPATH": str(brief),
        "STUB_CALLS": str(tmp_path / "calls.txt"),
        "STUB_CATEGORIES": json.dumps([[slugs["a"], "portal_only"], [slugs["b"], "standalone"]]),
    }
    e.pop("BRIEF_MAIL_ENABLED", None)
    yield {"brief": brief, "pending": pending, "env": e, "slugs": slugs, "calls": tmp_path / "calls.txt"}
    for s in slugs.values():
        for p in Path("/tmp").glob(f"brief_*{s}_{DATE}*"):
            p.unlink(missing_ok=True)


def _run(env, *args, **extra):
    # cwd 를 스텁 디렉토리로 — `python -c` 는 cwd 를 sys.path 맨 앞에 둬서, 실제 popory_brief 가
    # 있는 곳에서 돌리면 스텁 카테고리 대신 실제 카테고리를 읽는다.
    r = subprocess.run(["bash", str(SCRIPT), "--now", f"--date={DATE}", *args], cwd=env["brief"],
                       env={**env["env"], **extra}, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    calls = env["calls"].read_text().splitlines() if env["calls"].exists() else []
    log = (env["brief"] / "logs" / f"{DATE}.log").read_text()
    return r.stdout, calls, log


def test_publish_failure_is_reported_and_queued_for_retry(env):
    a, b = env["slugs"]["a"], env["slugs"]["b"]
    out, _, log = _run(env, STUB_PUBLISH_FAIL=a)
    assert f"__RUN_PUBLISH_FAIL_CATS__={a}" in out
    assert f"publish_fail={a}" in log and "failed=none" in log
    pending = json.loads((env["pending"] / f"brief_pending_{DATE}.json").read_text())
    assert pending["categories"] == [a]
    # 401·5xx 는 금방 안 풀린다 — 10분 폴링마다 두드리지 않게 재시도 시각을 미룬다.
    assert pending["reset_at"] > 0
    assert Path(f"/tmp/brief_pubfail_{a}_{DATE}").exists()
    assert not Path(f"/tmp/brief_pubfail_{b}_{DATE}").exists()


def test_retry_republishes_without_regenerating(env):
    """발행만 실패한 카테고리는 생성본을 다시 발행한다 — 다시 생성하면 LLM 사용량을 또 쓴다."""
    a = env["slugs"]["a"]
    _run(env, STUB_PUBLISH_FAIL=a)
    env["calls"].unlink()
    out, calls, log = _run(env, f"--only={a}")
    assert calls == [f"publish brief-{a}"]
    assert f"republish only category={a}" in log
    assert "__RUN_PUBLISH_FAIL_CATS__=" in out.splitlines()   # 재발행 성공 — 남은 항목 없음
    assert not Path(f"/tmp/brief_pubfail_{a}_{DATE}").exists()


def test_all_published_clears_pending(env):
    _run(env, STUB_PUBLISH_FAIL=env["slugs"]["a"])
    _, _, log = _run(env)
    assert not (env["pending"] / f"brief_pending_{DATE}.json").exists()
    assert log.strip().splitlines()[-1].endswith('"pending cleared (no retryable failures)"}')


def test_mail_switch_off_by_default_skips_send(env):
    """delivery_mode 가 메일 모드로 남은 카테고리가 있어도 스위치가 꺼져 있으면 보내지 않는다."""
    _, calls, log = _run(env)
    assert "send" not in calls
    assert "mail disabled" in log and "standalone=1" in log
