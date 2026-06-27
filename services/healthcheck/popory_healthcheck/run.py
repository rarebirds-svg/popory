# 헬스체크 엔트리 — 점검 실행 → 모드별 발송 판단 → 텔레그램 발송 → 상태 저장.
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from popory_healthcheck import checks, report
from popory_healthcheck.telegram import send_telegram, TelegramError

KST = timezone(timedelta(hours=9))
PORTAL = "https://poporyfamily.com"
API = "https://api.poporyfamily.com/health"
BRIEF = "https://poporyfamily.com/p/brief-realestate/"
WORKER_LOG_DIR = "/Users/daegong/projects/popory/services/content/logs"
STATE_FILE = str(Path(__file__).resolve().parent.parent / "state" / "last.json")


def _today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _yesterday() -> str:
    return (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")


def _log_path(date_str: str) -> Path:
    return Path(WORKER_LOG_DIR) / f"{date_str}.log"


def _read_log(date_str: str) -> str:
    try:
        return _log_path(date_str).read_text(encoding="utf-8")
    except OSError:
        return ""


def _recent_log_path() -> str:
    today = _log_path(_today())
    if today.exists():
        return str(today)
    yday = _log_path(_yesterday())
    if yday.exists():
        return str(yday)
    return str(today)


def gather() -> list[tuple[str, str, str]]:
    log_text = _read_log(_yesterday()) + "\n" + _read_log(_today())
    log_path = _recent_log_path()
    out = []
    out.append(("포털", *checks.check_http("포털", PORTAL)))
    out.append(("API", *checks.check_http("API", API)))
    out.append(("브리핑", *checks.check_brief_published(BRIEF, _today())))
    out.append(("워커데몬", *checks.check_daemon("com.popory.content-worker")))
    out.append(("이미지데몬", *checks.check_daemon("com.popory.imagegen")))
    out.append(("워커로그", *checks.check_log_freshness(log_path, 24 * 3600)))
    out.append(("자원한도", *checks.scan_log_markers(log_text)))
    out.append(("콘텐츠루틴", *checks.check_content_routine(log_text)))
    return out


def _load_prev() -> dict | None:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _save_state(results) -> None:
    Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(report.state_signature(results), f, ensure_ascii=False)


def run(mode: str) -> int:
    results = gather()
    prev = _load_prev()
    if report.should_send(mode, results, prev):
        header = "아침 점검" if mode == "am" else "저녁 점검"
        text = report.format_report(results, header)
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        try:
            send_telegram(token, chat_id, text)
        except TelegramError as e:
            print(f"telegram send failed: {e}", file=sys.stderr)
            return 1
    # 발송 성공 시에만 상태 저장 — 발송 실패(return 1)면 상태 미갱신으로 다음 실행이 재시도.
    _save_state(results)
    return 0


def main() -> int:
    mode = "am"
    for a in sys.argv[1:]:
        if a.startswith("--mode="):
            mode = a.split("=", 1)[1]
    if mode not in ("am", "pm"):
        print("usage: run --mode=am|pm", file=sys.stderr)
        return 2
    return run(mode)


if __name__ == "__main__":
    sys.exit(main())
