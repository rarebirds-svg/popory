# keychain 토큰 파싱과 oauth/usage 응답 해석 단위 테스트.
import json

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
