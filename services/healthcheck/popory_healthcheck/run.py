# 헬스체크 엔트리 — 점검 실행 → 5영역 폴딩 → 공용 포맷터로 발송 → 상태 저장.
import json
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from popory_healthcheck import checks, claude_auth, report

KST = timezone(timedelta(hours=9))
SEND_PY = "/Users/daegong/projects/scripts/ops-report/send.py"
ENV_FILE = str(Path(__file__).resolve().parent.parent / "secrets" / "env.sh")
PORTAL = "https://poporyfamily.com"
API = "https://api.poporyfamily.com/health"
BRIEF_URL_TEMPLATE = "https://poporyfamily.com/p/brief-{slug}/"
BRIEF_CATEGORY_DIR = "/Users/daegong/projects/popory/services/brief/categories"
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


def _brief_categories() -> list[tuple[str, str]]:
    """브리핑 카테고리 SKILL.md 프론트매터에서 (slug, 한글 이름)을 읽는다 — enabled: false는 제외."""
    out = []
    for skill in sorted(Path(BRIEF_CATEGORY_DIR).glob("*/SKILL.md")):
        meta = {}
        for line in skill.read_text(encoding="utf-8").splitlines()[1:]:
            if line.strip() == "---":
                break
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        if meta.get("enabled") == "false":
            continue
        if meta.get("slug") and meta.get("name"):
            out.append((meta["slug"], meta["name"]))
    return out


def gather() -> list[tuple[str, str, str]]:
    log_text = _read_log(_yesterday()) + "\n" + _read_log(_today())
    log_path = _recent_log_path()
    out = []
    out.append(("포털", *checks.check_http("포털", PORTAL)))
    out.append(("API", *checks.check_http("API", API)))
    # 브리핑보다 앞에 둔다 — 인증이 죽으면 브리핑 실패는 결과일 뿐이라 원인이 먼저 보여야 한다.
    out.append(("Claude인증", *checks.check_claude_auth(*claude_auth.current_state(), time.time())))
    out.append(("브리핑", *checks.check_briefs_published(BRIEF_URL_TEMPLATE, _brief_categories(), _today())))
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


def _send_digest(sections: dict, mode: str) -> int:
    """공용 포맷터에 계약 JSON을 넘긴다. 발송 실패가 점검 자체를 실패로 만들지는 않는다."""
    payload = {
        "kind": "digest",
        "project": "popory",
        "at": datetime.now(KST).isoformat(timespec="seconds"),
        "slot": "am" if mode == "am" else "pm",
        "sections": sections,
    }
    proc = subprocess.run(
        [sys.executable, SEND_PY, f"--env-file={ENV_FILE}"],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        print(f"ops-report 발송 실패(rc={proc.returncode}): {proc.stderr.strip()}", file=sys.stderr)
    return proc.returncode


def run(mode: str) -> int:
    results = gather()
    # 이상이 없어도 항상 보낸다 — 침묵이 "정상"과 "발송기 고장"을 구분하지 못하면 안 된다.
    rc = _send_digest(report.fold_sections(results), mode)
    _save_state(results)
    return 0 if rc == 0 else 1


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
