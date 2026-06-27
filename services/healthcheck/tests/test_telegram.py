# 텔레그램 Bot API 발송 함수 단위 테스트.
import pytest
import responses
from popory_healthcheck.telegram import send_telegram, TelegramError


@responses.activate
def test_send_ok():
    responses.add(responses.POST, "https://api.telegram.org/botTOK/sendMessage", json={"ok": True}, status=200)
    send_telegram("TOK", "123", "안녕하세요.")  # 예외 없으면 통과
    assert responses.calls[0].request.body is not None


@responses.activate
def test_send_failure_raises():
    responses.add(responses.POST, "https://api.telegram.org/botTOK/sendMessage", json={"ok": False}, status=400)
    with pytest.raises(TelegramError):
        send_telegram("TOK", "123", "x")
