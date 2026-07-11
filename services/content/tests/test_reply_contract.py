# 답글 초안 계약(<reply> 또는 <skip>) 파서 단위 테스트.
import pytest

from popory_content.contract import ContractError
from popory_content.reply_contract import parse_reply


def test_reply_tag():
    got = parse_reply("생각을 정리했습니다.\n<reply>읽어주셔서 고맙습니다.</reply>")
    assert got == {"skip": False, "reply": "읽어주셔서 고맙습니다."}


def test_skip_tag():
    got = parse_reply("<skip>광고 스팸입니다.</skip>")
    assert got == {"skip": True, "reason": "광고 스팸입니다."}


def test_no_tag_raises():
    with pytest.raises(ContractError):
        parse_reply("답글을 쓰겠습니다.")


def test_both_tags_raise():
    with pytest.raises(ContractError):
        parse_reply("<reply>고맙습니다.</reply><skip>스팸</skip>")


def test_empty_reply_raises():
    with pytest.raises(ContractError):
        parse_reply("<reply>   </reply>")
