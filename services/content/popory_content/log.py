# JSONL · KST · 메타만 적는 단일 로그 writer (모든 CLI 공용). 실패 레코드는 포털로도 전송한다.
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

KST = timezone(timedelta(hours=9))
SERVICE = "content"
AREA = "content-worker"
SHIP_PATH = "/api/admin/job-logs"
SHIP_TIMEOUT_SECONDS = 3

# 접미사 규칙에 안 걸리지만 실패인 status. auth_failure_exit 은 claude 인증이 끊겨 워커가 죽는 고신호 이벤트다.
# portal_error 는 포털이 죽은 상황이라 전송해도 실패하므로 넣지 않는다.
EXTRA_FAILURE_STATUSES = ("failed", "error", "auth_failure_exit")

# 하위 프로세스 원본 출력을 담는 키. 키 파일 경로·claude CLI 원본 출력이 섞여 들어오므로 포털로는 보내지 않는다.
REDACTED_DETAIL_KEYS = ("stderr", "stdout")


def is_failure(status: str) -> bool:
    """실패 성격의 status 인가. video_unavailable·skipped·done 같은 정상 상태는 제외한다."""
    return status in EXTRA_FAILURE_STATUSES or status.endswith(("_fail", "_failed"))


def _redacted(record: dict) -> dict:
    """포털 전송용 사본. 하위 프로세스 원본 출력 키를 마스킹한다 (원문은 같은 머신의 로컬 파일 로그에만 남는다)."""
    return {k: ("<redacted>" if k in REDACTED_DETAIL_KEYS else v) for k, v in record.items()}


def _portal_target() -> tuple[str, str] | None:
    """전송할 URL과 Bearer 토큰. 키·base 가 없으면 None (개발·테스트 환경에서 잡이 깨지면 안 된다)."""
    key_file = os.environ.get("POPORY_CONTENT_KEY_FILE")
    base = os.environ.get("POPORY_PORTAL_API_BASE")
    if not key_file or not base:
        return None
    from popory_content.jwt_signer import KeyMaterial, sign_for_portal

    material = KeyMaterial.load(Path(key_file))
    token = sign_for_portal(material, area=AREA, ttl_seconds=300)
    return f"{base.rstrip('/')}{SHIP_PATH}", token


def _ship(record: dict, ts: int) -> None:
    """실패 레코드 1건을 포털로 단발 전송. 재시도·백오프 없음 (fire-and-forget 이라 잡을 붙잡으면 안 된다)."""
    target = _portal_target()
    if target is None:
        return
    url, token = target
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "service": SERVICE,
            # worker.py 는 "cli" 대신 "worker" 키로 남긴다. 둘 다 없을 때만 unknown.
            "cli": str(record.get("cli") or record.get("worker") or "unknown"),
            "status": str(record.get("status", "")),
            "job_id": record.get("job_id") or record.get("job"),
            "owner_sub": record.get("owner_sub"),
            "detail": json.dumps(_redacted(record), ensure_ascii=False),
            "ts": ts,
        },
        timeout=SHIP_TIMEOUT_SECONDS,
    )
    if not 200 <= resp.status_code < 300:
        raise RuntimeError(f"job-logs {resp.status_code}: {resp.text[:200]}")


def append_log(logs_dir: Path, record: dict) -> None:
    """KST 일자 파일에 한 줄 JSONL append. record에 ts를 자동 채운다. 실패 레코드는 포털로도 보낸다."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(KST)
    record = {"ts": now.isoformat(timespec="seconds"), **record}
    fname = logs_dir / f"{now.strftime('%Y-%m-%d')}.log"
    with fname.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    status = str(record.get("status", ""))
    if status == "ship_fail" or not is_failure(status):
        return
    try:
        _ship(record, int(now.timestamp()))
    except Exception as e:  # noqa: BLE001 — 전송 실패가 잡을 죽이면 안 된다.
        append_log(logs_dir, {"cli": record.get("cli"), "status": "ship_fail", "error": str(e)[:200]})
