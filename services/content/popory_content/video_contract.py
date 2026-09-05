# claude 출력에서 scenes_json·video_meta 두 태그를 추출·파싱. ContractError 는 contract 모듈 재사용.
import json
import re
from typing import Any

from popory_content.contract import ContractError
from popory_content.video_prompt import append_description_cta, ending_cta_scene

# 카드 텍스트 상한. 카드는 화면 한가운데 큰 글씨라 이보다 길면 렌더에서 줄이 넘친다.
CARD_QUOTE_MAX = 80
CARD_ITEM_MAX = 20
CARD_ITEMS_MAX = 4


def normalize_card(card: Any) -> dict[str, Any] | None:
    """장면의 card 필드를 렌더가 믿고 쓸 수 있는 형태로 정리한다. 모양이 틀리면 None(카드 없음).
    LLM 이 키를 빠뜨리거나 items 를 문자열로 주는 경우가 있어 계약 위반으로 잡을 게 아니라 버린다 —
    카드는 장식이지 대본이 아니다."""
    if not isinstance(card, dict):
        return None
    kind = str(card.get("type") or "").strip().lower()
    if kind == "quote":
        text = str(card.get("text") or "").strip().strip('"“”')
        if not text:
            return None
        source = str(card.get("source") or "").strip()
        return {"type": "quote", "text": text[:CARD_QUOTE_MAX], "source": source}
    if kind == "keypoints":
        items = card.get("items")
        if not isinstance(items, list):
            return None
        cleaned = [str(x).strip()[:CARD_ITEM_MAX] for x in items if str(x).strip()]
        if len(cleaned) < 2:
            return None
        return {"type": "keypoints", "title": str(card.get("title") or "").strip()[:CARD_ITEM_MAX],
                "items": cleaned[:CARD_ITEMS_MAX]}
    return None


def ensure_ending_cta(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """마지막 장면이 구독 CTA 를 담고 있지 않으면 결정적 엔딩 CTA 장면을 덧붙인다(멱등).
    LLM 이 "구독 요청 금지" 시절 습관대로 CTA 를 빼먹어도 영상이 CTA 없이 끝나지 않게 한다."""
    if scenes and "구독" in str(scenes[-1].get("narration", "")):
        return scenes
    return [*scenes, ending_cta_scene()]


def parse_video(text: str, *, ending_cta: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """ending_cta=True(롱폼)면 마지막 장면에 구독 CTA 가 있도록 보장한다. 쇼츠는 False — 60초 안에
    CTA 를 넣지 않는 정책이 그대로다."""
    scenes_m = re.search(r"<scenes_json>\s*(\[.*\])\s*</scenes_json>", text, re.DOTALL)
    meta_m = re.search(r"<video_meta>\s*(\{.*?\})\s*</video_meta>", text, re.DOTALL)
    if not scenes_m or not meta_m:
        raise ContractError("scenes_json/video_meta 태그를 찾지 못함")
    try:
        scenes = json.loads(scenes_m.group(1).strip())
        meta = json.loads(meta_m.group(1).strip())
    except json.JSONDecodeError as e:
        raise ContractError(f"video JSON 파싱 실패: {e}") from e
    if not isinstance(scenes, list) or not scenes:
        raise ContractError("scenes 가 비어있음")
    for s in scenes:
        if not s.get("caption") or not s.get("narration"):
            raise ContractError("scene 에 caption/narration 누락")
        if not s.get("image_prompt"):
            raise ContractError("scene 에 image_prompt 누락")
        card = normalize_card(s.get("card"))
        if card:
            s["card"] = card
        else:
            s.pop("card", None)
    if ending_cta:
        scenes = ensure_ending_cta(scenes)
    meta["description"] = append_description_cta(meta.get("description", ""))  # 구독 CTA·브랜딩 결정적 append
    return scenes, meta
