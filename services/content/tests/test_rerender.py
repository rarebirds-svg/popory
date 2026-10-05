# 재렌더링 — 저장 대본 복원, 남은 배경 재사용, 장면 정보 병합, 워커 라우팅 검증.
import json

import pytest

from popory_content import rerender, worker
from popory_content.video_prompt import ENDING_CTA_CAPTION, ENDING_CTA_IMAGE_PROMPT

DRAFT = "[성과는 밖에 있다]\n첫 문장입니다. 둘째 문장입니다.\n\n[강점에 집중하라]\n강점을 씁니다.\n이어지는 줄입니다."


def test_parse_script_round_trips_worker_draft():
    scenes = [{"caption": "성과는 밖에 있다", "narration": "첫 문장입니다. 둘째 문장입니다."},
              {"caption": "강점에 집중하라", "narration": "강점을 씁니다.\n이어지는 줄입니다."}]
    draft = "\n\n".join(f"[{s['caption']}]\n{s['narration']}" for s in scenes)  # worker 저장 형식 그대로
    assert rerender.parse_script(draft) == scenes
    assert rerender.parse_script(DRAFT) == scenes


def test_parse_script_rejects_empty_or_headerless():
    for bad in (None, "", "제목 없는 글입니다.", "[제목만]\n"):
        with pytest.raises(rerender.RerenderError):
            rerender.parse_script(bad)


def test_load_backgrounds_requires_matching_scene_count(tmp_path):
    assert rerender.load_backgrounds(tmp_path / "없음", 2) == {}
    (tmp_path / "0.png").write_bytes(b"A")
    (tmp_path / "1.png").write_bytes(b"B")
    (tmp_path / "head_0.png").write_bytes(b"H")      # 헤드라인·자막 PNG 는 배경이 아니다
    (tmp_path / "sub_0_0.png").write_bytes(b"S")
    assert rerender.load_backgrounds(tmp_path, 2) == {0: b"A", 1: b"B"}
    assert rerender.load_backgrounds(tmp_path, 3) == {}  # 장면 수가 바뀌었으면 순서를 믿지 않는다


def test_build_scenes_prefers_reused_background_then_saved_prompt():
    script = rerender.parse_script(DRAFT + f"\n\n[{ENDING_CTA_CAPTION}]\n구독 부탁드립니다.")
    meta = {"thumbnail_image_prompt": "thumb tone", "scenes": [
        {"caption": "x", "narration": "y", "image_prompt": "desk at dawn"},
        {"caption": "x", "narration": "y", "image_prompt": "open road", "card": {"type": "quote", "text": "인용"}},
        {"caption": "x", "narration": "y"},
    ]}
    scenes = rerender.build_scenes(script, meta, {0: b"PNG"})
    assert scenes[0]["image_prompt"] == f"{rerender.REUSE_PREFIX}0"
    assert scenes[0]["caption"] == "성과는 밖에 있다"            # 문구는 대본이 기준
    assert scenes[1]["image_prompt"] == "open road"
    assert scenes[1]["card"] == {"type": "quote", "text": "인용"}
    assert scenes[2]["image_prompt"] == ENDING_CTA_IMAGE_PROMPT
    # 다음 재렌더를 위해 남기는 기록엔 재사용 표시 대신 원래 프롬프트가 들어간다
    records = rerender.scene_records(scenes)
    assert records[0]["image_prompt"] == "desk at dawn"
    assert records[1]["card"]["text"] == "인용"


def test_build_scenes_ignores_saved_scenes_when_count_differs():
    script = rerender.parse_script(DRAFT)
    meta = {"scenes": [{"image_prompt": "a", "card": {"type": "quote", "text": "t"}}]}
    scenes = rerender.build_scenes(script, meta, {})
    assert all(s["image_prompt"] == rerender.GENERIC_BG_PROMPT for s in scenes)
    assert not any("card" in s for s in scenes)
    meta["thumbnail_image_prompt"] = "thumb tone"
    assert rerender.build_scenes(script, meta, {})[0]["image_prompt"] == "thumb tone"


def test_image_fetcher_returns_reused_bytes_without_generating():
    calls = []
    fetch = rerender.image_fetcher({1: b"OLD"}, lambda p: calls.append(p) or b"NEW")
    assert fetch(f"{rerender.REUSE_PREFIX}1") == b"OLD"
    assert fetch("a forest") == b"NEW"
    assert calls == ["a forest"]


