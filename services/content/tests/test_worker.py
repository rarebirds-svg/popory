# 워커가 claim→generate→result 를 올바른 상태로 호출하는지 검증.
import io

import pytest
from PIL import Image

from popory_content import worker


def _png(color=(10, 20, 30)) -> bytes:
    """디코드 가능한 유효 PNG 바이트(이미지 검증 통과용)."""
    b = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(b, format="PNG")
    return b.getvalue()


@pytest.fixture(autouse=True)
def _isolate_logs(tmp_path, monkeypatch):
    """테스트가 실제 services/content/logs/ 를 오염시키지 않도록 LOGS_DIR 격리."""
    monkeypatch.setattr(worker, "LOGS_DIR", tmp_path / "logs")


class FakeClient:
    def __init__(self, claim_response):
        self._claim = claim_response
        self.patched = []
        self.uploaded = []

    def post(self, path, *, json=None):
        assert path == "/api/content/jobs/claim"
        return self._claim

    def patch(self, path, *, json):
        self.patched.append((path, json))
        return {"ok": True}

    def put_binary(self, path, *, data, content_type):
        self.uploaded.append(path)
        return {"ok": True}


def test_no_job_returns_false():
    client = FakeClient({})  # 204 → {}
    assert worker.run_once(client) is False


def test_success_posts_review(monkeypatch):
    monkeypatch.setattr(worker, "generate", lambda **kw: ("# 글", {"seo": {"score": 80}}))
    client = FakeClient({"job": {"id": "j1", "topic": "t"}, "sources": [], "style_samples": []})
    assert worker.run_once(client) is True
    path, body = client.patched[0]
    assert path == "/api/content/jobs/j1/result"
    assert body["status"] == "review"
    assert body["draft"] == "# 글"
    assert body["meta"]["seo"]["score"] == 80


def test_failure_posts_failed(monkeypatch):
    def boom(**kw):
        raise worker.GenerateError("ng")
    monkeypatch.setattr(worker, "generate", boom)
    client = FakeClient({"job": {"id": "j2", "topic": "t"}, "sources": [], "style_samples": []})
    assert worker.run_once(client) is True
    path, body = client.patched[0]
    assert path == "/api/content/jobs/j2/result"
    assert body["status"] == "failed"
    assert "ng" in body["error"]


def test_is_claude_auth_failure():
    assert worker._is_claude_auth_failure("claude CLI exit 1: || stdout: Not logged in · Please run /login") is True
    assert worker._is_claude_auth_failure("Please run /login") is True
    assert worker._is_claude_auth_failure("claude CLI timeout after 1200s") is False
    assert worker._is_claude_auth_failure("ng") is False


def test_auth_failure_reports_failed_then_exits(monkeypatch):
    """claude 인증 실패면 failed 회신 후 sys.exit(1) — launchd KeepAlive 재기동 유도."""
    def boom(**kw):
        raise worker.GenerateError("claude CLI exit 1 (시도 4): || stdout: Not logged in · Please run /login")
    monkeypatch.setattr(worker, "generate", boom)
    client = FakeClient({"job": {"id": "j3", "topic": "t"}, "sources": [], "style_samples": []})
    with pytest.raises(SystemExit) as exc:
        worker.run_once(client)
    assert exc.value.code == 1
    # 종료 전에 failed 회신은 반드시 이뤄져야 한다(잡이 running 으로 묶이지 않게).
    path, body = client.patched[0]
    assert path == "/api/content/jobs/j3/result"
    assert body["status"] == "failed"


class RaisingPatchClient(FakeClient):
    def patch(self, path, *, json):
        raise worker.PortalError("boom", exit_code=5)


def test_patch_failure_does_not_crash(monkeypatch):
    monkeypatch.setattr(worker, "generate", lambda **kw: ("# 글", {}))
    client = RaisingPatchClient({"job": {"id": "j3", "topic": "t"}, "sources": [], "style_samples": []})
    # 회신 PATCH 가 실패해도 run_once 는 예외 없이 True 를 반환해야 한다.
    assert worker.run_once(client) is True


