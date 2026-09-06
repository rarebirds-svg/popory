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


def test_master_audio_copies_video(tmp_path, monkeypatch):
    # 마스터 단계는 오디오만 손댄다 — 비디오를 재인코딩하면 3세대 손실이 붙는다.
    cmds = []
    monkeypatch.setattr(_video, "_run", lambda cmd: cmds.append(cmd))
    _video._master_audio(tmp_path / "in.mp4", tmp_path / "out.mp4", None)
    cmd = cmds[0]
    assert "copy" in cmd and "libx264" not in cmd
    assert not any("scale=" in str(a) for a in cmd)


def test_master_audio_with_bgm_still_copies_video(tmp_path, monkeypatch):
    # BGM 이 붙어도 비디오는 copy 여야 한다(쇼츠 다운스케일 회귀 방지).
    cmds = []
    monkeypatch.setattr(_video, "_run", lambda cmd: cmds.append(cmd))
    _video._master_audio(tmp_path / "in.mp4", tmp_path / "out.mp4", tmp_path / "bgm.mp3")
    cmd = cmds[0]
    assert "copy" in cmd and "libx264" not in cmd
    assert not any("scale=" in str(a) for a in cmd)


def test_x264_q_shorts_richer_than_longform():
    # 쇼츠(60초 상한)는 롱폼(10분)보다 후하게 — 1080×1920 에 구워 넣은 글자가 뭉개지지 않게.
    long_q, short_q = _video._x264_q(portrait=False), _video._x264_q(portrait=True)
    assert int(short_q[short_q.index("-crf") + 1]) < int(long_q[long_q.index("-crf") + 1])
    short_rate = int(short_q[short_q.index("-maxrate") + 1].rstrip("k"))
    long_rate = int(long_q[long_q.index("-maxrate") + 1].rstrip("k"))
    assert short_rate > long_rate
    # 60초 × maxrate 가 Cloudflare 업로드 한도(100MB)를 넘지 않아야 한다.
    assert short_rate * 60 / 8 / 1000 < 100


def test_bufsize_derives_from_maxrate():
    # env 로 maxrate 만 바꿔도 VBV 버퍼가 어긋나지 않는다.
    assert _video._bufsize("6000k") == "12000k"
    assert _video._bufsize("1200k") == "2400k"
    assert _video._bufsize("weird") == "weird"


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
    """짧은 장면(3초)은 장면 절반에서 한 번 되돌린다 — 주기가 곧 장면 길이(90프레임)."""
    from popory_content.video import _zoompan_filter, _MOTIONS, _zoom_amplitude
    amp = _zoom_amplitude(3.0)
    f_in = _zoompan_filter(3.0, variant=0)     # 넓게 시작 → 확대 → 복귀
    f_out = _zoompan_filter(3.0, variant=1)    # 확대로 시작 → 축소 → 복귀
    assert f"1.0+{amp:.4f}*(1-abs(1-2*mod(on,90)/90))" in f_in
    assert f"{1 + amp:.4f}-{amp:.4f}*(1-abs(1-2*mod(on,90)/90))" in f_out


def test_pan_headroom_uses_pixels_cover_crop_would_discard():
    from popory_content.video import _pan_headroom
    # 1024² 원본을 1920x1080에 커버하면 1.875배로 1920x1920이 되고 세로 840px이 잘린다.
    assert _pan_headroom((1024, 1024)) == 840
    # 세로형은 같은 원본에서 가로로 840px이 남는다.
    assert _pan_headroom((1024, 1024), portrait=True) == 840
    # 이미 16:9인 원본은 버려지는 여유가 없다 → 패닝 없음.
    assert _pan_headroom((1920, 1080)) == 0
    assert _pan_headroom(None) == 0


def test_pan_amplitude_capped_by_headroom_and_floor():
    from popory_content.video import _pan_amplitude, PAN_RATE_PX_PER_SEC, PAN_MIN_PX
    # 편도라 목표 속도 × 길이. 44.6초면 312px로 840px 여유 안에 들어간다.
    assert _pan_amplitude(44.6, 840) == int(PAN_RATE_PX_PER_SEC * 44.6)
    # 여유가 부족하면 여유까지만 — 확대를 더 하지 않기 위함.
    assert _pan_amplitude(44.6, 120) == 120
    # 여유가 아예 없으면(16:9 원본) 패닝 없음.
    assert _pan_amplitude(44.6, 0) == 0
    # 너무 짧으면 캔버스만 키우고 체감이 없으므로 걸지 않는다.
    assert _pan_amplitude(3.0, 840) == 0
    assert PAN_MIN_PX > 0


