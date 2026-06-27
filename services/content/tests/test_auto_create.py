# auto_create 의 주제 선택·배정 규칙과 run 흐름 단위 테스트.
from popory_content.auto_create import select_assignments


def test_two_recs_youtube_then_shorts():
    recs = [{"id": "a", "title": "오래된것"}, {"id": "b", "title": "새것"}]
    out = select_assignments(recs)
    assert out == [("youtube", recs[0]), ("shorts", recs[1])]


def test_one_rec_same_topic_both():
    recs = [{"id": "a", "title": "하나"}]
    out = select_assignments(recs)
    assert out == [("youtube", recs[0]), ("shorts", recs[0])]


def test_empty_returns_empty():
    assert select_assignments([]) == []
