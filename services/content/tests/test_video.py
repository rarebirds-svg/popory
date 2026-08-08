# 영상 합성 테스트. _render_card 는 Pillow만 필요(항상 실행), render_video 스모크는 ffmpeg/say 필요(조건부).
import io
import shutil
from pathlib import Path

import pytest
from PIL import Image as _Image

from popory_content.video import (
    render_video,
    _render_card,
    _split_sentences,
    _spans_from_durations,
    _render_subtitle_png,
    _deepen_voice,
    FONT_PATH,
)
from popory_content import video as _video

_HAS_TOOLS = bool(shutil.which("ffmpeg") and shutil.which("say") and Path(FONT_PATH).exists())


def test_render_card_with_and_without_bg(tmp_path):
    buf = io.BytesIO()
    _Image.new("RGB", (320, 180), (200, 100, 50)).save(buf, format="PNG")
    bg = buf.getvalue()
    p1 = tmp_path / "with_bg.png"
    p2 = tmp_path / "no_bg.png"
    _render_card("챕터 제목", "지금 읽는 문장입니다.", p1, bg_image_bytes=bg)
    _render_card("챕터 제목", "지금 읽는 문장입니다.", p2, bg_image_bytes=None)
    assert p1.exists() and p1.stat().st_size > 1000
    assert p2.exists() and p2.stat().st_size > 1000


def test_render_card_corrupt_bytes_falls_back(tmp_path):
    # 깨진 이미지 바이트가 와도 크래시하지 않고 단색 카드로 폴백한다.
    out = tmp_path / "corrupt.png"
    _render_card("제목", "문장", out, bg_image_bytes=b"\x89PNG-not-a-real-image")
    assert out.exists() and out.stat().st_size > 1000


def test_split_sentences():
    assert _split_sentences("첫 문장이다. 둘째 문장! 셋째?") == ["첫 문장이다.", "둘째 문장!", "셋째?"]
    assert _split_sentences("  ") == []
    assert _split_sentences("문장 하나만") == ["문장 하나만"]


def test_split_sentences_keeps_decimals_intact():
    # 소수점에서 끊기면 tts 의 소수→한글 변환이 온전한 토큰을 못 받아 점을 흘린다(6.25→"육 이십오").
    assert _split_sentences("보상은 6.25개에서 3.125개로 줄었다. 다음.") == [
        "보상은 6.25개에서 3.125개로 줄었다.",
        "다음.",
    ]
    # 공백 없는 문장 경계는 계속 끊는다(뒤가 숫자가 아니면 문장 끝).
    assert _split_sentences("첫째다.둘째다.") == ["첫째다.", "둘째다."]


def test_spans_from_durations_track_real_audio_lengths():
    # 자막 타이밍은 문장별 실측 길이를 그대로 따른다(글자수 추정 아님). 문장 사이 gap만큼 띄움.
    spans = _spans_from_durations([2.0, 3.0, 1.0], 0.5)
    assert len(spans) == 3
    assert spans[0][0] == 0.0
    # 비마지막 문장은 다음 문장 시작까지(갭 포함) 자막 유지 → 깜빡임 없음
    assert abs(spans[0][1] - 2.5) < 1e-6     # 0+2.0+0.5
    assert abs(spans[1][0] - 2.5) < 1e-6
    assert abs(spans[1][1] - 6.0) < 1e-6     # 2.5+3.0+0.5
    assert abs(spans[2][0] - 6.0) < 1e-6
    assert abs(spans[2][1] - 7.0) < 1e-6     # 마지막은 발화 끝(뒤 갭 없음)
    # 각 문장 자막의 시작 간격은 실측 길이+gap을 정확히 반영(누적 드리프트 없음)
    assert abs((spans[1][0] - spans[0][0]) - (2.0 + 0.5)) < 1e-6
    assert abs((spans[2][0] - spans[1][0]) - (3.0 + 0.5)) < 1e-6


def test_spans_from_durations_single():
    assert _spans_from_durations([5.0], 0.5) == [(0.0, 5.0)]


