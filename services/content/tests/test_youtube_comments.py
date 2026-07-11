# 유튜브 댓글 조회·필터(자기 댓글·기존 답글 제외) 단위 테스트.
import pytest
import responses

from popory_content.youtube_comments import list_comment_threads, collect_new_comments
from popory_content.youtube_upload import UploadError

CH = "UC_mine"


def _thread(cid, text, author_ch="UC_viewer", replies_ch=None):
    t = {
        "snippet": {
            "topLevelComment": {
                "id": cid,
                "snippet": {
                    "textOriginal": text,
                    "authorDisplayName": "시청자",
                    "authorChannelId": {"value": author_ch},
                    "publishedAt": "2026-07-10T00:00:00Z",
                },
            }
        }
    }
    if replies_ch:
        t["replies"] = {"comments": [{"snippet": {"authorChannelId": {"value": c}}} for c in replies_ch]}
    return t


def test_collect_excludes_own_comment():
    items = [_thread("c1", "서점 링크", author_ch=CH)]
    assert collect_new_comments(items, CH) == []


def test_collect_excludes_already_replied():
    items = [_thread("c2", "좋아요", replies_ch=[CH])]
    assert collect_new_comments(items, CH) == []


def test_collect_keeps_reply_from_others_only():
    items = [_thread("c3", "질문 있어요", replies_ch=["UC_other"])]
    got = collect_new_comments(items, CH)
    assert len(got) == 1
    assert got[0]["comment_id"] == "c3"
    assert got[0]["text"] == "질문 있어요"
    assert got[0]["author_name"] == "시청자"
    assert got[0]["published_at"] == "2026-07-10T00:00:00Z"


@responses.activate
def test_list_comment_threads_ok():
    responses.add(
        responses.GET,
        "https://www.googleapis.com/youtube/v3/commentThreads",
        json={"items": [_thread("c1", "안녕")]},
        status=200,
    )
    items = list_comment_threads("tok", "vid1")
    assert len(items) == 1


@responses.activate
def test_list_comment_threads_error_raises():
    responses.add(
        responses.GET,
        "https://www.googleapis.com/youtube/v3/commentThreads",
        body="forbidden",
        status=403,
    )
    with pytest.raises(UploadError):
        list_comment_threads("tok", "vid1")
