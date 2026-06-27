# auto_create 의 주제 선택·배정 규칙과 run 흐름 단위 테스트.
import json
import pytest
from popory_content import auto_create
from popory_content.auto_create import select_assignments
from popory_content.portal_client import PortalError


# ---------------------------------------------------------------------------
# select_assignments 단위 테스트
# ---------------------------------------------------------------------------

def test_two_recs_youtube_then_shorts():
    recs = [{"id": "a", "title": "오래된것"}, {"id": "b", "title": "새것"}]
    out = select_assignments(recs)
    assert out == [("youtube", recs[0]), ("shorts", recs[1])]


def test_one_rec_same_topic_both():
    recs = [{"id": "a", "title": "하나"}]
    out = select_assignments(recs)
    assert out == [("youtube", recs[0]), ("shorts", recs[0])]


def test_empty_returns_empty():
    assert select_assignments([]) == []


# ---------------------------------------------------------------------------
# run() 흐름 테스트 — 부분 실패 / 전체 성공
# ---------------------------------------------------------------------------

class _FakeClient:
    """PortalClient 대역. fail_platform 이 지정된 플랫폼 POST 에서 PortalError 발생."""

    def __init__(self, fail_platform=None):
        self._fail_platform = fail_platform

    def get(self, url):
        return {
            "recommendations": [
                {"id": "r1", "title": "주제A"},
                {"id": "r2", "title": "주제B"},
            ]
        }

    def post(self, url, json=None):
        platform = (json or {}).get("platform")
        if platform == self._fail_platform:
            raise PortalError(f"서버 오류 — {platform}", exit_code=500)
        return {"id": f"job-{platform}"}


def _read_logs(log_dir):
    """tmp_path 아래 날짜 JSONL 파일을 모두 읽어 record 리스트로 반환."""
    records = []
    for f in sorted(log_dir.glob("*.log")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def test_run_partial_failure_status_partial(tmp_path, monkeypatch):
    """POST 중 하나가 PortalError 이면 최종 요약 status 가 'partial' 이어야 한다."""
    monkeypatch.setenv("POPORY_RECOMMEND_OWNER", "user-sub-test")
    monkeypatch.setattr(auto_create, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(auto_create, "_client", lambda: _FakeClient(fail_platform="shorts"))

    rc = auto_create.run()

    assert rc == 0
    records = _read_logs(tmp_path)
    summary = records[-1]
    assert summary["status"] == "partial"
    # create_fail 로그도 기록되어야 한다.
    fail_logs = [r for r in records if r.get("status") == "create_fail"]
    assert len(fail_logs) == 1
    assert fail_logs[0]["platform"] == "shorts"


def test_run_all_success_status_ok(tmp_path, monkeypatch):
    """두 POST 모두 성공하면 최종 요약 status 가 'ok' 이고 created 에 2건이어야 한다."""
    monkeypatch.setenv("POPORY_RECOMMEND_OWNER", "user-sub-test")
    monkeypatch.setattr(auto_create, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(auto_create, "_client", lambda: _FakeClient())

    rc = auto_create.run()

    assert rc == 0
    records = _read_logs(tmp_path)
    summary = records[-1]
    assert summary["status"] == "ok"
    assert len(summary["created"]) == 2