def test_zoompan_pans_with_crop_after_zoom():
    from popory_content.video import _zoompan_filter
    f = _zoompan_filter(20.0, variant=0, pan_px=140)
    # 캔버스가 패닝 여유만큼(수퍼샘플 기준 2배) 세로로 길어진다.
    assert "scale=3840:2440," in f and "s=3840x2440" in f
    # zoompan 이 먼저, crop 이 나중 — 순서가 뒤바뀌면 패닝이 얼어붙는다.
    assert f.index("zoompan") < f.index("crop")
    # crop 은 프레임 크기 창을 세로로 움직인다.
    assert "crop=3840:2160:0:'(ih-oh)*(t/20.000)'" in f
    # zoompan 의 s 는 입력과 같은 크기 — 다르면 종횡비가 눌린다.
    assert "s=3840x2160" not in f


def test_zoompan_without_headroom_keeps_old_chain():
    from popory_content.video import _zoompan_filter
    f = _zoompan_filter(20.0, variant=0, pan_px=0)
    assert "crop=" not in f                  # 패닝 여유가 없으면 crop 자체를 걸지 않는다
    assert "scale=3840:2160," in f and "s=3840x2160" in f


def test_zoompan_pan_direction_varies_by_variant():
    from popory_content.video import _zoompan_filter, _MOTIONS
    fwd = [m[2] for m in _MOTIONS]
    assert any(fwd) and not all(fwd)          # 정방향·역방향이 섞여 있다
    v_fwd = next(i for i, m in enumerate(_MOTIONS) if m[2])
    v_back = next(i for i, m in enumerate(_MOTIONS) if not m[2])
    assert "(t/20.000)'" in _zoompan_filter(20.0, variant=v_fwd, pan_px=140)
    assert "(1-t/20.000)'" in _zoompan_filter(20.0, variant=v_back, pan_px=140)


def test_render_card_canvas_and_scrim_flag(tmp_path):
    from popory_content.video import _render_card
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), (180, 180, 180)).save(buf, format="PNG")
    bg = buf.getvalue()
    out = tmp_path / "canvas.png"
    _render_card("", "", out, bg_image_bytes=bg, canvas=(1920, 1220), scrim=False)
    img = Image.open(out)
    assert img.size == (1920, 1220)          # 확장 캔버스로 커버 크롭
    # scrim=False 면 하단이 어두워지지 않는다(스크림은 화면 고정 오버레이가 담당).
    assert img.getpixel((960, 1215))[0] > 150


def test_render_scrim_png_is_bottom_gradient(tmp_path):
    from popory_content.video import _render_scrim_png
    from PIL import Image
    out = tmp_path / "scrim.png"
    _render_scrim_png(out)
    img = Image.open(out).convert("RGBA")
    assert img.size == (1920, 1080)
    assert img.getpixel((960, 100))[3] == 0        # 상단은 완전 투명
    assert img.getpixel((960, 1070))[3] > 150      # 하단은 진하게


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


def test_headline_places_logo_left_of_title(tmp_path):
    from PIL import Image
    from popory_content import video
    out = tmp_path / "head.png"
    video._render_headline_png("챕터 제목", out)
    img = Image.open(out).convert("RGBA")
    assert img.size == (1920, 1080)
    # 로고 자리(좌상단)에 불투명 픽셀이 있다.
    logo_box = img.crop((video.LOGO_X, video.LOGO_Y,
                         video.LOGO_X + video.LOGO_SIZE, video.LOGO_Y + video.LOGO_SIZE))
    assert logo_box.split()[-1].getextrema()[1] > 0
    # 원형 마스크라 로고 상자의 네 모서리는 투명하다(검은 사각형이 드러나지 않는다).
    assert logo_box.getpixel((1, 1))[3] == 0
    assert logo_box.getpixel((video.LOGO_SIZE - 2, 1))[3] == 0
    # 제목은 로고 오른쪽에서 시작한다 → 로고 왼쪽 여백엔 글자가 없다.
    assert img.crop((0, 0, video.LOGO_X, 1080)).split()[-1].getextrema()[1] == 0