def test_master_audio_copies_video_without_scale(tmp_path, monkeypatch):
    # scale 없으면 비디오는 copy(기존 동작 유지)
    cmds = []
    monkeypatch.setattr(_video, "_run", lambda cmd: cmds.append(cmd))
    _video._master_audio(tmp_path / "in.mp4", tmp_path / "out.mp4", None)
    cmd = cmds[0]
    assert "copy" in cmd and "libx264" not in cmd
    assert not any("scale=" in str(a) for a in cmd)


def test_master_audio_portrait_scales_to_half(tmp_path, monkeypatch):
    # portrait 출력은 540×960으로 다운스케일 재인코딩(쇼츠 절반 크기)
    cmds = []
    monkeypatch.setattr(_video, "_run", lambda cmd: cmds.append(cmd))
    _video._master_audio(tmp_path / "in.mp4", tmp_path / "out.mp4", None,
                         scale=(_video.PORTRAIT_OUT_W, _video.PORTRAIT_OUT_H))
    graph = cmds[0][cmds[0].index("-filter_complex") + 1]
    assert "scale=540:960" in graph
    assert "libx264" in cmds[0] and "copy" not in cmds[0]


def test_deepen_voice_disabled_returns_original(tmp_path, monkeypatch):
    monkeypatch.setattr(_video, "VOICE_DEEPEN_SEMITONES", 0.0)
    p = tmp_path / "0.mp3"
    p.write_bytes(b"x")
    assert _deepen_voice(p) == p          # 0이면 변형 안 함


def test_deepen_voice_builds_pitchdown_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(_video, "VOICE_DEEPEN_SEMITONES", 2.0)
    cmds = []
    monkeypatch.setattr(_video, "_run", lambda cmd: cmds.append(cmd))
    src = tmp_path / "0.mp3"
    src.write_bytes(b"x")
    out = _deepen_voice(src)
    assert out.name == "0_deep.mp3"        # 새 파일로 출력
    af = cmds[0][cmds[0].index("-af") + 1]
    assert "asetrate" in af and "atempo" in af   # 피치 다운
    assert "treble" in af                         # 명료도(프레즌스) 복원
    assert "equalizer=f=350" in af                # 머드 컷


def test_render_subtitle_png_is_transparent(tmp_path):
    out = tmp_path / "sub.png"
    _render_subtitle_png("자막 문장입니다.", out)
    img = _Image.open(out)
    assert img.mode == "RGBA"           # 투명 오버레이용
    assert img.size == (1920, 1080)
    # 완전 투명이 아닌 픽셀(글자)이 존재
    assert img.getextrema()[3][1] > 0


def test_render_card_portrait_creates_correct_size(tmp_path):
    """portrait=True 시 1080×1920 PNG가 생성된다."""
    from popory_content.video import _render_card
    from PIL import Image
    out = tmp_path / "card.png"
    _render_card("제목", "자막 테스트 문장입니다.", out, portrait=True)
    img = Image.open(out)
    assert img.size == (1080, 1920)


def test_render_card_landscape_creates_correct_size(tmp_path):
    """기본(portrait=False)은 1920×1080을 유지한다."""
    from popory_content.video import _render_card
    from PIL import Image
    out = tmp_path / "card.png"
    _render_card("제목", "자막", out)
    img = Image.open(out)
    assert img.size == (1920, 1080)


def test_zoompan_filter_landscape_and_portrait():
    from popory_content.video import _zoompan_filter
    fl = _zoompan_filter(3.0, portrait=False)
    # 2배 수퍼샘플 캔버스에서 zoompan 후 최종 1920x1080으로 다운스케일
    assert "zoompan" in fl and "fps=30" in fl
    assert "s=3840x2160" in fl and "scale=1920:1080" in fl
    fp = _zoompan_filter(3.0, portrait=True)
    assert "s=2160x3840" in fp and "scale=1080:1920" in fp


