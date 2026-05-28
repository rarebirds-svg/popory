# JSONL · KST · 메타만 적는 단일 로그 writer (모든 CLI 공용)
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))


def append_log(logs_dir: Path, record: dict) -> None:
    """KST 일자 파일에 한 줄 JSONL append. record에 ts를 자동 채운다."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(KST)
    record = {"ts": now.isoformat(timespec="seconds"), **record}
    fname = logs_dir / f"{now.strftime('%Y-%m-%d')}.log"
    with fname.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
