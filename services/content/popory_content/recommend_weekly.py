# 주간 시스템 추천 — 기존 컨텐츠를 claude CLI로 검토해 책/주제 10~15건을 추천 등록한다.
import os
import re
import sys
from pathlib import Path

from popory_content.generate import run_claude_cli, model_for, GenerateError
from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.log import append_log

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
AREA = "content-recommend"
RECOMMEND_MIN = 10
RECOMMEND_MAX = 15

SYSTEM_PROMPT = (
    "너는 한국어 독서·자기계발 콘텐츠 기획자다. 이미 다룬 책 목록을 줄 테니, "
    "겹치지 않으면서 같은 독자층(투자·자기계발·인문 교양)이 좋아할 실제 출간된 책을 "
    f"{RECOMMEND_MIN}~{RECOMMEND_MAX}건 제안하라. "
    "채널에서 투자·돈·경제(가치투자·재테크·부·금융·경제사) 주제가 조회수가 가장 높으니, "
    "추천의 약 60%는 투자·돈·경제 분야로, 나머지는 자기계발·인문 교양으로 구성하라. "
    "각 줄은 '제목 - 저자' 형식으로, 실제 저자를 반드시 포함하라. "
    "가공의 책이나 저자 없는 주제는 제안하지 마라. 설명·번호·불릿 없이 목록만. "
    "반드시 <recommendations>와 </recommendations> 태그로 감싸라."
)


def _client() -> PortalClient:
    key_file = os.environ["POPORY_CONTENT_KEY_FILE"]
    base = os.environ["POPORY_PORTAL_API_BASE"]
    material = KeyMaterial.load(Path(key_file))
    return PortalClient(
        base_url=base,
        token_provider=lambda: sign_for_portal(material, area=AREA, ttl_seconds=300),
    )


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


def build_user_msg(known_titles: list[str]) -> str:
    """기존 제목 목록을 받아 '겹치지 마라' 지시를 담은 user 메시지를 만든다."""
    base = "투자·자기계발·인문 교양 분야의 새로운 책 후보를 제안하라. 투자·돈·경제 분야를 약 60% 비중으로 우선하라."
    if not known_titles:
        return base
    listed = ", ".join(known_titles)
    return (
        base
        + " 다음은 이미 다뤘거나 추천 대기 중인 제목이다. 이 목록과 제목·저자·내용이"
        + " 겹치거나 표기만 다른 같은 책은 절대 제안하지 마라:\n"
        + listed
    )


def generate_items(known_titles: list[str]) -> list[dict]:
    """claude CLI로 추천 목록을 생성한다. 프롬프트·파싱·건수 규약을 auto_create 폴백과 공유한다."""
    return run_claude_cli(system_prompt=SYSTEM_PROMPT, user_msg=build_user_msg(known_titles),
                          model=model_for("recommend"),
                          parse=_parse, job_id="recommend")


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

    # 기존 제목을 프롬프트에 주입해 claude가 변형 제안 자체를 피하게 한다(서버 정규화
    # dedup은 마지막 방어선). 조회 실패해도 생성은 진행한다.
    try:
        known = client.get(f"/api/content/recommendations/known-titles?owner_sub={owner_sub}").get("titles", [])
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "recommend_weekly", "status": "known_fetch_fail", "error": str(e)})
        known = []
    try:
        items = generate_items(known)
    except GenerateError as e:
        append_log(LOGS_DIR, {"cli": "recommend_weekly", "status": "claude_fail", "error": str(e)[:300]})
        return 0

    try:
        out = client.post("/api/content/recommendations/service-bulk", json={"owner_sub": owner_sub, "items": items, "category_slug": "book-review"})
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "recommend_weekly", "status": "post_fail", "error": str(e)})
        return 3
    append_log(LOGS_DIR, {"cli": "recommend_weekly", "status": "ok", "added": out.get("added"), "skipped": out.get("skipped")})
    return 0


if __name__ == "__main__":
    sys.exit(run())