def test_youtube_branch_uploads_video_and_reviews(monkeypatch, tmp_path):
    mp4 = tmp_path / "v.mp4"
    mp4.write_bytes(b"\x00\x01\x02")
    captured = {}

    def fake_make_video(**kw):
        captured.update(kw)
        return (mp4, [{"caption": "c", "narration": "n"}], {"title": "T"}, 0, 1, [])

    monkeypatch.setattr(worker, "make_video", fake_make_video)

    class VidClient(FakeClient):
        def __init__(self, claim):
            super().__init__(claim)
            self.put_bin = []

        def put_binary(self, path, *, data, content_type):
            self.put_bin.append((path, len(data), content_type))
            return {"ok": True}

    client = VidClient({"job": {"id": "yt1", "topic": "t", "platform": "youtube", "params_json": '{"length":"7","voice":"male","image_style":"illust"}'}, "sources": [], "style_samples": []})
    assert worker.run_once(client) is True
    assert client.put_bin[0][0] == "/api/content/jobs/yt1/video"
    assert client.put_bin[0][2] == "video/mp4"
    path, body = client.patched[0]
    assert path == "/api/content/jobs/yt1/result"
    assert body["status"] == "review"
    assert callable(captured.get("image_fetcher"))
    assert captured.get("scene_count") == 12
    assert captured.get("voice") == "ko-KR-Chirp3-HD-Charon"
    assert "illustration" in captured.get("image_style_kw")


def test_safe_image_returns_none_on_error(monkeypatch):
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)

    def fake_post(url, json=None, timeout=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(worker.requests, "post", fake_post)
    assert worker._safe_image(None, "prompt") is None


def test_safe_image_returns_bytes(monkeypatch):
    png = _png()

    class Resp:
        status_code = 200
        content = png

    monkeypatch.setattr(worker.requests, "post", lambda url, json=None, timeout=None: Resp())
    assert worker._safe_image(None, "prompt") == png


def test_safe_image_corrupt_bytes_retries_then_none(monkeypatch):
    # 연결 끊김으로 잘린 바이트(디코드 불가)는 재시도 후 None+로깅(조용한 폴백 방지).
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    calls = {"n": 0}

    class Resp:
        status_code = 200
        content = b"\x89PNG\r\n\x1a\n" + b"truncated-garbage"  # 잘린 PNG

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        return Resp()

    monkeypatch.setattr(worker.requests, "post", fake_post)
    assert worker._safe_image(None, "p", "job1") is None
    assert calls["n"] == worker.IMAGE_MAX_ATTEMPTS  # 깨진 응답도 재시도


def test_safe_image_corrupt_then_valid_recovers(monkeypatch):
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    png = _png((40, 50, 60))
    calls = {"n": 0}

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1

        class Resp:
            status_code = 200
            content = b"\x89PNG-broken" if calls["n"] == 1 else png

        return Resp()

    monkeypatch.setattr(worker.requests, "post", fake_post)
    assert worker._safe_image(None, "p") == png
    assert calls["n"] == 2  # 첫 깨진 응답 → 재시도 → 복구


def test_run_upload_once_uploads_and_reports(monkeypatch):
    captured_up = {}

    def fake_upload(*a, **k):
        captured_up["privacy"] = k.get("privacy")
        return "vid_xyz"

    monkeypatch.setattr(worker, "upload", fake_upload)

    class UpClient:
        def __init__(self):
            self.patched = []

        def post(self, path, *, json=None):
            assert path == "/api/content/youtube/claim-upload"
            return {"job_id": "yt1", "title": "t", "description": "", "tags": [], "access_token": "tok", "privacy": "public"}

        def get_bytes(self, path):
            return b"\x00mp4"

        def patch(self, path, *, json):
            self.patched.append((path, json))
            return {"ok": True}

    client = UpClient()
    assert worker.run_upload_once(client) is True
    path, body = client.patched[0]
    assert path == "/api/content/jobs/yt1/youtube-result"
    assert body == {"status": "done", "video_id": "vid_xyz"}
    assert captured_up["privacy"] == "public"


def test_run_upload_once_no_job():
    class C:
        def post(self, path, *, json=None):
            return {}

    assert worker.run_upload_once(C()) is False


def test_upload_thumbnail_failure_keeps_done(monkeypatch):
    """set_thumbnail 실패해도 youtube-result done이 유지되어야 한다(베스트에포트)."""
    monkeypatch.setattr(worker, "upload", lambda *a, **k: "vid1")
    monkeypatch.setattr(worker, "_upload_captions", lambda *a, **k: None)

    def boom(*a, **k):
        raise RuntimeError("thumb 403")

    monkeypatch.setattr(worker, "set_thumbnail", boom)
    patched = []

    class C:
        def post(self, path, *, json=None):
            return {"job_id": "j1", "access_token": "t", "title": "t"}

        def get_bytes(self, path):
            return b"\xff\xd8\xff"

        def patch(self, path, *, json):
            patched.append((path, json))
            return {}

    assert worker.run_upload_once(C()) is True
    assert any("youtube-result" in p and j.get("status") == "done" for p, j in patched)


def test_safe_image_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    calls = {"n": 0}

    png = _png()

    class Resp:
        status_code = 200
        content = png

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return Resp()

    monkeypatch.setattr(worker.requests, "post", fake_post)
    assert worker._safe_image(None, "p") == png
    assert calls["n"] == 3


def test_safe_image_all_fail_returns_none(monkeypatch):
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)

    def fake_post(url, json=None, timeout=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(worker.requests, "post", fake_post)
    assert worker._safe_image(None, "p") is None


def test_safe_image_http_error_returns_none(monkeypatch):
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)

    class Resp:
        status_code = 500
        text = "err"

    monkeypatch.setattr(worker.requests, "post", lambda url, json=None, timeout=None: Resp())
    assert worker._safe_image(None, "p") is None


