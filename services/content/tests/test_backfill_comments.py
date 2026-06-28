# 서점 댓글 소급 백필 CLI·중복확인 단위 테스트.
import responses
from popory_content.youtube_upload import comment_exists
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
    monkeypatch.setattr(bc, "comment_exists", lambda tok, vid: vid == "v2")  # v2 이미 존재
    monkeypatch.setattr(bc, "build_purchase_comment_validated", lambda title, author: None if title == "무효링크" else f"{title} 링크")
    monkeypatch.setattr(bc, "post_comment", lambda tok, vid, text: calls.append(vid))
    assert bc.run() == 0
    assert calls == ["v1"]  # v2 skip(중복), v3 skip(무효링크)
