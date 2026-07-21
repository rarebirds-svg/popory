# 재생목록 분류·find-or-create·추가 로직 단위 테스트(REST 모킹).
import responses

from popory_content import youtube_playlist as yp


def test_classify_investment_first():
    # 투자·돈 키워드는 최우선 버킷
    assert yp.classify_playlist("140억 만든 한 문장 — 피터 린치", ["투자", "가치투자"]) == "돈이 되는 책 — 투자·경제"
    assert yp.classify_playlist("부자의 습관", []) == "돈이 되는 책 — 투자·경제"  # '부자' 매칭


def test_classify_other_buckets_and_default():
    assert yp.classify_playlist("아주 작은 습관의 힘", ["자기계발"]) == "단단해지는 책 — 자기계발·습관"
    assert yp.classify_playlist("니체의 삶", ["철학"]) == "깊어지는 책 — 인문·철학"
    assert yp.classify_playlist("위로가 되는 시", ["에세이"]) == "스며드는 책 — 시·에세이"
    # 키워드 없음 → 기본 재생목록
    assert yp.classify_playlist("무제", []) == yp.DEFAULT_PLAYLIST


@responses.activate
def test_find_or_create_returns_existing():
    responses.add(responses.GET, yp.PLAYLISTS_URL,
                  json={"items": [{"id": "PL_existing", "snippet": {"title": "깊어지는 책 — 인문·철학"}}]}, status=200)
    assert yp.find_or_create_playlist("tok", "깊어지는 책 — 인문·철학") == "PL_existing"


@responses.activate
def test_find_or_create_creates_when_absent():
    responses.add(responses.GET, yp.PLAYLISTS_URL, json={"items": []}, status=200)
    responses.add(responses.POST, yp.PLAYLISTS_URL, json={"id": "PL_new"}, status=200)
    assert yp.find_or_create_playlist("tok", "돈이 되는 책 — 투자·경제") == "PL_new"
    body = responses.calls[1].request.body
    assert "privacyStatus" in (body if isinstance(body, str) else body.decode())


@responses.activate
def test_add_to_playlist_posts_item():
    responses.add(responses.POST, yp.PLAYLIST_ITEMS_URL, json={"id": "item1"}, status=200)
    yp.add_to_playlist("tok", "PL1", "vid123")
    body = responses.calls[0].request.body
    payload = body if isinstance(body, str) else body.decode()
    assert "PL1" in payload and "vid123" in payload and "youtube#video" in payload


@responses.activate
def test_assign_to_playlist_end_to_end():
    responses.add(responses.GET, yp.PLAYLISTS_URL, json={"items": []}, status=200)
    responses.add(responses.POST, yp.PLAYLISTS_URL, json={"id": "PL_new"}, status=200)
    responses.add(responses.POST, yp.PLAYLIST_ITEMS_URL, json={"id": "item1"}, status=200)
    name = yp.assign_to_playlist("tok", "vid1", "버핏의 투자 원칙", ["투자"])
    assert name == "돈이 되는 책 — 투자·경제"
