# claude 출력에서 draft_html·meta_json 추출을 검증.
import pytest
from popory_content.contract import parse_generation, ContractError


def test_parses_draft_and_meta():
    text = """헤더 잡담
<draft_html>
<h2>전세사기 예방</h2>
<p>본문입니다.</p>
<figure><img src="https://x/i.jpg" alt="a"><figcaption>출처: 매체</figcaption></figure>
</draft_html>
<meta_json>
{"title": "전세사기 예방", "tags": ["전세"], "images": [{"url": "https://x/i.jpg", "source": "매체"}], "videos": [], "seo": {"score": 82}, "copyright": {"ok": true}}
</meta_json>
끝말"""
    draft, meta = parse_generation(text)
    assert "<h2>" in draft
    assert "figure" in draft
    assert meta["title"] == "전세사기 예방"
    assert meta["images"][0]["source"] == "매체"
    assert meta["seo"]["score"] == 82


def test_missing_tags_raises():
    with pytest.raises(ContractError):
        parse_generation("draft 없음")


def test_bad_json_raises():
    text = "<draft_html>x</draft_html><meta_json>{not json}</meta_json>"
    with pytest.raises(ContractError):
        parse_generation(text)
