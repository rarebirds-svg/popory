# 헬스체크 엔트리 — 점검 실행 → 5영역 폴딩 → 공용 포맷터로 발송 → 상태 저장.
import json
import subprocess
import sys
import time
from datetime import date, datetime, timezone, timedelta
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


# 인덱스가 date.weekday()와 일치한다 (월=0 … 일=6). services/brief의 days 규약과 동일.
VALID_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _parse_days(raw: str | None) -> tuple[str, ...] | None:
    """frontmatter days 값("mon,tue,..." 따옴표 포함 가능) → 요일 tuple, 없거나 파싱 불능이면 None(매일).

    잘못된 토큰은 버린다 — 전부 버려지면 매일로 취급한다(fail-open: 점검을 줄이지 않는 방향)."""
    if not raw:
        return None
    tokens = [t.strip().lower() for t in raw.strip().strip('"').split(",") if t.strip()]
    tokens = [t for t in tokens if t in VALID_DAYS]
    return tuple(tokens) or None


def _brief_categories() -> list[tuple[str, str, tuple[str, ...] | None]]:
    """브리핑 카테고리 SKILL.md 프론트매터에서 (slug, 한글 이름, 발행 요일)을 읽는다 — enabled: false는 제외."""
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
            out.append((meta["slug"], meta["name"], _parse_days(meta.get("days"))))
    return out


def _prev_scheduled(days: tuple[str, ...] | None, today: date) -> str | None:
    """오늘 이전의 가장 최근 발행 예정일 — 매일 발행이면 전일, 주 1회면 지난 발행일."""
    for back in range(1, 8):
        d = today - timedelta(days=back)
        if days is None or VALID_DAYS[d.weekday()] in days:
            return d.strftime("%Y-%m-%d")
    return None


def _briefs_due_today(mode: str) -> tuple[list[tuple[str, str, str | None]], int]:
    """오늘 발행 예정 카테고리 목록(오전이면 카테고리별 폴백 일자 포함)과 발행 없는 날이라 건너뛴 수.

    요일제 카테고리(days)는 발행 요일에만 점검한다 — 미발행 요일의 오늘자 미확인 오경보 방지.
    오전 폴백은 전일이 아니라 그 카테고리의 직전 발행 예정일이다(주 1회 카테고리 대응)."""
    today = datetime.strptime(_today(), "%Y-%m-%d").date()
    due: list[tuple[str, str, str | None]] = []
    skipped = 0
    for slug, name, days in _brief_categories():
        if days is not None and VALID_DAYS[today.weekday()] not in days:
            skipped += 1
            continue
        fallback = _prev_scheduled(days, today) if mode == "am" else None
        due.append((slug, name, fallback))
    return due, skipped


def gather(mode: str = "pm") -> list[tuple[str, str, str]]:
    log_text = _read_log(_yesterday()) + "\n" + _read_log(_today())
    log_path = _recent_log_path()
    out = []
    out.append(("포털", *checks.check_http("포털", PORTAL)))
    out.append(("API", *checks.check_http("API", API)))
    # 브리핑보다 앞에 둔다 — 인증이 죽으면 브리핑 실패는 결과일 뿐이라 원인이 먼저 보여야 한다.
    out.append(("Claude인증", *checks.check_claude_auth(*claude_auth.current_state(), time.time())))
    # 오전(09:00) 점검은 브리핑 생성 창(08:00 + 0~120분 지터 + 생성 시간)과 겹친다.
    # 오늘자가 아직 없어도 직전 발행 예정일자가 확인되면 정상으로 본다 — 확정 판정은 21:00 pm이 한다.
    # 요일제 카테고리는 발행 요일에만 점검하고, 오늘 발행 예정이 하나도 없는 날은 ok로 넘어간다.
    brief_due, brief_skipped = _briefs_due_today(mode)
    if brief_due or brief_skipped == 0:
        out.append(("브리핑", *checks.check_briefs_published(
            BRIEF_URL_TEMPLATE, brief_due, _today())))
    else:
        out.append(("브리핑", "ok", f"오늘 발행 예정 카테고리 없음 (요일제 {brief_skipped}개 건너뜀) — {_today()}"))
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
    results = gather(mode)
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