def test_headline_falls_back_to_text_when_logo_missing(monkeypatch, tmp_path):
    # 로고 파일이 없어도 헤드라인은 그려져야 한다(영상 전체가 죽으면 안 됨).
    from PIL import Image
    from popory_content import video
    monkeypatch.setattr(video, "LOGO_PATH", tmp_path / "없는파일.png")
    out = tmp_path / "head2.png"
    video._render_headline_png("챕터 제목", out)
    img = Image.open(out).convert("RGBA")
    assert img.split()[-1].getextrema()[1] > 0   # 글자는 그려졌다


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
    monkeypatch.setattr(video, "_pick_bgm_moods", lambda d, j: None)   # 분위기 버킷이 없으면 한 곡
    captured = {}
    monkeypatch.setattr(video, "_master_audio", lambda src, out, bgm, scale=None: captured.update(bgm=bgm))
    video.render_video([{"caption": "a", "narration": "n1"}, {"caption": "b", "narration": "n2"}], job_id="withbgm")
    assert captured["bgm"] == "PICKED"


def test_render_video_builds_mood_bed_when_both_buckets_exist(monkeypatch, tmp_path):
    from popory_content import video
    _render_stub(monkeypatch, tmp_path, video)
    monkeypatch.setattr(video, "TMP", tmp_path)
    monkeypatch.setattr(video, "BGM_ENABLED", True)
    monkeypatch.setattr(video, "_pick_bgm_moods", lambda d, j: (Path("tense.mp3"), Path("warm.mp3")))
    built = {}
    monkeypatch.setattr(video, "_build_bgm_bed", lambda t, w, total, out: built.update(t=t, w=w, total=total) or out)
    captured = {}
    monkeypatch.setattr(video, "_master_audio", lambda src, out, bgm, scale=None: captured.update(bgm=bgm))
    video.render_video([{"caption": "a", "narration": "n1"}, {"caption": "b", "narration": "n2"}], job_id="bed")
    assert captured["bgm"].name == "bgm_bed.mp3"
    assert built["t"].name == "tense.mp3" and built["w"].name == "warm.mp3"
    # 총 길이 = 클립 합 - 크로스페이드(클립 길이 1.0 스텁 × 2 - 0.4)
    assert abs(built["total"] - 1.6) < 1e-6


def test_bgm_mood_by_filename_and_deterministic_pair(tmp_path):
    from popory_content.video import _bgm_mood, _pick_bgm_moods
    for name, mood in (("pad_deep_emin", "tense"), ("pad_warm_am", "tense"), ("pad_hope_g", "warm"), ("pad_bright_d", "warm")):
        assert _bgm_mood(Path(f"{name}.mp3")) == mood
    assert _pick_bgm_moods(tmp_path, "j") is None                # 빈 폴더
    (tmp_path / "pad_deep_emin.mp3").write_bytes(b"x")
    assert _pick_bgm_moods(tmp_path, "j") is None                # warm 버킷 없음 → 한 곡 방식
    (tmp_path / "pad_hope_g.mp3").write_bytes(b"x")
    pair = _pick_bgm_moods(tmp_path, "j")
    assert pair == (tmp_path / "pad_deep_emin.mp3", tmp_path / "pad_hope_g.mp3")
    assert _pick_bgm_moods(tmp_path, "j") == pair                # 결정적


def test_build_bgm_bed_splits_at_ratio_with_crossfade(monkeypatch, tmp_path):
    cmds = []
    monkeypatch.setattr(_video, "_run", lambda cmd: cmds.append(cmd))
    out = _video._build_bgm_bed(Path("t.mp3"), Path("w.mp3"), 100.0, tmp_path / "bed.mp3", ratio=0.55, xfade=4.0)
    assert out == tmp_path / "bed.mp3"
    graph = cmds[-1][cmds[-1].index("-filter_complex") + 1]
    assert "atrim=0:55.000" in graph and "acrossfade=d=4.0" in graph
    assert "atrim=0:50.000" in graph          # 100-55+4+1 — 크로스페이드가 먹는 만큼 여유
    assert cmds[-1].count("-stream_loop") == 2  # 곡이 짧아도 끊기지 않게 둘 다 반복
    # 짧은 영상(쇼츠)은 전환 자리가 없어 앞 곡만 쓴다
    cmds.clear()
    _video._build_bgm_bed(Path("t.mp3"), Path("w.mp3"), 8.0, tmp_path / "bed2.mp3")
    assert "w.mp3" not in " ".join(cmds[-1]) and "-filter_complex" not in cmds[-1]


