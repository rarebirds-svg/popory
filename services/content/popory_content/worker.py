# 포털 큐에서 컨텐츠 작업을 claim → claude 생성 → 결과 회신. __main__ 은 무한 poll 루프.
import os
import sys
import time
from pathlib import Path

from popory_content.generate import generate, GenerateError
from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.log import append_log

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
WORKER_AREA = "content-worker"
POLL_INTERVAL_SECONDS = 20
# 서비스 JWT 수명. 60초는 시계 오차·느린 요청에 취약(일시 401 관측) → 여유 상향.
TOKEN_TTL_SECONDS = 300


def run_once(client) -> bool:
    """큐에서 한 건 처리. 처리했으면 True, 큐가 비었으면 False."""
    data = client.post("/api/content/jobs/claim", json=None)
    if not data:
        return False
    job = data["job"]
    sources = data.get("sources", [])
    samples = data.get("style_samples", [])
    job_id = job["id"]
    try:
        draft, meta = generate(topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id)
    except Exception as e:  # noqa: BLE001 — 생성 실패는 failed 로 회신
        _report(client, job_id, {"status": "failed", "error": str(e)[:2000]}, "failed")
        return True
    _report(client, job_id, {"status": "review", "draft": draft, "meta": meta}, "review")
    return True


def _report(client, job_id: str, body: dict, status_label: str) -> None:
    """결과 회신. 회신 자체가 실패해도 poll 루프를 죽이지 않는다(작업은 running 으로 남음)."""
    try:
        client.patch(f"/api/content/jobs/{job_id}/result", json=body)
        append_log(LOGS_DIR, {"worker": "content", "status": status_label, "job": job_id})
    except Exception as e:  # noqa: BLE001 — 회신 실패는 로그만 남긴다
        append_log(LOGS_DIR, {"worker": "content", "status": "report_failed", "job": job_id, "error": str(e)[:300]})


def _build_client() -> PortalClient:
    key_file = os.environ.get("POPORY_CONTENT_KEY_FILE")
    base = os.environ.get("POPORY_PORTAL_API_BASE")
    if not key_file or not Path(key_file).exists():
        print(f"error: POPORY_CONTENT_KEY_FILE 미설정/없음: {key_file}", file=sys.stderr)
        sys.exit(2)
    if not base:
        print("error: POPORY_PORTAL_API_BASE 미설정", file=sys.stderr)
        sys.exit(2)
    material = KeyMaterial.load(Path(key_file))
    return PortalClient(
        base_url=base,
        token_provider=lambda: sign_for_portal(material, area=WORKER_AREA, ttl_seconds=TOKEN_TTL_SECONDS),
    )


def main() -> None:
    client = _build_client()
    append_log(LOGS_DIR, {"worker": "content", "status": "start"})
    while True:
        try:
            processed = run_once(client)
        except PortalError as e:
            append_log(LOGS_DIR, {"worker": "content", "status": "portal_error", "error": str(e)[:300]})
            processed = False
        if not processed:
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