class _CFClient:
    """post_for_bytes만 가진 가짜 PortalClient(CF flux 경로 테스트용)."""

    def __init__(self, result):
        self.result = result  # bytes 또는 raise할 Exception
        self.calls = 0

    def post_for_bytes(self, path, *, json):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_safe_image_uses_cloudflare_first(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, "CF_QUOTA_FILE", tmp_path / "cf_quota.json")
    png = _png()
    client = _CFClient(png)
    local = {"n": 0}
    monkeypatch.setattr(worker.requests, "post", lambda *a, **k: local.__setitem__("n", local["n"] + 1))
    assert worker._safe_image(client, "p") == png
    assert client.calls == 1
    assert local["n"] == 0  # CF 성공이면 로컬 호출 안 함


def test_safe_image_falls_back_to_local_on_cf_quota(monkeypatch, tmp_path):
    from popory_content.portal_client import PortalError
    monkeypatch.setattr(worker, "CF_QUOTA_FILE", tmp_path / "cf_quota.json")
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    client = _CFClient(PortalError("ai-image 500: 4006: you have used up your daily free allocation of 10,000 neurons", exit_code=4))
    png = _png((1, 2, 3))

    class Resp:
        status_code = 200
        content = png

    monkeypatch.setattr(worker.requests, "post", lambda url, json=None, timeout=None: Resp())
    assert worker._safe_image(client, "p") == png   # 한도 → 로컬 폴백
    assert worker._cf_exhausted_today() is True       # 오늘 소진 기록됨


def test_safe_image_skips_cf_when_exhausted(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, "CF_QUOTA_FILE", tmp_path / "cf_quota.json")
    worker._mark_cf_exhausted()                       # 오늘 소진 상태
    png = _png()
    client = _CFClient(png)

    class Resp:
        status_code = 200
        content = png

    monkeypatch.setattr(worker.requests, "post", lambda url, json=None, timeout=None: Resp())
    assert worker._safe_image(client, "p") == png
    assert client.calls == 0   # 소진이면 CF 건너뛰고 바로 로컬


class _Mp4:
    def read_bytes(self):
        return b""


def test_youtube_most_images_failed_reports_failed(monkeypatch):
    monkeypatch.setattr(worker, "make_video",
                        lambda **kw: (_Mp4(), [{"caption": "c", "narration": "n"}], {"title": "t"}, 5, 6, []))
    client = FakeClient({"job": {"id": "j1", "topic": "t", "platform": "youtube",
                                 "params_json": '{"length":"5","voice":"male","image_style":"photo"}'},
                         "sources": [], "style_samples": []})
    assert worker.run_once(client) is True
    result = [p for p in client.patched if p[0].endswith("/result")][-1]
    assert result[1]["status"] == "failed"
    assert "배경 이미지 생성 실패" in result[1]["error"]


