# 인스타그램 캐러셀 출력 계약 파서 테스트.
import pytest
from popory_content.instagram_image_contract import parse_carousel
from popory_content.contract import ContractError


VALID_OUTPUT = """
여기 캐러셀입니다.
<slides_json>
[{"title": "제목1", "body": "본문1", "image_prompt": "sunny sky"},
 {"title": "제목2", "body": "본문2", "image_prompt": "green field"}]
</slides_json>
<carousel_meta>
{"caption": "캡션 #해시태그", "hashtags": ["해시태그"]}
</carousel_meta>
"""


def test_parse_carousel_success():
    slides, meta = parse_carousel(VALID_OUTPUT)
    assert len(slides) == 2
    assert slides[0]["title"] == "제목1"
    assert slides[1]["image_prompt"] == "green field"
    assert meta["caption"] == "캡션 #해시태그"


def test_parse_carousel_missing_tag_raises():
    with pytest.raises(ContractError):
        parse_carousel("태그가 없는 출력")


def test_parse_carousel_empty_slides_raises():
    bad = '<slides_json>[]</slides_json><carousel_meta>{"caption":"c"}</carousel_meta>'
    with pytest.raises(ContractError):
        parse_carousel(bad)


def test_parse_carousel_missing_title_raises():
    bad = '<slides_json>[{"body":"b","image_prompt":"p"}]</slides_json><carousel_meta>{"caption":"c"}</carousel_meta>'
    with pytest.raises(ContractError):
        parse_carousel(bad)
