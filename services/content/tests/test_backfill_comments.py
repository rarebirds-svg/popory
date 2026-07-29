# 서점 댓글 소급 백필 CLI·중복확인 단위 테스트.
import responses
from popory_content.youtube_upload import comment_exists, commentable_video_ids
from popory_content.backfill_comments import _parse_topic


def test_parse_topic_with_author():
    assert _parse_topic("원씽 - 게리 켈러, 제이 파파산") == ("원씽", "게리 켈러, 제이 파파산")


def test_parse_topic_without_author():
    assert _parse_topic("바람의 노래를 들어라") == ("바람의 노래를 들어라", None)


@responses.activate
def test_comment_exists_true_when_store_link_present():
    responses.add(responses.GET, "https://www.googleapis.com/youtube/v3/commentThreads",
                  json={"items": [{"snippet": {"topLevelComment": {"snippet": {"textOriginal": "구매: https://www.aladin.co.kr/search?x"}}}}]}, status=200)
    assert comment_exists("tok", "vid1") is True


@responses.activate
def test_comment_exists_false_when_none():
    responses.add(responses.GET, "https://www.googleapis.com/youtube/v3/commentThreads",
                  json={"items": [{"snippet": {"topLevelComment": {"snippet": {"textOriginal": "좋은 영상!"}}}}]}, status=200)
    assert comment_exists("tok", "vid1") is False


@responses.activate
def test_commentable_excludes_private_and_missing():
    responses.add(responses.GET, "https://www.googleapis.com/youtube/v3/videos",
                  json={"items": [{"id": "pub", "status": {"privacyStatus": "public"}},
                                  {"id": "unl", "status": {"privacyStatus": "unlisted"}},
                                  {"id": "pri", "status": {"privacyStatus": "private"}}]}, status=200)
    # gone 은 응답에 없다 = 삭제된 영상.
    assert commentable_video_ids("tok", ["pub", "unl", "pri", "gone"]) == {"pub", "unl"}


@responses.activate
def test_commentable_passes_through_on_api_error():
    responses.add(responses.GET, "https://www.googleapis.com/youtube/v3/videos", json={}, status=500)
    assert commentable_video_ids("tok", ["v1", "v2"]) == {"v1", "v2"}


def test_run_posts_skips_and_continues(monkeypatch):
    from popory_content import backfill_comments as bc
    calls = []
    class C:
        def get(self, path):
            return {"items": [
                {"video_id": "v1", "topic": "원씽 - 게리 켈러", "access_token": "t"},
                {"video_id": "v2", "topic": "이미달림 - 저자", "access_token": "t"},
                {"video_id": "v3", "topic": "무효링크 - 저자", "access_token": "t"},
            ]}
    monkeypatch.setattr(bc, "_client", lambda: C())
    monkeypatch.setattr(bc, "commentable_video_ids", lambda tok, vids: set(vids))
    monkeypatch.setattr(bc, "comment_exists", lambda tok, vid: vid == "v2")  # v2 이미 존재
    monkeypatch.setattr(bc, "build_purchase_comment_validated", lambda title, author: None if title == "무효링크" else f"{title} 링크")
    monkeypatch.setattr(bc, "post_comment", lambda tok, vid, text: calls.append(vid))
    assert bc.run() == 0
    assert calls == ["v1"]  # v2 skip(중복), v3 skip(무효링크)


def test_run_drops_uncommentable_before_posting(monkeypatch):
    from popory_content import backfill_comments as bc
    calls = []
    class C:
        def get(self, path):
            return {"items": [
                {"video_id": "pub", "topic": "원씽 - 게리 켈러", "access_token": "t"},
                {"video_id": "pri", "topic": "비공개 - 저자", "access_token": "t"},
                {"video_id": "gone", "topic": "삭제됨 - 저자", "access_token": "t"},
            ]}
    monkeypatch.setattr(bc, "_client", lambda: C())
    monkeypatch.setattr(bc, "commentable_video_ids", lambda tok, vids: {"pub"})
    monkeypatch.setattr(bc, "comment_exists", lambda tok, vid: False)
    monkeypatch.setattr(bc, "build_purchase_comment_validated", lambda title, author: f"{title} 링크")
    monkeypatch.setattr(bc, "post_comment", lambda tok, vid, text: calls.append(vid))
    assert bc.run() == 0
    assert calls == ["pub"]  # 비공개·삭제 영상엔 시도 자체를 안 한다