def test_zoom_amplitude_holds_target_rate_on_long_scenes():
    from popory_content.video import _zoom_amplitude, ZOOM_RATE_PER_SEC
    # 왕복이라 장면 절반 만에 피크에 닿는다 → 초당 변화율 = amp / (dur/2).
    for dur in (20.0, 30.0, 44.6):
        rate = _zoom_amplitude(dur) / (dur / 2)
        assert abs(rate - ZOOM_RATE_PER_SEC) < 1e-9
    # 문제 영상 S10(44.6초)은 피크 1.156 — 검토 때 고른 B안(피크 1.16)과 같다.
    assert round(1 + _zoom_amplitude(44.6), 3) == 1.156


def test_zoom_amplitude_clamped_at_both_ends():
    from popory_content.video import _zoom_amplitude, ZOOM_SPAN_MIN, ZOOM_SPAN_MAX
    # 쇼츠처럼 짧은 장면은 목표 속도를 그대로 쓰면 폭이 거의 0이 된다 → 하한으로 받친다.
    assert _zoom_amplitude(7.0) == ZOOM_SPAN_MIN
    # 아주 긴 장면은 폭이 무한정 커져 1024px 원본이 뭉개진다 → 상한으로 막는다.
    assert _zoom_amplitude(60.0) == ZOOM_SPAN_MAX
    # 상한에 걸려도 기존(0.12를 장면 전체에 분산)보다는 여전히 빠르다.
    assert ZOOM_SPAN_MAX / 30.0 > 0.12 / 60.0


def test_zoompan_is_pingpong_returning_to_start():
    from popory_content.video import _zoompan_filter, _MOTIONS, _zoom_amplitude
    amp = _zoom_amplitude(3.0)
    f_in = _zoompan_filter(3.0, variant=0)     # 넓게 시작 → 확대 → 복귀
    f_out = _zoompan_filter(3.0, variant=1)    # 확대로 시작 → 축소 → 복귀
    assert f"1.0+{amp:.4f}*(1-abs(1-2*on/90))" in f_in
    assert f"{1 + amp:.4f}-{amp:.4f}*(1-abs(1-2*on/90))" in f_out


def test_zoompan_variant_alternates_direction_and_anchor():
    from popory_content.video import _zoompan_filter, _MOTIONS
    # 인접 variant는 줌 방향이 서로 달라, 장면이 이어져도 같은 무빙이 반복되지 않는다.
    dirs = [m[0] for m in _MOTIONS]
    assert all(dirs[i] != dirs[i + 1] for i in range(len(dirs) - 1))
    assert dirs[-1] != dirs[0]  # 순환해도 이어붙지 않는다
    # 가로 기준점만 옮기고 세로는 항상 중앙 — 배경에 구워진 하단 스크림을 밀지 않기 위함.
    assert "*0.35'" in _zoompan_filter(3.0, variant=1)
    assert "*0.50'" in _zoompan_filter(3.0, variant=0)
    assert all("ih/zoom)*0.50'" in _zoompan_filter(3.0, variant=v) for v in range(len(_MOTIONS)))


def test_zoompan_variant_wraps_and_keeps_canvas_size():
    from popory_content.video import _zoompan_filter, _MOTIONS
    # variant는 장면 인덱스를 그대로 받으므로 길이를 넘어가면 순환한다.
    assert _zoompan_filter(3.0, variant=len(_MOTIONS)) == _zoompan_filter(3.0, variant=0)
    # 어떤 variant도 수퍼샘플 캔버스 크기를 바꾸지 않는다(렌더 비용이 장면마다 동일).
    for v in range(len(_MOTIONS)):
        assert "s=3840x2160" in _zoompan_filter(3.0, variant=v)


def test_xfade_graph_offsets_and_labels():
    from popory_content.video import _xfade_graph
    graph, vlabel, alabel = _xfade_graph([3.0, 4.0, 5.0], td=0.4)
    # 첫 전환 offset = 3.0-0.4 = 2.6, 둘째 = (3.0-0.4)+(4.0-0.4) = 2.6+3.6 = 6.2
    assert "offset=2.600" in graph
    assert "offset=6.200" in graph
    assert "acrossfade=d=0.4" in graph
    assert vlabel == "v2" and alabel == "a2"