def test_gaps_for_lengthens_pause_after_questions():
    from popory_content.video import _gaps_for, SENTENCE_GAP, QUESTION_GAP
    gaps = _gaps_for(["왜 무너졌을까요?", "답은 태도였습니다.", "그럼 무엇을 해야 할까요?", "끝."])
    assert gaps == [QUESTION_GAP, SENTENCE_GAP, QUESTION_GAP]
    assert QUESTION_GAP > SENTENCE_GAP
    assert _gaps_for(["하나."]) == []


def test_spans_and_concat_accept_per_gap_lists(monkeypatch, tmp_path):
    from popory_content.video import _spans_from_durations, _concat_audio_with_gaps
    spans = _spans_from_durations([2.0, 3.0, 1.0], [1.0, 0.5])
    assert spans == [(0.0, 3.0), (3.0, 6.5), (6.5, 7.5)]
    cmds = []
    monkeypatch.setattr(_video, "_run", lambda cmd: cmds.append(cmd))
    segs = [tmp_path / f"{i}.mp3" for i in range(3)]
    _concat_audio_with_gaps(segs, [1.0, 0.7], tmp_path / "out.mp3")
    silences = [c for c in cmds if "anullsrc=channel_layout=mono:sample_rate=24000" in c]
    assert sorted(c[c.index("-t") + 1] for c in silences) == ["0.700", "1.000"]  # 길이별 무음 1개씩
    concat = cmds[-1]
    inputs = [concat[i + 1] for i, a in enumerate(concat) if a == "-i"]
    assert inputs[1].endswith("_gap1_000.wav") and inputs[3].endswith("_gap0_700.wav")


def _zoom_at(amp: float, period: int, zoom_in_first: bool, on: float) -> float:
    """_zoompan_filter 가 만드는 z 식을 파이썬으로 그대로 재현한다(연속성·속도 검증용)."""
    tri = 1 - abs(1 - 2 * (on % period) / period)
    return 1.0 + amp * tri if zoom_in_first else (1 + amp) - amp * tri


def test_zoom_cycle_holds_one_speed_for_every_scene_length():
    """긴 장면일수록 느려지던 문제의 해법 — 폭이 아니라 반주기를 고정해 초당 속도를 맞춘다."""
    from popory_content.video import _zoom_cycle, ZOOM_HALF_CYCLE_SECONDS
    speeds = []
    for dur in (20.0, 35.0, 53.0):
        amp, period = _zoom_cycle(dur)
        half = period / 2 / 30
        assert abs(half - ZOOM_HALF_CYCLE_SECONDS) < 1e-6      # 긴 장면은 주기 고정
        speeds.append(amp / half)
    assert max(speeds) - min(speeds) < 1e-9                    # 길이가 달라도 같은 속도
    # 쇼츠(7초)는 장면 절반에서 한 번만 되돌린다 — 예전 폭·속도 그대로
    amp, period = _zoom_cycle(7.0)
    assert abs(period / 30 - 7.0) < 0.05 and amp == 0.06


def test_zoom_curve_never_jumps_and_keeps_a_constant_rate():
    """2026-09-06 피드백: 재생 도중 화면이 갑자기 원본 크기로 되돌아갔다. 샷 경계에서 배율을
    1.0 ↔ 1+폭 으로 튀게 한 탓이다. 이제 곡선은 어디서도 끊기지 않아야 한다."""
    from popory_content.video import _zoom_cycle, ZOOM_HALF_CYCLE_SECONDS
    dur = 35.0
    amp, period = _zoom_cycle(dur)
    frames = round(dur * 30)
    zs = [_zoom_at(amp, period, True, on) for on in range(frames + 1)]
    steps = [abs(zs[i + 1] - zs[i]) for i in range(len(zs) - 1)]
    per_frame = amp / (period / 2)
    # 프레임 간 변화가 전부 같다 = 점프 없음 + 등속. 예전 코드는 경계에서 amp(0.06) 만큼 튀었다.
    assert max(steps) < per_frame * 1.5
    assert max(steps) < amp / 2                       # 회귀 방지: 경계 점프(=amp)면 여기서 걸린다
    assert abs(max(steps) - min(steps)) < 1e-9
    # 배율은 언제나 [1.0, 1+폭] 안에 있고, 반주기마다 방향이 바뀐다
    assert min(zs) >= 1.0 - 1e-9 and max(zs) <= 1 + amp + 1e-9
    half_frames = period // 2
    assert zs[half_frames] > zs[0] and zs[period] < zs[half_frames]


