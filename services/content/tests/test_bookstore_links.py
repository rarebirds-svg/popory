# 서점 구매 링크 댓글 빌더 단위 테스트.
from urllib.parse import quote
import pytest
import responses
from popory_content.bookstore_links import build_purchase_comment
from popory_content.youtube_upload import post_comment, UploadError


def test_includes_four_stores_with_author():
    text = build_purchase_comment("원씽", "게리 켈러")
    assert "search.kyobobook.co.kr" in text
    assert "ypbooks.co.kr" in text
    assert "aladin.co.kr" in text
    assert "yes24.com" in text
    q = quote("원씽 게리 켈러")
    assert q in text  # 검색어에 저자 포함·인코딩
    assert "원씽" in text  # 제목 노출


def test_title_only_when_no_author():
    text = build_purchase_comment("원씽", None)
    assert quote("원씽") in text
    assert "게리" not in text
    # 4개 서점 모두 유지
    for d in ("kyobobook", "ypbooks", "aladin", "yes24"):
        assert d in text


def test_empty_author_string_treated_as_none():
    text = build_purchase_comment("원씽", "")
    assert quote("원씽 ") not in text  # 공백 저자 붙지 않음
    assert quote("원씽") in text  # 제목은 여전히 포함
    for d in ("kyobobook", "ypbooks", "aladin", "yes24"):
        assert d in text  # 4개 서점 모두 유지


@responses.activate
def test_post_comment_ok():
    responses.add(responses.POST, "https://www.googleapis.com/youtube/v3/commentThreads", json={"id": "c1"}, status=200)
    post_comment("tok", "vid1", "안녕")  # 예외 없으면 통과


@responses.activate
def test_post_comment_403_raises():
    responses.add(responses.POST, "https://www.googleapis.com/youtube/v3/commentThreads", json={"error": {}}, status=403)
    with pytest.raises(UploadError):
        post_comment("tok", "vid1", "안녕")