def test_xfade_graph_single_clip_is_empty():
    from popory_content.video import _xfade_graph
    graph, vlabel, alabel = _xfade_graph([3.0], td=0.4)
    assert graph == "" and vlabel == "0:v" and alabel == "0:a"


def test_pick_bgm_none_when_empty(tmp_path):
    from popory_content.video import _pick_bgm
    assert _pick_bgm(tmp_path, "job1") is None


def test_pick_bgm_deterministic(tmp_path):
    from popory_content.video import _pick_bgm
    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "b.mp3").write_bytes(b"y")
    first = _pick_bgm(tmp_path, "job1")
    assert first is not None
    assert first == _pick_bgm(tmp_path, "job1")  # 같은 job_id → 같은 선택


@pytest.mark.skipif(not _HAS_TOOLS, reason="ffmpeg/say/폰트 없음 (CI 등)")
def test_render_two_scenes_makes_mp4(tmp_path, monkeypatch):
    import popory_content.video as v
    monkeypatch.setattr(v, "TMP", tmp_path)
    scenes = [
        {"caption": "테스트 장면 하나", "narration": "이것은 첫 문장입니다. 두 번째 문장이에요."},
        {"caption": "테스트 장면 둘", "narration": "이것은 다른 장면입니다. 마지막 문장입니다."},
    ]
    out, _, _, _ = render_video(scenes, job_id="smoketest")
    assert out.exists() and out.stat().st_size > 10000
    # 장면당 클립 1개(문장 분할 안 함): scene_*.mp4 가 정확히 2개
    work = tmp_path / "video_smoketest"
    clips = sorted(work.glob("scene_*.mp4"))
    assert len(clips) == 2


def test_wrap_chunks_keeps_every_chunk_within_one_line():
    from popory_content.video import _wrap_chunks, SUB_WRAP_LANDSCAPE
    s = "복리는 수익률이 아니라 시간에 붙습니다 그래서 버티는 사람에게만 열리는 문이 됩니다 대부분은 그걸 못 견딥니다"
    chunks = _wrap_chunks(s, SUB_WRAP_LANDSCAPE)
    assert len(chunks) > 1
    assert all(len(c) <= SUB_WRAP_LANDSCAPE for c in chunks)
    # 어절을 쪼개지 않고 공백 경계에서만 끊는다 → 이어붙이면 원문 그대로.
    assert " ".join(chunks) == s
    # 짧은 문장은 그대로 한 조각.
    assert _wrap_chunks("짧은 문장.", SUB_WRAP_LANDSCAPE) == ["짧은 문장."]


def test_chunk_spans_split_speech_and_hold_through_gap():
    from popory_content.video import _chunk_spans
    # 발화 6초 + 뒤 무음까지 포함한 문장 구간 [10.0, 17.0].
    spans = _chunk_spans(["가나다라", "마바사아"], start=10.0, speech_dur=6.0, end=17.0)
    assert len(spans) == 2
    assert spans[0][0] == 10.0
    # 정규화 길이가 같으니 발화 6초를 절반씩 → 첫 조각은 13.0에서 끝난다.
    assert abs(spans[0][1] - 13.0) < 1e-6
    assert abs(spans[1][0] - 13.0) < 1e-6
    # 마지막 조각은 문장 뒤 무음까지 유지해 깜빡임을 없앤다.
    assert spans[1][1] == 17.0


def test_chunk_spans_weight_by_tts_normalized_length():
    from popory_content.video import _chunk_spans
    # "1,700"은 5글자지만 TTS는 "천칠백"으로 읽는다. 원문 글자수로 나누면 이 조각이 과대평가된다.
    spans = _chunk_spans(["1,700", "천칠백"], start=0.0, speech_dur=10.0, end=10.0)
    assert abs(spans[0][1] - 5.0) < 0.5   # 두 조각의 실제 발화량이 같으므로 거의 반반