def test_zoompan_expression_is_one_continuous_wave():
    """식 자체에 조건 분기가 없어야 한다 — if/floor 로 구간을 나누면 그 경계가 곧 점프다."""
    from popory_content.video import _zoompan_filter
    fl = _zoompan_filter(35.0, variant=0)
    z_expr = fl.split("z='")[1].split("'")[0]
    assert "if(" not in z_expr and "floor(" not in z_expr
    assert "mod(on," in z_expr                        # 연속 삼각파
    # 기준점도 장면 내내 고정 — 도중에 옮기면 그 자체가 화면이 튀는 것으로 보인다
    assert "if(" not in fl.split(":x='")[1].split("'")[0]
    assert "if(" not in fl.split(":y='")[1].split("'")[0]


def test_render_video_inserts_card_clip_before_scene(monkeypatch, tmp_path):
    from popory_content import video
    _render_stub(monkeypatch, tmp_path, video)
    monkeypatch.setattr(video, "TMP", tmp_path)
    monkeypatch.setattr(video, "CARDS_ENABLED", True)
    monkeypatch.setattr(video, "_master_audio", lambda src, out, bgm, scale=None: None)
    monkeypatch.setattr(video, "_pick_bgm", lambda d, j: None)
    made = []
    monkeypatch.setattr(video, "_card_clip", lambda card, i, work, portrait=False: made.append((i, card["type"])) or (work / f"card_{i}.mp4"))
    durs = []
    monkeypatch.setattr(video, "_xfade_graph", lambda d, td=0.4: durs.extend(d) or ("", "v", "a"))
    scenes = [{"caption": "a", "narration": "n1."},
              {"caption": "b", "narration": "n2.", "card": {"type": "quote", "text": "부는 보이지 않는다", "source": "책"}},
              {"caption": "c", "narration": "n3.", "card": {"type": "keypoints", "title": "3원칙", "items": ["복리", "인내"]}}]
    _, _, _, cues = video.render_video(scenes, job_id="cards")
    assert made == [(1, "quote"), (2, "keypoints")]
    assert len(durs) == 5                                   # 장면 3 + 카드 2 클립
    assert [c[2] for c in cues] == ["n1.", "n2.", "n3."]    # 카드는 cue 를 만들지 않는다
    # 카드 클립이 앞에 끼어도 뒤 장면 cue 오프셋이 그만큼 밀린다(클립 길이 1.0 스텁, xfade 0.4)
    assert abs(cues[1][0] - (2 * (1.0 - 0.4))) < 1e-6


def test_card_clip_failure_does_not_break_render(monkeypatch, tmp_path):
    from popory_content import video
    _render_stub(monkeypatch, tmp_path, video)
    monkeypatch.setattr(video, "TMP", tmp_path)
    monkeypatch.setattr(video, "CARDS_ENABLED", True)
    monkeypatch.setattr(video, "_master_audio", lambda src, out, bgm, scale=None: None)
    monkeypatch.setattr(video, "_pick_bgm", lambda d, j: None)

    def boom(*a, **k):
        raise video.VideoError("ffmpeg died")
    monkeypatch.setattr(video, "_card_clip", boom)
    scenes = [{"caption": "a", "narration": "n1.", "card": {"type": "quote", "text": "x"}}, {"caption": "b", "narration": "n2."}]
    _, _, _, cues = video.render_video(scenes, job_id="cardfail")
    assert len(cues) == 2