def test_youtube_half_images_failed_reports_failed(monkeypatch):
    monkeypatch.setattr(worker, "make_video",
                        lambda **kw: (_Mp4(), [{"caption": "c", "narration": "n"}], {"title": "t"}, 3, 6, []))
    client = FakeClient({"job": {"id": "j3", "topic": "t", "platform": "youtube",
                                 "params_json": '{"length":"5","voice":"male","image_style":"photo"}'},
                         "sources": [], "style_samples": []})
    assert worker.run_once(client) is True
    result = [p for p in client.patched if p[0].endswith("/result")][-1]
    assert result[1]["status"] == "failed"


def test_youtube_few_images_failed_reports_review(monkeypatch):
    monkeypatch.setattr(worker, "make_video",
                        lambda **kw: (_Mp4(), [{"caption": "c", "narration": "n"}], {"title": "t"}, 1, 6, []))
    client = FakeClient({"job": {"id": "j2", "topic": "t", "platform": "youtube",
                                 "params_json": '{"length":"5","voice":"male","image_style":"photo"}'},
                         "sources": [], "style_samples": []})
    assert worker.run_once(client) is True
    result = [p for p in client.patched if p[0].endswith("/result")][-1]
    assert result[1]["status"] == "review"
    assert result[1]["meta"]["images_missing"] == 1


def test_run_cycle_attempts_upload_even_when_generating(monkeypatch):
    """생성이 처리돼도 같은 사이클에서 업로드/IG/FB claim 을 시도해야 한다(starvation 제거)."""
    calls = []
    monkeypatch.setattr(worker, "run_once", lambda c: (calls.append("gen") or True))
    monkeypatch.setattr(worker, "run_upload_once", lambda c: (calls.append("up") or False))
    monkeypatch.setattr(worker, "run_instagram_upload_once", lambda c: (calls.append("ig") or False))
    monkeypatch.setattr(worker, "run_facebook_upload_once", lambda c: (calls.append("fb") or False))
    monkeypatch.setattr(worker, "run_custom_brief_once", lambda c: (calls.append("brief") or False))
    assert worker.run_cycle(object()) is True
    assert calls == ["gen", "up", "ig", "fb"]   # 생성 처리돼도 업로드·IG·FB 시도, 저순위 브리핑은 건너뜀


def test_run_cycle_brief_only_when_all_idle(monkeypatch):
    """다른 큐가 모두 비었을 때만 저순위 커스텀 브리핑을 시도한다."""
    calls = []
    monkeypatch.setattr(worker, "run_once", lambda c: (calls.append("gen") or False))
    monkeypatch.setattr(worker, "run_upload_once", lambda c: (calls.append("up") or False))
    monkeypatch.setattr(worker, "run_instagram_upload_once", lambda c: (calls.append("ig") or False))
    monkeypatch.setattr(worker, "run_facebook_upload_once", lambda c: (calls.append("fb") or False))
    monkeypatch.setattr(worker, "run_custom_brief_once", lambda c: (calls.append("brief") or True))
    assert worker.run_cycle(object()) is True
    assert calls == ["gen", "up", "ig", "fb", "brief"]


def test_run_cycle_idle_returns_false(monkeypatch):
    """모든 큐가 비면 False(메인 루프가 sleep)."""
    monkeypatch.setattr(worker, "run_once", lambda c: False)
    monkeypatch.setattr(worker, "run_upload_once", lambda c: False)
    monkeypatch.setattr(worker, "run_instagram_upload_once", lambda c: False)
    monkeypatch.setattr(worker, "run_facebook_upload_once", lambda c: False)
    monkeypatch.setattr(worker, "run_custom_brief_once", lambda c: False)
    assert worker.run_cycle(object()) is False


class SubClient:
    """put_binary/get_bytes를 기록·스텁하는 자막용 페이크."""
    def __init__(self, srt_by_lang=None):
        self.put = []  # (path, data)
        self._srt = srt_by_lang or {}

    def put_binary(self, path, *, data, content_type):
        self.put.append((path, data))
        return {"ok": True}

    def get_bytes(self, path):
        for lang, b in self._srt.items():
            if path.endswith(f"/subtitle/{lang}"):
                return b
        raise RuntimeError("404")