class _Client:
    def __init__(self, claim):
        self._claim = claim
        self.patched = []
        self.put = []

    def post(self, path, *, json=None):
        return self._claim

    def patch(self, path, *, json):
        self.patched.append((path, json))
        return {"ok": True}

    def put_binary(self, path, *, data, content_type):
        self.put.append(path)
        return {"ok": True}


@pytest.fixture
def rerender_env(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(worker, "TMP", tmp_path)
    monkeypatch.setattr(worker, "make_video", lambda **kw: pytest.fail("재렌더는 대본을 새로 쓰지 않는다"))
    monkeypatch.setattr(worker, "_maybe_put_thumbnail", lambda *a, **k: pytest.fail("썸네일은 그대로 둔다"))
    monkeypatch.setattr(worker, "_store_subtitles", lambda client, job_id, cues: client.put.append("subs"))
    monkeypatch.setattr(worker, "_safe_image", lambda client, p, *a, **k: b"GEN")
    mp4 = tmp_path / "out.mp4"
    mp4.write_bytes(b"MP4")
    captured = {}

    def fake_render(scenes, *, job_id, image_fetcher, voice, portrait, tts_stats):
        captured.update(scenes=scenes, voice=voice, portrait=portrait,
                        images=[image_fetcher(s["image_prompt"]) for s in scenes])
        tts_stats.update(used_voice=voice, sentences=3)
        return mp4, 0, len(scenes), [(0.0, 1.0, "첫 문장입니다.")]

    monkeypatch.setattr(worker, "render_video", fake_render)
    return tmp_path, captured


def _claim(platform="youtube", meta=None, draft=DRAFT):
    job = {"id": "jd", "topic": "프로페셔널의 조건", "platform": platform,
           "params_json": json.dumps({"length": "10", "voice": "male", "rerender": True}),
           "meta_json": json.dumps(meta or {"title": "T", "images_missing": 3, "images_total": 9})}
    return {"job": job, "sources": [], "style_samples": [], "draft": draft}


def test_run_once_rerenders_with_saved_script_and_old_backgrounds(rerender_env):
    tmp, captured = rerender_env
    work = tmp / "video_jd"
    work.mkdir()
    (work / "0.png").write_bytes(b"BG0")
    (work / "1.png").write_bytes(b"BG1")
    client = _Client(_claim())
    assert worker.run_once(client) is True
    assert [s["caption"] for s in captured["scenes"]] == ["성과는 밖에 있다", "강점에 집중하라"]
    assert captured["images"] == [b"BG0", b"BG1"]           # 이미지 생성 없이 남은 배경 재사용
    assert captured["voice"] == "gemini-3.8-flash-tts/Iapetus" and captured["portrait"] is False
    assert client.put == ["/api/content/jobs/jd/video", "subs"]
    path, body = client.patched[0]
    assert body["status"] == "review"
    assert body["draft"] == DRAFT                           # 대본은 그대로 돌려준다
    meta = body["meta"]
    assert meta["title"] == "T"                             # 제목·설명 등 기존 meta 유지
    assert "images_missing" not in meta                     # 이전 렌더의 누락 기록은 지운다
    assert meta["tts"]["voice"] == "gemini-3.8-flash-tts/Iapetus"
    assert meta["rerender"]["reused_backgrounds"] == 2
    assert [s["caption"] for s in meta["scenes"]] == ["성과는 밖에 있다", "강점에 집중하라"]


def test_run_once_rerender_generates_missing_backgrounds(rerender_env):
    _, captured = rerender_env
    client = _Client(_claim("shorts", meta={"scenes": [{"image_prompt": "a"}, {"image_prompt": "b"}]}))
    worker.run_once(client)
    assert captured["images"] == [b"GEN", b"GEN"]
    assert [s["image_prompt"] for s in captured["scenes"]] == ["a", "b"]
    assert captured["portrait"] is True


def test_run_once_rerender_without_script_fails_visibly(rerender_env):
    client = _Client(_claim(draft=None))
    worker.run_once(client)
    _, body = client.patched[0]
    assert body["status"] == "failed" and "대본" in body["error"]