def test_card_clip_uses_silence_or_chime_and_matches_scene_audio_format(monkeypatch, tmp_path):
    cmds = []
    monkeypatch.setattr(_video, "_run", lambda cmd: cmds.append(cmd))
    monkeypatch.setattr(_video, "_render_graphic_card_png", lambda card, png, portrait=False: None)
    monkeypatch.setattr(_video, "CARD_SFX", tmp_path / "없음.mp3")
    clip = _video._card_clip({"type": "quote", "text": "x"}, 3, tmp_path)
    assert clip == tmp_path / "card_3.mp4"
    cmd = cmds[-1]
    assert "anullsrc=channel_layout=mono:sample_rate=24000" in cmd and "-crf" in cmd
    assert cmd[cmd.index("-t") + 1] == f"{_video.CARD_SECONDS:.3f}"
    chime = tmp_path / "chime.mp3"; chime.write_bytes(b"x")
    monkeypatch.setattr(_video, "CARD_SFX", chime)
    _video._card_clip({"type": "quote", "text": "x"}, 4, tmp_path)
    cmd = cmds[-1]
    assert str(chime) in cmd and "sample_rates=24000:channel_layouts=mono" in " ".join(cmd)


@pytest.mark.skipif(not Path(FONT_PATH).exists(), reason="한국어 폰트 필요")
def test_render_graphic_card_png_quote_and_keypoints(tmp_path):
    q = tmp_path / "q.png"; k = tmp_path / "k.png"
    _video._render_graphic_card_png({"type": "quote", "text": "부는 보이지 않는다", "source": "모건 하우절"}, q)
    _video._render_graphic_card_png({"type": "keypoints", "title": "부자의 3가지 원칙", "items": ["복리", "인내심", "통제권"]}, k, portrait=True)
    assert _Image.open(q).size == (1920, 1080) and _Image.open(k).size == (1080, 1920)


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


# --- 쇼츠 자막 위치 (폰트 없이 상수만 검사) ---

def test_portrait_subtitle_clears_youtube_ui_band():
    """쇼츠 번인 자막이 재생기 UI 띠를 침범하면 YouTube 제목과 겹쳐 둘 다 안 읽힌다.
    2026-08-22 업로드분에서 실제로 그랬다(자막이 UI 안으로 139px 들어가 있었다)."""
    top = _video.PORTRAIT_H - _video.SUB_Y_PORTRAIT
    bottom = top + _video.SUB_LINE_H_PORTRAIT
    ui_top = _video.PORTRAIT_H - _video.PORTRAIT_UI_SAFE_BOTTOM
    assert bottom <= ui_top, f"자막 하단 {bottom} 이 UI 안전선 {ui_top} 을 침범한다"
    assert top > _video.PORTRAIT_H * 0.6, f"자막 상단 {top} 이 너무 높다 — 화면 중앙을 가린다"


def test_portrait_subtitle_stays_inside_scrim():
    """자막은 하단 스크림 그라데이션 안에 있어야 밝은 배경에서도 읽힌다."""
    scrim_top = _video.PORTRAIT_H - int(_video.PORTRAIT_H * 0.4)
    assert _video.PORTRAIT_H - _video.SUB_Y_PORTRAIT > scrim_top


def test_landscape_subtitle_unchanged():
    """가로형은 재생기 UI 가 재생 중 숨으므로 기존 위치를 유지한다."""
    assert _video.SUB_Y_LANDSCAPE == 175


def test_make_video_runs_script_review_before_render(monkeypatch):
    """검수가 렌더 앞에 서서 TTS·자막·제목이 교정본으로 나가고, 결과가 meta.script_review 에 남는다."""
    order = []
    scenes = [{"caption": "범트", "narration": "범트 이야기.", "image_prompt": "x"}]
    monkeypatch.setattr(_video, "generate_scenes", lambda **kw: (scenes, {"title": "범트"}))

    def fake_review(sc, meta, *, job_id):
        order.append("review"); sc[0]["caption"] = "버몬트"; return {"status": "ok", "fixes": [{"from": "범트", "to": "버몬트"}]}
    monkeypatch.setattr(_video, "review_script", fake_review)

    def fake_render(sc, **kw):
        order.append(("render", sc[0]["caption"])); return (Path("/tmp/x.mp4"), 0, 1, [])
    monkeypatch.setattr(_video, "render_video", fake_render)
    _, out_scenes, meta, *_ = _video.make_video(topic="t", sources=[], style_samples=[], job_id="j")
    assert order == ["review", ("render", "버몬트")]
    assert meta["script_review"]["status"] == "ok"
