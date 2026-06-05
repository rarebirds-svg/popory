# claude 출력에서 draft_markdown·meta_json 추출을 검증.
import pytest
from popory_content.contract import parse_generation, ContractError


def test_parses_draft_and_meta():
    text = """헤더 잡담
<draft_markdown>
# 전세사기 예방
본문입니다.
</draft_markdown>
<meta_json>
{"title": "전세사기 예방", "tags": ["전세", "사기예방"], "seo": {"score": 82}, "copyright": {"ok": true}}
</meta_json>
끝말"""
    draft, meta = parse_generation(text)
    assert draft.startswith("# 전세사기 예방")
    assert meta["title"] == "전세사기 예방"
    assert meta["seo"]["score"] == 82
    assert meta["copyright"]["ok"] is True


def test_missing_tags_raises():
    with pytest.raises(ContractError):
        parse_generation("draft 없음")


def test_bad_json_raises():
    text = "<draft_markdown>x</draft_markdown><meta_json>{not json}</meta_json>"
    with pytest.raises(ContractError):
        parse_generation(text)
