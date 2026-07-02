# 게시물 출력 계약(post_markdown·post_meta) 파서 검증.
import pytest

from popory_content.youtube_post_contract import parse_youtube_post
from popory_content.contract import ContractError


def test_parse_ok():
    text = (
        'intro <post_markdown>"한 문장이다."\n\n— 『책제목』 저자\n\n'
        '오늘도 한 줄에 기대어.\n\n#오늘의문장 #인생문장 #책추천 #포포리책방</post_markdown> '
        '<post_meta>{"quote_verified": true, "book": "책제목", "author": "저자"}</post_meta> tail'
    )
    post, meta = parse_youtube_post(text)
    assert '"한 문장이다."' in post
    assert "#포포리책방" in post
    assert meta["quote_verified"] is True
    assert meta["book"] == "책제목"


def test_missing_tags_raises():
    with pytest.raises(ContractError):
        parse_youtube_post("태그가 없다.")


def test_empty_body_raises():
    with pytest.raises(ContractError):
        parse_youtube_post('<post_markdown>   </post_markdown><post_meta>{}</post_meta>')


def test_bad_meta_json_raises():
    with pytest.raises(ContractError):
        parse_youtube_post('<post_markdown>x</post_markdown><post_meta>{nope}</post_meta>')
