# 그날의 brief 본문을 portal에 publish 하는 CLI (하루 1회 호출)
"""
사용법.
    python publish_to_portal.py --area brief-{slug} \\
        --meta-file /tmp/brief_YYYY-MM-DD.meta.json \\
        --body-file /tmp/brief_YYYY-MM-DD.md

성공 시 stdout. {"status":"ok","id":"<ulid>","title":"...","ts":"..."}
실패 시 비제로 exit code (2/3/4/5).

환경변수.
    POPORY_BRIEF_KEY_FILE   ES256 키 파일
    POPORY_PORTAL_API_BASE  포털 API base
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from popory_brief.categories import load_category
from popory_brief.jwt_signer import KeyMaterial, sign_for_portal
from popory_brief.portal_client import PortalClient, PortalError
from popory_brief.log import append_log, safe_error, KST

LOGS_DIR = Path(__file__).resolve().parent / "logs"


def _key_path() -> Path:
    p = os.environ.get("POPORY_BRIEF_KEY_FILE")
    if not p or not Path(p).exists():
        print(f"error: POPORY_BRIEF_KEY_FILE 미설정 또는 파일 없음: {p}", file=sys.stderr)
        # 키 파일 경로는 로그에 남기지 않는다 (자격증명 위치).
        append_log(LOGS_DIR, {"cli": "publish_to_portal", "status": "init_fail",
                              "error": "POPORY_BRIEF_KEY_FILE 미설정 또는 파일 없음"})
        sys.exit(2)
    return Path(p)


def _portal_base() -> str:
    v = os.environ.get("POPORY_PORTAL_API_BASE")
    if not v:
        print("error: POPORY_PORTAL_API_BASE 미설정", file=sys.stderr)
        append_log(LOGS_DIR, {"cli": "publish_to_portal", "status": "init_fail",
                              "error": "POPORY_PORTAL_API_BASE 미설정"})
        sys.exit(2)
    return v


def publish(*, area: str, meta_file: Path, body_file: Path, replace_same_day: bool = False) -> dict:
    meta = json.loads(Path(meta_file).read_text(encoding="utf-8"))
    body = Path(body_file).read_text(encoding="utf-8")
    payload = {
        "area": area,
        "title": meta["title"],
        "body": body,
        "published_at": int(meta["published_at"]),
    }
    if meta.get("summary"):
        payload["summary"] = meta["summary"]
    if meta.get("tags"):
        payload["tags"] = list(meta["tags"])
    if replace_same_day:
        payload["replace_same_day"] = True

    material = KeyMaterial.load(_key_path())
    client = PortalClient(
        base_url=_portal_base(),
        token_provider=lambda: sign_for_portal(material, area=area),
    )
    return client.post("/api/published_items", json=payload)


def check_area(area: str) -> str | None:
    """발행 영역이 포털 피드가 읽는 형식인지. 문제가 있으면 사유, 없으면 None.

    포털은 brief-{카테고리 slug}·custom-{주제 id} 영역만 피드·카테고리로 보여 준다. 그 밖의 영역도
    서버는 받아 주므로, 여기서 막지 않으면 발행 성공(ok)으로 끝나고도 아무도 못 보는 글이 된다."""
    if area == "brief" or (area.startswith("custom-") and len(area) > len("custom-")):
        return None   # brief: 단일 브리핑 시절 영역(하위호환)
    if area.startswith("brief-"):
        slug = area[len("brief-"):]
        try:
            load_category(slug)
        except KeyError:
            return f"알 수 없는 카테고리 영역 {area!r} — categories/{slug}/SKILL.md 가 없다"
        return None
    return f"발행 영역 형식 오류 {area!r} — brief-{{slug}} 또는 custom-{{id}} 여야 한다"


def main() -> None:
    p = argparse.ArgumentParser()
    # 기본값을 두지 않고 형식도 확인한다(check_area). 2026-09-25 수동 발행에서 영역을
    # "realestate-pick5-blog"(brief- 접두사 누락)로 넘겨 글이 아무 피드에도 안 잡히는 영역에 들어갔고,
    # 제 영역(brief-realestate-pick5-blog)에는 발행이 없었다.
    p.add_argument("--area", required=True,
                   help="발행 영역 — 카테고리는 brief-{slug}, 커스텀 주제는 custom-{id}")
    p.add_argument("--meta-file", required=True)
    p.add_argument("--body-file", required=True)
    p.add_argument("--replace-same-day", action="store_true",
                   help="같은 area·같은 KST 날짜의 기존 발행물을 지우고 새로 넣는다")
    args = p.parse_args()
    problem = check_area(args.area)
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        append_log(LOGS_DIR, {"cli": "publish_to_portal", "status": "init_fail",
                              "area": args.area, "error": problem[:200]})
        sys.exit(2)
    try:
        body = publish(area=args.area,
                       meta_file=Path(args.meta_file),
                       body_file=Path(args.body_file),
                       replace_same_day=args.replace_same_day)
    except PortalError as e:
        print(f"error: {e}", file=sys.stderr)
        append_log(LOGS_DIR, {"cli": "publish_to_portal", "status": "publish_fail",
                              "area": args.area, "error": str(e)[:200]})
        sys.exit(e.exit_code)
    ts = datetime.now(KST).isoformat(timespec="seconds")
    append_log(LOGS_DIR, {
        "cli": "publish_to_portal", "status": "ok",
        "area": args.area, "id": body.get("id"),
    })
    print(json.dumps({"status": "ok", "id": body.get("id"),
                      "area": args.area, "ts": ts}, ensure_ascii=False))


def run() -> None:
    """엔트리포인트. 비처리 예외도 로그로 남긴 뒤 그대로 다시 raise 한다 (traceback·exit code 유지)."""
    try:
        main()
    except Exception as e:   # SystemExit 은 Exception 이 아니라 여기 안 걸린다 (명시적 실패 경로 이중 기록 방지).
        append_log(LOGS_DIR, {"cli": "publish_to_portal", "status": "unexpected_fail",
                              "error": safe_error(e)})
        raise


if __name__ == "__main__":
    run()
