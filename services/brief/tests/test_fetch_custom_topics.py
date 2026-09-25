# fetch_custom_topics — 활성 커스텀 주제 조회 CLI 가 빈 목록과 조회 실패를 exit code 로 가르는지 검증.
"""run_daily.sh 4단계는 이 CLI 의 exit code 로 조회 실패를 로그에 남긴다. 종전 셸 파이프라인은
JWT 서명·curl·파싱 어느 단계가 실패해도 빈 목록으로 삼켜 그날 커스텀 주제가 소리 없이 빠졌다."""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest
import responses

import fetch_custom_topics
from popory_brief import portal_client

API = "https://api.popory.test"
ACTIVE = f"{API}/api/brief/custom-topics/active"


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    """테스트용 서명 키와 포털 주소를 주입하고, 로그는 tmp 로 돌린다."""
    from jwcrypto import jwk
    key = jwk.JWK.generate(kty="EC", crv="P-256")
    public = json.loads(key.export_public())
    public.update(kid="test-kid", alg="ES256", use="sig")
    pem = key.export_to_pem(private_key=True, password=None).decode("ascii")
    keyfile = tmp_path / "key.json"
    keyfile.write_text(json.dumps({"kid": "test-kid", "public_jwk": public, "private_pem": pem}))
    monkeypatch.setenv("POPORY_BRIEF_KEY_FILE", str(keyfile))
    monkeypatch.setenv("POPORY_PORTAL_API_BASE", API)
    monkeypatch.setattr(fetch_custom_topics, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(portal_client.time, "sleep", lambda s: None)   # 5xx 재시도 대기 생략
    # 실패 레코드의 포털 전송(log._ship)이 실제 네트워크로 나가지 않게 막는다.
    monkeypatch.setattr("popory_brief.log._ship", lambda record, ts: None)
    return tmp_path


def _log_records(tmp_path: Path) -> list[dict]:
    return [json.loads(line) for f in (tmp_path / "logs").glob("*.log")
            for line in f.read_text(encoding="utf-8").splitlines()]


def _jwt_claims(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


@responses.activate
def test_prints_one_line_per_topic_for_run_daily(env, capsys):
    """run_daily.sh 가 `read -r TID TNAME` 으로 읽고 `_` 를 공백으로 되돌리는 형태 그대로."""
    responses.add(responses.GET, ACTIVE, status=200, json={"topics": [
        {"id": "t1", "name": "AI 규제 동향", "slug": "ai", "owner_email": "a@x"},
        {"id": "t2", "name": "반도체", "slug": "chip", "owner_email": "b@x"},
    ]})
    fetch_custom_topics.run()
    assert capsys.readouterr().out == "t1 AI_규제_동향\nt2 반도체\n"


@responses.activate
def test_signs_with_custom_service_area(env, capsys):
    """포털 requireService 가 받는 서비스 토큰이어야 한다 — 틀리면 prod 에서 매일 401 이다."""
    responses.add(responses.GET, ACTIVE, status=200, json={"topics": []})
    fetch_custom_topics.run()
    auth = responses.calls[0].request.headers["Authorization"]
    assert auth.startswith("Bearer ")
    assert _jwt_claims(auth.removeprefix("Bearer "))["area"] == "custom-service"


@responses.activate
def test_empty_list_is_success_with_no_output(env, capsys):
    responses.add(responses.GET, ACTIVE, status=200, json={"topics": []})
    fetch_custom_topics.run()   # SystemExit 없음 = exit 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("status,exit_code", [(401, 3), (404, 4), (500, 5)])
@responses.activate
def test_portal_error_exits_nonzero(env, capsys, status, exit_code):
    responses.add(responses.GET, ACTIVE, status=status, json={"error": "x"})
    with pytest.raises(SystemExit) as exc:
        fetch_custom_topics.run()
    assert exc.value.code == exit_code
    assert capsys.readouterr().out == ""
    rec = _log_records(env)[-1]
    assert rec["cli"] == "fetch_custom_topics" and rec["status"] == "fetch_fail"


@responses.activate
def test_network_error_exits_nonzero(env, capsys):
    responses.add(responses.GET, ACTIVE, body=portal_client.requests.ConnectionError("boom"))
    with pytest.raises(SystemExit) as exc:
        fetch_custom_topics.run()
    assert exc.value.code == 5
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("unset", ["POPORY_BRIEF_KEY_FILE", "POPORY_PORTAL_API_BASE"])
def test_missing_env_exits_nonzero(env, monkeypatch, capsys, unset):
    monkeypatch.delenv(unset)
    with pytest.raises(SystemExit) as exc:
        fetch_custom_topics.run()
    assert exc.value.code == 2
    assert _log_records(env)[-1]["status"] == "init_fail"


def test_missing_key_file_exits_nonzero_without_logging_path(env, monkeypatch, capsys):
    missing = str(env / "nope.json")
    monkeypatch.setenv("POPORY_BRIEF_KEY_FILE", missing)
    with pytest.raises(SystemExit) as exc:
        fetch_custom_topics.run()
    assert exc.value.code == 2
    assert missing not in json.dumps(_log_records(env))   # 자격증명 위치는 로그에 남기지 않는다


@pytest.mark.parametrize("body", [
    {}, "not json",
    {"topics": [{"id": "t1", "name": "정상"}, {"id": "t2"}]},   # 앞 항목만 나가면 부분 목록이 성공처럼 보인다
])
@responses.activate
def test_malformed_response_fails_instead_of_empty_list(env, capsys, body):
    """형식이 틀린 응답을 빈 목록으로 보면 종전과 같이 소리 없이 빠진다."""
    if isinstance(body, str):
        responses.add(responses.GET, ACTIVE, status=200, body=body)
    else:
        responses.add(responses.GET, ACTIVE, status=200, json=body)
    with pytest.raises(Exception):   # 처리 안 된 예외 = 프로세스 exit 1 (SystemExit 은 여기 안 걸린다)
        fetch_custom_topics.run()
    assert capsys.readouterr().out == ""
    assert _log_records(env)[-1]["status"] == "unexpected_fail"

