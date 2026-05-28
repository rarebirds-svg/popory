# brief 영역 구독자 목록을 portal에서 가져와 stdout JSON으로 출력하는 CLI
"""
사용법.
    python fetch_subscribers.py --area brief

성공 시 stdout. {"subscribers":[{"email":"...","display_name":"..."}]}
실패 시 비제로 exit code (2/3/4/5 — popory_brief.portal_client 매핑).

환경변수.
    POPORY_BRIEF_KEY_FILE   ES256 키 파일 경로 (services/brief/secrets/brief_signing_key.json)
    POPORY_PORTAL_API_BASE  포털 API base (예: https://api.poporyfamily.com)
"""
import argparse
import json
import os
import sys
from pathlib import Path

from popory_brief.jwt_signer import KeyMaterial, sign_for_portal
from popory_brief.portal_client import PortalClient, PortalError
from popory_brief.log import append_log

LOGS_DIR = Path(__file__).resolve().parent / "logs"


def _key_path() -> Path:
    p = os.environ.get("POPORY_BRIEF_KEY_FILE")
    if not p:
        print("error: POPORY_BRIEF_KEY_FILE 미설정", file=sys.stderr)
        sys.exit(2)
    if not Path(p).exists():
        print(f"error: key file not found: {p}", file=sys.stderr)
        sys.exit(2)
    return Path(p)


def _portal_base() -> str:
    v = os.environ.get("POPORY_PORTAL_API_BASE")
    if not v:
        print("error: POPORY_PORTAL_API_BASE 미설정", file=sys.stderr)
        sys.exit(2)
    return v


def fetch(*, area: str) -> dict:
    material = KeyMaterial.load(_key_path())
    client = PortalClient(
        base_url=_portal_base(),
        token_provider=lambda: sign_for_portal(material, area=area),
    )
    return client.get(f"/api/areas/{area}/subscribers")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--area", default="brief")
    args = p.parse_args()
    try:
        body = fetch(area=args.area)
    except PortalError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(e.exit_code)
    count = len(body.get("subscribers", []))
    append_log(LOGS_DIR, {"cli": "fetch_subscribers", "status": "ok",
                          "area": args.area, "count": count})
    print(json.dumps(body, ensure_ascii=False))


if __name__ == "__main__":
    main()