def test_render_video_cues_stay_sentence_level_while_overlays_split(monkeypatch, tmp_path):
    # 번인 자막은 한 줄씩 쪼개지만, cue(=SRT·번역 단위)는 문장 그대로 유지돼야 한다.
    from popory_content import video
    _render_stub(monkeypatch, tmp_path, video)
    monkeypatch.setattr(video, "_master_audio", lambda src, out, bgm, scale=None: None)
    monkeypatch.setattr(video, "_pick_bgm", lambda d, j: None)
    rendered = []
    monkeypatch.setattr(video, "_render_subtitle_png",
                        lambda text, png, portrait=False: rendered.append(text))
    long_sentence = ("복리는 수익률이 아니라 시간에 붙습니다 그래서 버티는 사람에게만 "
                     "열리는 문이 되고 대부분은 그걸 끝내 못 견딥니다.")
    scenes = [{"caption": "a", "narration": long_sentence},
              {"caption": "b", "narration": long_sentence}]
    _, _, _, cues = video.render_video(scenes, job_id="cuetest")
    assert len(cues) == 2                      # 장면당 문장 1개 → cue 2개
    assert cues[0][2] == long_sentence         # 조각이 아니라 문장 전체
    assert len(rendered) > 1                   # 화면에는 여러 조각으로 나뉘어 표시
    assert all(len(t) <= video.SUB_WRAP_LANDSCAPE for t in rendered)


def test_render_video_counts_missing_images(monkeypatch, tmp_path):
    from popory_content import video
    monkeypatch.setattr(video, "FONT_PATH", str(tmp_path))  # 폰트 존재 체크 통과
    monkeypatch.setattr(video, "synthesize", lambda text, voice=None: b"AUDIO")
    monkeypatch.setattr(video, "_run", lambda cmd: None)
    monkeypatch.setattr(video, "_duration", lambda path: 1.0)
    monkeypatch.setattr(video, "_render_card", lambda *a, **k: None)
    monkeypatch.setattr(video, "_render_headline_png", lambda *a, **k: None)
    monkeypatch.setattr(video, "_render_subtitle_png", lambda *a, **k: None)
    monkeypatch.setattr(video, "_master_audio", lambda src, out, bgm, scale=None: None)
    monkeypatch.setattr(video, "_pick_bgm", lambda d, j: None)
    monkeypatch.setattr(video, "_xfade_graph", lambda durs, td=0.4: ("", "v", "a"))
    scenes = [
        {"caption": "a", "narration": "n1", "image_prompt": "ok one"},
        {"caption": "b", "narration": "n2", "image_prompt": "fail two"},
        {"caption": "c", "narration": "n3", "image_prompt": "fail three"},
        {"caption": "d", "narration": "n4"},  # image_prompt 없음 → total 미포함
    ]
    fetcher = lambda p: b"IMG" if "ok" in p else None
    out, missing, total, _ = video.render_video(scenes, job_id="vbtest", image_fetcher=fetcher)
    assert total == 3   # image_prompt 있는 장면 수
    assert missing == 2 # 'fail' 2개


def test_render_video_encodes_with_bitrate_cap(monkeypatch, tmp_path):
    # scene/join 인코딩에 CRF·maxrate 상한이 실려 파일 용량이 Cloudflare 100MB 한도 아래로 유지된다
    from popory_content import video
    cmds = []
    monkeypatch.setattr(video, "FONT_PATH", str(tmp_path))
    monkeypatch.setattr(video, "synthesize", lambda text, voice=None: b"AUDIO")
    monkeypatch.setattr(video, "_run", lambda cmd: cmds.append(cmd))
    monkeypatch.setattr(video, "_duration", lambda path: 1.0)
    monkeypatch.setattr(video, "_render_card", lambda *a, **k: None)
    monkeypatch.setattr(video, "_render_headline_png", lambda *a, **k: None)
    monkeypatch.setattr(video, "_render_subtitle_png", lambda *a, **k: None)
    monkeypatch.setattr(video, "_master_audio", lambda src, out, bgm, scale=None: None)
    monkeypatch.setattr(video, "_pick_bgm", lambda d, j: None)
    scenes = [{"caption": "a", "narration": "n1", "image_prompt": "ok"},
              {"caption": "b", "narration": "n2", "image_prompt": "ok"}]
    video.render_video(scenes, job_id="captest", image_fetcher=lambda p: b"IMG")
    enc = [c for c in cmds if "libx264" in c]
    assert enc, "libx264 인코딩 명령이 있어야 한다"
    assert all("-crf" in c and "-maxrate" in c for c in enc)   # 모든 인코딩에 상한


