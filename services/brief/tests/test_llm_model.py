# resolve_model — 어드민 설정 조회와 fail-open 동작 검증.
"""모델 설정을 못 읽어도 브리핑은 기본 모델로 돌아야 한다(fail-open)."""
from __future__ import annotations

import pytest

from popory_brief import llm_model

FALLBACK = "claude-sonnet-4-6"


class _Resp:
    def __init__(self, status: int, payload: object):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture
def signed(monkeypatch):
    """토큰 획득이 성공한 상태로 고정 — 조회 응답만 바꿔가며 본다."""
    monkeypatch.setattr(llm_model, "_token", lambda: ("https://api.example.com", "tok"))


def test_uses_configured_model(signed, monkeypatch):
    monkeypatch.setattr(llm_model.requests, "get",
                        lambda *a, **k: _Resp(200, {"models": {"brief_issue": "claude-opus-5"}}))
    assert llm_model.resolve_model("brief_issue", FALLBACK) == "claude-opus-5"


def test_falls_back_when_feature_absent(signed, monkeypatch):
    monkeypatch.setattr(llm_model.requests, "get", lambda *a, **k: _Resp(200, {"models": {}}))
    assert llm_model.resolve_model("brief_issue", FALLBACK) == FALLBACK


def test_falls_back_on_error_status(signed, monkeypatch):
    monkeypatch.setattr(llm_model.requests, "get", lambda *a, **k: _Resp(403, {}))
    assert llm_model.resolve_model("brief_issue", FALLBACK) == FALLBACK


def test_falls_back_on_network_error(signed, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(llm_model.requests, "get", _boom)
    assert llm_model.resolve_model("brief_issue", FALLBACK) == FALLBACK


def test_falls_back_without_portal_base(monkeypatch):
    # 키·base 가 없는 환경(개발·테스트)에서 토큰 서명까지 가지 않는다.
    monkeypatch.delenv("POPORY_PORTAL_API_BASE", raising=False)
    assert llm_model.resolve_model("brief_issue", FALLBACK) == FALLBACK