def test_store_subtitles_translates_and_stores_four(monkeypatch):
    monkeypatch.setattr(worker, "translate_lines",
                        lambda lines, **kw: {"en": ["A", "B"], "zh": ["甲", "乙"], "ja": ["あ", "い"]})
    client = SubClient()
    cues = [(0.0, 1.0, "가"), (1.0, 2.0, "나")]
    worker._store_subtitles(client, "j1", cues)
    langs = {p.rsplit("/", 1)[1] for p, _ in client.put}
    assert langs == {"ko", "en", "zh", "ja"}
    en = next(d for p, d in client.put if p.endswith("/subtitle/en"))
    assert b"00:00:00,000 --> 00:00:01,000" in en and b"A" in en


def test_store_subtitles_translation_failure_keeps_ko(monkeypatch):
    monkeypatch.setattr(worker, "translate_lines", lambda lines, **kw: None)
    client = SubClient()
    worker._store_subtitles(client, "j1", [(0.0, 1.0, "가")])
    langs = {p.rsplit("/", 1)[1] for p, _ in client.put}
    assert langs == {"ko"}


def test_upload_captions_uploads_present_langs(monkeypatch):
    sent = []
    monkeypatch.setattr(worker, "upload_caption",
                        lambda tok, vid, lang, name, b: sent.append((lang, vid)))
    client = SubClient(srt_by_lang={"en": b"1\n00:00:00,000 --> 00:00:01,000\nhi\n"})
    worker._upload_captions(client, "tok", "j1", "vid9")
    assert sent == [("en", "vid9")]


def test_store_subtitles_empty_cues_noop():
    client = SubClient()
    worker._store_subtitles(client, "j1", [])
    assert client.put == []


def test_upload_posts_bookstore_comment_for_book_review(monkeypatch):
    monkeypatch.setattr(worker, "upload", lambda *a, **k: "vid1")
    monkeypatch.setattr(worker, "_upload_captions", lambda *a, **k: None)
    posted = {}
    monkeypatch.setattr(worker, "post_comment", lambda tok, vid, text: posted.update(vid=vid, text=text))
    class C:
        def post(self, path, *, json=None):
            return {"job_id": "j1", "access_token": "t", "title": "후킹제목",
                    "book_title": "원씽", "book_author": "게리 켈러", "category_slug": "book-review"}
        def get_bytes(self, path):
            from popory_content.portal_client import PortalError
            if path.endswith("/thumbnail"): raise PortalError("404", 404)
            return b"mp4"
        def patch(self, path, *, json): return {}
    assert worker.run_upload_once(C()) is True
    assert posted.get("vid") == "vid1"
    assert "원씽" in posted["text"] and "kyobobook" in posted["text"]


def test_upload_skips_comment_for_non_book_review(monkeypatch):
    monkeypatch.setattr(worker, "upload", lambda *a, **k: "vid1")
    monkeypatch.setattr(worker, "_upload_captions", lambda *a, **k: None)
    called = {"n": 0}
    monkeypatch.setattr(worker, "post_comment", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    class C:
        def post(self, path, *, json=None):
            return {"job_id": "j1", "access_token": "t", "book_title": "조커", "category_slug": "movie-review"}
        def get_bytes(self, path):
            from popory_content.portal_client import PortalError
            if path.endswith("/thumbnail"): raise PortalError("404", 404)
            return b"mp4"
        def patch(self, path, *, json): return {}
    assert worker.run_upload_once(C()) is True
    assert called["n"] == 0


def test_comment_failure_keeps_done(monkeypatch):
    monkeypatch.setattr(worker, "upload", lambda *a, **k: "vid1")
    monkeypatch.setattr(worker, "_upload_captions", lambda *a, **k: None)
    def boom(*a, **k): raise RuntimeError("comment 403")
    monkeypatch.setattr(worker, "post_comment", boom)
    patched = []
    class C:
        def post(self, path, *, json=None):
            return {"job_id": "j1", "access_token": "t", "book_title": "원씽", "category_slug": "book-review"}
        def get_bytes(self, path):
            from popory_content.portal_client import PortalError
            if path.endswith("/thumbnail"): raise PortalError("404", 404)
            return b"mp4"
        def patch(self, path, *, json): patched.append((path, json)); return {}
    assert worker.run_upload_once(C()) is True
    assert any("youtube-result" in p and j.get("status") == "done" for p, j in patched)
