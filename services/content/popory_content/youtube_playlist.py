# 업로드된 유튜브 영상을 주제(제목·태그 키워드)로 분류해 해당 재생목록에 넣는다(find-or-create).
import requests

from popory_content.youtube_upload import UploadError

PLAYLISTS_URL = "https://www.googleapis.com/youtube/v3/playlists"
PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"

# 기본 재생목록(미분류 catch-all).
DEFAULT_PLAYLIST = "포포리 책방 — 인생의 지혜"

# 우선순위 순 (title+tags에 키워드가 있으면 그 재생목록). 투자·돈이 조회수 1위라 최상단.
PLAYLIST_TAXONOMY: list[tuple[str, tuple[str, ...]]] = [
    ("돈이 되는 책 — 투자·경제", (
        "투자", "주식", "경제", "재테크", "돈", "금융", "부동산", "자산", "펀드",
        "월가", "버핏", "멍거", "밸류", "가치투자", "부의", "부자", "연금", "배당", "시장",
    )),
    ("단단해지는 책 — 자기계발·습관", (
        "자기계발", "습관", "성공", "동기", "목표", "성장", "마인드", "생산성", "루틴",
        "노력", "실행", "몰입", "그릿", "회복탄력",
    )),
    ("깊어지는 책 — 인문·철학", (
        "철학", "인문", "역사", "심리", "니체", "스토아", "삶", "죽음", "의미",
        "사피엔스", "고전", "인간", "사유", "지혜",
    )),
    ("스며드는 책 — 시·에세이", (
        "시", "에세이", "산문", "위로", "문장", "감성", "일상", "마음",
    )),
]


def classify_playlist(title: str, tags: list[str] | None = None) -> str:
    """제목·태그 키워드로 재생목록 이름을 고른다. 매칭 없으면 기본 재생목록."""
    hay = (title or "") + " " + " ".join(tags or [])
    for name, keywords in PLAYLIST_TAXONOMY:
        if any(k in hay for k in keywords):
            return name
    return DEFAULT_PLAYLIST


def find_or_create_playlist(access_token: str, title: str) -> str:
    """내 채널에서 title 과 일치하는 재생목록 id 를 찾고, 없으면 공개로 생성해 id 반환."""
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(
        PLAYLISTS_URL,
        params={"part": "snippet", "mine": "true", "maxResults": 50},
        headers=headers, timeout=30,
    )
    if resp.status_code != 200:
        raise UploadError(f"playlists.list {resp.status_code}: {resp.text[:200]}")
    for item in resp.json().get("items", []):
        if item.get("snippet", {}).get("title") == title:
            return item["id"]
    created = requests.post(
        PLAYLISTS_URL,
        params={"part": "snippet,status"},
        headers={**headers, "Content-Type": "application/json"},
        json={"snippet": {"title": title}, "status": {"privacyStatus": "public"}},
        timeout=30,
    )
    if created.status_code not in (200, 201):
        raise UploadError(f"playlists.insert {created.status_code}: {created.text[:200]}")
    return created.json()["id"]


def add_to_playlist(access_token: str, playlist_id: str, video_id: str) -> None:
    """재생목록에 영상 1개 추가. 실패 시 UploadError."""
    resp = requests.post(
        PLAYLIST_ITEMS_URL,
        params={"part": "snippet"},
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"snippet": {"playlistId": playlist_id,
                          "resourceId": {"kind": "youtube#video", "videoId": video_id}}},
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise UploadError(f"playlistItems.insert {resp.status_code}: {resp.text[:200]}")


def assign_to_playlist(access_token: str, video_id: str, title: str, tags: list[str] | None = None) -> str:
    """영상을 주제 분류해 해당 재생목록(없으면 생성)에 넣고, 재생목록 이름을 반환한다."""
    name = classify_playlist(title, tags)
    playlist_id = find_or_create_playlist(access_token, name)
    add_to_playlist(access_token, playlist_id, video_id)
    return name
