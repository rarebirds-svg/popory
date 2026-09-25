# 공급자 대체 정책 — Gemini 실패 시 claude 로 대신 쓸지, 어떤 모델로 쓸지.
import pytest

from popory_brief.fallback import DEFAULT_FALLBACK_MODEL, fallback_model


@pytest.fixture
def claude_bin(tmp_path):
    b = tmp_path / "claude"
    b.write_text("")
    return str(b)


def test_defaults_to_sonnet_when_cli_exists(monkeypatch, claude_bin):
    monkeypatch.delenv("BRIEF_FALLBACK_MODEL", raising=False)
    assert fallback_model(claude_bin) == DEFAULT_FALLBACK_MODEL == "claude-sonnet-4-6"


def test_custom_claude_model(monkeypatch, claude_bin):
    monkeypatch.setenv("BRIEF_FALLBACK_MODEL", " claude-opus-4-8 ")
    assert fallback_model(claude_bin) == "claude-opus-4-8"


@pytest.mark.parametrize("raw", ["off", "OFF", "none", "0", "false", ""])
def test_can_be_turned_off(monkeypatch, claude_bin, raw):
    monkeypatch.setenv("BRIEF_FALLBACK_MODEL", raw)
    assert fallback_model(claude_bin) is None


def test_gemini_model_is_not_a_fallback(monkeypatch, claude_bin):
    """같은 공급자 재호출은 대체가 아니다 — 재시도는 gemini_client 가 이미 한다."""
    monkeypatch.setenv("BRIEF_FALLBACK_MODEL", "gemini-3-pro")
    assert fallback_model(claude_bin) is None


def test_no_fallback_without_cli(monkeypatch, tmp_path):
    """CLI 가 없는 머신에서 대체를 시도하면 원래 Gemini 오류가 init 실패로 덮인다."""
    monkeypatch.delenv("BRIEF_FALLBACK_MODEL", raising=False)
    assert fallback_model(str(tmp_path / "missing")) is None