def _render_stub(monkeypatch, tmp_path, video):
    """render_video 의 무거운 ffmpeg/TTS 호출을 전부 우회하는 공통 monkeypatch."""
    monkeypatch.setattr(video, "FONT_PATH", str(tmp_path))
    monkeypatch.setattr(video, "synthesize", lambda text, voice=None: b"AUDIO")
    monkeypatch.setattr(video, "_run", lambda cmd: None)
    monkeypatch.setattr(video, "_duration", lambda path: 1.0)
    monkeypatch.setattr(video, "_render_card", lambda *a, **k: None)
    monkeypatch.setattr(video, "_render_headline_png", lambda *a, **k: None)
    monkeypatch.setattr(video, "_render_subtitle_png", lambda *a, **k: None)
    monkeypatch.setattr(video, "_xfade_graph", lambda durs, td=0.4: ("", "v", "a"))


def test_render_video_skips_bgm_when_disabled(monkeypatch, tmp_path):
    from popory_content import video
    _render_stub(monkeypatch, tmp_path, video)
    monkeypatch.setattr(video, "BGM_ENABLED", False)
    monkeypatch.setattr(video, "_pick_bgm", lambda d, j: "PICKED")  # 꺼지면 호출 결과가 쓰이면 안 됨
    captured = {}
    monkeypatch.setattr(video, "_master_audio", lambda src, out, bgm, scale=None: captured.update(bgm=bgm))
    video.render_video([{"caption": "a", "narration": "n1"}, {"caption": "b", "narration": "n2"}], job_id="nobgm")
    assert captured["bgm"] is None


def test_render_video_uses_bgm_when_enabled(monkeypatch, tmp_path):
    from popory_content import video
    _render_stub(monkeypatch, tmp_path, video)
    monkeypatch.setattr(video, "BGM_ENABLED", True)
    monkeypatch.setattr(video, "_pick_bgm", lambda d, j: "PICKED")
    captured = {}
    monkeypatch.setattr(video, "_master_audio", lambda src, out, bgm, scale=None: captured.update(bgm=bgm))
    video.render_video([{"caption": "a", "narration": "n1"}, {"caption": "b", "narration": "n2"}], job_id="withbgm")
    assert captured["bgm"] == "PICKED"


def test_global_cues_offset_by_scene(monkeypatch):
    # 장면 2개, 각 1문장. 장면 클립 길이를 고정해 전역 cue 오프셋을 검증.
    from popory_content import video as V

    monkeypatch.setattr(V, "_duration", lambda p: 5.0)  # 모든 클립 5초로 측정
    # render 내부의 무거운 ffmpeg/TTS 호출을 우회: 장면-로컬 cue를 직접 합성.
    local = [[(0.0, 2.0, "첫 문장")], [(0.0, 1.5, "둘째 문장")]]
    durations = [5.0, 5.0]
    offsets = V.scene_offsets(durations, V.XFADE_TD)
    cues = []
    for off, scene in zip(offsets, local):
        cues += [(off + st, off + en, t) for (st, en, t) in scene]
    assert cues[0] == (0.0, 2.0, "첫 문장")
    assert cues[1] == (4.6, 6.1, "둘째 문장")  # 5.0 - 0.4 = 4.6 오프셋
