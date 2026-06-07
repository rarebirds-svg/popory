# 워커가 claim→generate→result 를 올바른 상태로 호출하는지 검증.
import pytest

from popory_content import worker


@pytest.fixture(autouse=True)
def _isolate_logs(tmp_path, monkeypatch):
    """테스트가 실제 services/content/logs/ 를 오염시키지 않도록 LOGS_DIR 격리."""
    monkeypatch.setattr(worker, "LOGS_DIR", tmp_path / "logs")


class FakeClient:
    def __init__(self, claim_response):
        self._claim = claim_response
        self.patched = []

    def post(self, path, *, json=None):
        assert path == "/api/content/jobs/claim"
        return self._claim

    def patch(self, path, *, json):
        self.patched.append((path, json))
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
        return (mp4, [{"caption": "c", "narration": "n"}], {"title": "T"})

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
    assert captured.get("voice") == "ko-KR-Neural2-C"
    assert "illustration" in captured.get("image_style_kw")


def test_safe_image_returns_none_on_error():
    class C:
        def post_for_bytes(self, path, *, json):
            raise worker.PortalError("boom", exit_code=4)
    assert worker._safe_image(C(), "prompt") is None


def test_safe_image_returns_bytes():
    class C:
        def post_for_bytes(self, path, *, json):
            return b"\x89PNG"
    assert worker._safe_image(C(), "prompt") == b"\x89PNG"


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
