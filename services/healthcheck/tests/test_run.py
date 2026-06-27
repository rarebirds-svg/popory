# 엔트리 run 의 발송/억제/상태저장 흐름 테스트(점검·발송 monkeypatch).
import json
from popory_healthcheck import run as runmod


def _stub_gather(results):
    return lambda: results


def test_am_sends_and_saves(tmp_path, monkeypatch):
    results = [("포털", "ok", "정상")]
    sent = {}
    monkeypatch.setattr(runmod, "gather", _stub_gather(results))
    monkeypatch.setattr(runmod, "send_telegram", lambda t, c, text: sent.update(text=text))
    monkeypatch.setattr(runmod, "STATE_FILE", str(tmp_path / "last.json"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "C")
    rc = runmod.run("am")
    assert rc == 0
    assert "포털" in sent["text"]
    assert json.load(open(tmp_path / "last.json"))["포털"] == "ok"


def test_pm_silent_when_ok(tmp_path, monkeypatch):
    results = [("포털", "ok", "정상")]
    sent = {}
    monkeypatch.setattr(runmod, "gather", _stub_gather(results))
    monkeypatch.setattr(runmod, "send_telegram", lambda t, c, text: sent.update(text=text))
    monkeypatch.setattr(runmod, "STATE_FILE", str(tmp_path / "last.json"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "C")
    rc = runmod.run("pm")
    assert rc == 0
    assert "text" not in sent  # 발송 안 함
