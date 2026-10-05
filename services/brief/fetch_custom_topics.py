# 활성 커스텀 주제 목록을 portal에서 가져와 run_daily.sh 가 읽는 "id 이름" 줄로 출력하는 CLI
"""
사용법.
    python fetch_custom_topics.py

성공 시 stdout 에 주제마다 한 줄 `{id} {이름(공백→_)}`. 활성 주제가 없으면 빈 출력 + exit 0.
실패 시 비제로 exit code (2 설정 누락, 3/4/5 popory_brief.portal_client 매핑, 1 형식이 틀린 응답).

빈 목록과 조회 실패를 exit code 로 가른다. 종전 셸 파이프라인(JWT 서명 → curl → python3 파싱)은
어느 단계가 실패해도 빈 목록으로 삼켜서, 그날 커스텀 주제가 소리 없이 빠졌다.

환경변수.
    POPORY_BRIEF_KEY_FILE   ES256 키 파일 경로 (services/brief/secrets/brief_signing_key.json)
    POPORY_PORTAL_API_BASE  포털 API base (예: https://api.poporyfamily.com)
"""
import os
import re
import sys
from pathlib import Path
from typing import NoReturn

from popory_brief.jwt_signer import KeyMaterial, sign_for_portal
from popory_brief.log import append_log, safe_error
from popory_brief.portal_client import PortalClient, PortalError

LOGS_DIR = Path(__file__).resolve().parent / "logs"
CLI = "fetch_custom_topics"


def _fail(status: str, error: str, exit_code: int) -> NoReturn:
    print(f"error: {error}", file=sys.stderr)
    append_log(LOGS_DIR, {"cli": CLI, "status": status, "error": error[:200]})
    sys.exit(exit_code)


def main() -> None:
    key_file = os.environ.get("POPORY_BRIEF_KEY_FILE")
    base = os.environ.get("POPORY_PORTAL_API_BASE")
    if not key_file or not base:
        _fail("init_fail", "POPORY_BRIEF_KEY_FILE 또는 POPORY_PORTAL_API_BASE 미설정", 2)
    if not Path(key_file).exists():
        _fail("init_fail", "key file not found", 2)   # 키 파일 경로는 로그에 남기지 않는다 (자격증명 위치).
    material = KeyMaterial.load(Path(key_file))
    client = PortalClient(
        base_url=base,
        token_provider=lambda: sign_for_portal(material, area="custom-service"),
    )
    try:
        body = client.get("/api/brief/custom-topics/active")
    except PortalError as e:
        _fail("fetch_fail", str(e), e.exit_code)
    # 전부 만든 뒤 한 번에 찍는다 — 중간 항목이 깨졌을 때 앞 항목만 나가면 부분 목록이 성공처럼 보인다.
    # 이름의 공백류는 `_` 로 — run_daily.sh 가 `read -r TID TNAME` 으로 읽고 되돌린다. 개행까지
    # 바꾸는 이유. 이름은 포털 사용자 입력이라, 개행이 남으면 둘째 줄이 별도 주제(임의 id)로 읽힌다.
    lines = [f"{t['id']} " + re.sub(r"\s", "_", t["name"]) for t in body["topics"]]
    if lines:
        print("\n".join(lines))


def run() -> None:
    """엔트리포인트. 비처리 예외도 로그로 남긴 뒤 그대로 다시 raise 한다 (traceback·exit code 유지)."""
    try:
        main()
    except Exception as e:   # SystemExit 은 Exception 이 아니라 여기 안 걸린다 (명시적 실패 경로 이중 기록 방지).
        append_log(LOGS_DIR, {"cli": CLI, "status": "unexpected_fail", "error": safe_error(e)})
        raise


if __name__ == "__main__":
    run()
