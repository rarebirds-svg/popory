# 텔레그램 Bot API sendMessage 발송 헬퍼.
import requests


class TelegramError(Exception):
    pass


def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    except requests.RequestException as e:
        raise TelegramError(f"network: {e}") from e
    if resp.status_code >= 400 or not resp.json().get("ok", False):
        raise TelegramError(f"telegram {resp.status_code}: {resp.text[:200]}")
