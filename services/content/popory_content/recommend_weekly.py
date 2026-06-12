# 주간 시스템 추천 — 기존 컨텐츠를 claude CLI로 검토해 책/주제 10~15건을 추천 등록한다.
import os
import re
import sys
from pathlib import Path

from popory_content.generate import run_claude_cli, GenerateError
from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.log import append_log

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
AREA = "content-recommend"
RECOMMEND_MIN = 10
RECOMMEND_MAX = 15

SYSTEM_PROMPT = (
    "너는 한국어 독서·자기계발 콘텐츠 기획자다. 이미 다룬 책/주제 목록을 줄 테니, "
    "겹치지 않으면서 같은 독자층(투자·자기계발·인문 교양)이 좋아할 책 또는 주제를 "
    f"{RECOMMEND_MIN}~{RECOMMEND_MAX}건 제안하라. 각 줄은 '제목 - 저자' 형식. "
    "저자 미상이면 제목만. 설명·번호·불릿 없이 목록만. "
    "반드시 <recommendations>와 </recommendations> 태그로 감싸라."
)


def _client() -> PortalClient:
    key_file = os.environ["POPORY_CONTENT_KEY_FILE"]
    base = os.environ["POPORY_PORTAL_API_BASE"]
    material = KeyMaterial.load(Path(key_file))
    token = sign_for_portal(material, area=AREA, ttl_seconds=300)
    return PortalClient(base_url=base, token=token)


def _parse(output: str) -> list[dict]:
    m = re.search(r"<recommendations>(.*?)</recommendations>", output, re.DOTALL)
    if not m:
        raise ValueError("no <recommendations> tag")
    items: list[dict] = []
    for line in m.group(1).strip().splitlines():
        t = line.strip().lstrip("-*0123456789. ").strip()
        if not t:
            continue
        idx = t.rfind(" - ")
        if idx == -1:
            items.append({"title": t})
        else:
            title, author = t[:idx].strip(), t[idx + 3:].strip()
            if title:
                items.append({"title": title, "author": author} if author else {"title": title})
    if not items:
        raise ValueError("empty recommendations")
    return items


def run() -> int:
    try:
        client = _client()
    except (KeyError, PortalError) as e:
        append_log(LOGS_DIR, {"cli": "recommend_weekly", "status": "init_fail", "error": str(e)})
        return 2

    # 토픽 보유 계정. 현 단계는 단일 계정 환경변수 고정.
    owner_sub = os.environ.get("POPORY_RECOMMEND_OWNER")
    if not owner_sub:
        append_log(LOGS_DIR, {"cli": "recommend_weekly", "status": "no_owner"})
        return 0

    # 기존 목록은 서버가 중복 skip 하므로 빈 user_msg로도 안전. 품질을 위해
    # owner 컨텍스트를 줄 수 있으나 서비스용 공개 GET이 없으므로 MVP는 일반 지시만.
    user_msg = "이미 다룬 책은 투자·자기계발·인문 교양 분야가 많다. 새로운 후보를 제안하라."
    try:
        items = run_claude_cli(system_prompt=SYSTEM_PROMPT, user_msg=user_msg, parse=_parse, job_id="recommend")
    except GenerateError as e:
        append_log(LOGS_DIR, {"cli": "recommend_weekly", "status": "claude_fail", "error": str(e)[-300:]})
        return 0

    try:
        out = client.post("/api/content/recommendations/service-bulk", json={"owner_sub": owner_sub, "items": items})
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "recommend_weekly", "status": "post_fail", "error": str(e)})
        return 3
    append_log(LOGS_DIR, {"cli": "recommend_weekly", "status": "ok", "added": out.get("added"), "skipped": out.get("skipped")})
    return 0


if __name__ == "__main__":
    sys.exit(run())
