# tools/chapter_voices.py — 긴 원고 챕터 경계 목소리 비교 도구의 잇기·자르기·재기·페이지.
# 네트워크 없이 돌도록 Cloud TTS·MP3 디코드는 가짜(화자마다 다른 음높이의 합성 유성음)로 바꾼다.
import importlib.util
import math
import shutil
import sys
from array import array
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "chapter_voices", Path(__file__).resolve().parents[1] / "tools" / "chapter_voices.py")
cv = importlib.util.module_from_spec(_spec)
sys.modules["chapter_voices"] = cv
_spec.loader.exec_module(cv)

R = cv.RATE


def _voiced(f0: float, seconds: float, amp: int = 6000) -> bytes:
    """f0 의 성대음 비슷한 신호(배음 몇 개) — voice_profile 이 음높이를 잴 수 있다."""
    n = round(seconds * R)
    return array("h", (int(amp * sum(math.sin(2 * math.pi * f0 * h * t / R) / h for h in (1, 2, 3)))
                       for t in range(n))).tobytes()


def test_default_draft_matches_the_job_it_references():
    """기본 원고는 작업 5c2ee146(16장면·93문장)의 대본이다 — 지금 영상 자막과 문장 수가 같아야 경계를 자른다."""
    scenes = cv.load_scenes(cv.DEFAULT_DRAFT)
    assert len(scenes) == 16
    assert sum(len(s) for s in cv.scene_sentences(scenes)) == 93
    assert cv.load_scenes(cv.DEFAULT_DRAFT, "3-5")[0]["caption"] == scenes[3]["caption"]


def test_default_picks_are_known_male_candidates_without_charon():
    assert set(cv.DEFAULT_PICKS) <= set(cv.CANDIDATES)
    assert "charon" not in cv.DEFAULT_PICKS        # 취향 사유로 두 번 기각된 화자
    assert all("Chirp3-HD" in cv.CANDIDATES[p][0] for p in cv.DEFAULT_PICKS)


def test_resolve_picks_reports_unknown_and_unavailable():
    avail = [{"name": "ko-KR-Chirp3-HD-Iapetus", "gender": "MALE"}]
    voices, notes = cv.resolve_picks(["iapetus", "orus", "nobody"], avail)
    assert [v[0] for v in voices] == ["iapetus"]
    assert any("orus" in n for n in notes) and any("nobody" in n for n in notes)
    voices, _ = cv.resolve_picks(["iapetus", "orus"], None)      # 목록 조회 실패 — 그대로 믿는다
    assert [v[0] for v in voices] == ["iapetus", "orus"]


def test_assemble_uses_the_video_gaps():
    """장면 안은 문장 0.7초·질문 뒤 1.0초, 장면 사이는 영상에서 들리는 CHAPTER_GAP - XFADE_TD."""
    one = b"\x01\x00" * R           # 1초
    sentences = [["가요?", "나다."], ["다다."]]
    full, spans = cv.assemble([[one, one], [one]], sentences)
    assert spans[0][0] == (0, R)
    gap_q = spans[0][1][0] - spans[0][0][1]
    assert gap_q == round(1.0 * R)
    gap_scene = spans[1][0][0] - spans[0][1][1]
    assert gap_scene == round(cv.SCENE_GAP_S * R) and abs(cv.SCENE_GAP_S - 1.0) < 1e-9
    assert len(full) // 2 == spans[1][0][1]


def test_montage_joins_scene_tail_and_next_head_with_marks():
    a, b, c = (bytes([k, 0]) * R for k in (1, 2, 3))
    full, spans = cv.assemble([[a, a], [b, b], [c]], [["가.", "나."], ["다.", "라."], ["마."]])
    mont, marks = cv.montage(full, spans, context=1)
    # 경계 2개: (장면0 끝 문장 + 쉼 + 장면1 첫 문장), 띄움, (장면1 끝 + 쉼 + 장면2 첫)
    per = 2 * R + round(cv.SCENE_GAP_S * R)
    assert [k for _, k in marks] == [0, 1]
    assert marks[0][0] == 0 and marks[1][0] == pytest.approx((per + round(cv.BOUNDARY_GAP_S * R)) / R)
    assert len(mont) // 2 == 2 * per + round(cv.BOUNDARY_GAP_S * R)
    s = array("h")
    s.frombytes(mont)
    assert s[0] == 1 and s[R + round(cv.SCENE_GAP_S * R)] == 2       # 앞 장면 소리 → 다음 장면 소리


def test_map_cues_needs_same_sentences():
    sentences = [["첫 문장이다.", "둘째다."], ["셋째다."]]
    cues = [(0.0, 1.5, "첫 문장이다."), (1.5, 2.4, "둘째다."), (4.0, 5.0, "셋째다.")]
    spans = cv.map_cues(cues, sentences)
    assert spans == [[(0, round(1.5 * R)), (round(1.5 * R), round(2.4 * R))], [(round(4.0 * R), round(5.0 * R))]]
    assert cv.map_cues(cues[:2], sentences) is None                          # 문장 수가 다르다
    assert cv.map_cues([(0, 1, "다른"), (1, 2, "대본"), (2, 3, "이다")], sentences) is None


def test_trim_silence_keeps_only_the_sound_with_a_small_pad():
    sound = _voiced(120, 0.5)
    pcm = cv._silence(0.7) + sound + cv._silence(0.7)
    out = cv.trim_silence(pcm)
    pad = round(cv.TRIM_PAD_S * R)
    assert abs(len(out) // 2 - (len(sound) // 2 + 2 * pad)) <= 2 * 240     # 프레임(10ms) 단위
    assert cv.trim_silence(cv._silence(1.0)) == b""


def test_measure_finds_the_pitch_step_between_scenes():
    """장면 0·1 은 120Hz, 장면 2 는 2반음 위 — 폭과 경계 차가 그만큼 나온다."""
    hi = 120 * 2 ** (2 / 12)
    pieces = [[_voiced(120, 5.0)], [_voiced(120, 5.0)], [_voiced(hi, 5.0)]]
    sentences = [["가" * 40 + "."], ["나" * 40 + "."], ["다" * 40 + "."]]
    m = cv.measure(pieces, sentences)
    s = m["summary"]
    assert s["scenes_measured"] == 3
    assert s["pitch_spread_st"] == pytest.approx(2.0, abs=0.3)
    assert s["pitch_jump_st"] == pytest.approx(1.0, abs=0.2)                 # (0 + 2) / 2
    assert cv.measure([[None]], [["가."]])["summary"] == {"scenes_measured": 0}


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")
def test_main_end_to_end_with_fake_tts(tmp_path, monkeypatch):
    """가짜 TTS 로 끝까지 — 화자별 MP3·index.html·report.json, 캐시 재사용, 합성 실패 화자 표시."""
    draft = tmp_path / "d.txt"
    draft.write_text("[하나]\n" + "가" * 30 + "입니다. 그렇죠?\n\n[둘]\n" + "나" * 30 + "입니다.\n", encoding="utf-8")
    f0 = {"ko-KR-Chirp3-HD-Iapetus": 118.0, "ko-KR-Chirp3-HD-Orus": 104.0}
    calls = []

    def fake_synth(text, voice, rate=None):
        calls.append((voice, rate))
        if voice not in f0:
            return None
        return f"{voice}|{len(text)}".encode()

    def fake_decode(data):
        voice, n = data.decode().split("|")
        return _voiced(f0[voice], max(4.5, int(n) * 0.15))

    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    monkeypatch.setattr(cv, "list_voices", lambda key: [{"name": n, "gender": "MALE"} for n in
                                                       (*f0, "ko-KR-Chirp3-HD-Schedar")])
    monkeypatch.setattr(cv.tts, "synthesize", fake_synth)
    monkeypatch.setattr(cv, "decode_mp3", fake_decode)
    monkeypatch.setattr(cv, "OUT_ROOT", tmp_path / "root")
    monkeypatch.setattr(cv.time, "sleep", lambda s: None)
    out = tmp_path / "out"
    args = ["--draft", str(draft), "--voices", "iapetus,orus,schedar", "--out", str(out), "--workers", "2"]
    assert cv.main(args) == 0
    for stem in ("iapetus", "orus"):
        assert (out / f"{stem}_boundaries.mp3").stat().st_size > 0
        assert (out / f"{stem}_full.mp3").stat().st_size > 0
    page = (out / "index.html").read_text(encoding="utf-8")
    assert "ko-KR-Chirp3-HD-Iapetus" in page and "seek(0," in page
    assert "한 문장도 합성하지 못했다" in page                                    # schedar(가짜 실패)
    assert all(r == cv.CHIRP_RATE for _, r in calls)                         # Chirp3-HD 기준 말속도로 보낸다
    import json
    rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
    iap = next(e for e in rep["entries"] if e["label"].startswith("iapetus"))
    assert iap["measure"]["summary"]["pitch_spread_st"] < 0.5               # 고정 화자 — 장면 사이 폭이 작다
    # 다시 돌리면 성공한 문장은 캐시에서 — 실패한 화자만 다시 보낸다
    calls.clear()
    assert cv.main(args[:-4] + ["--out", str(tmp_path / "out2")]) == 0
    assert {v for v, _ in calls} == {"ko-KR-Chirp3-HD-Schedar"}


def test_dry_run_sends_nothing(monkeypatch, capsys):
    monkeypatch.delenv("GOOGLE_TTS_API_KEY", raising=False)
    monkeypatch.setattr(cv.tts, "synthesize", lambda *a, **k: pytest.fail("보내면 안 된다"))
    assert cv.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "장면 16개" in out and "문장 93개" in out


def test_list_voices_sends_the_key_in_a_header_and_never_prints_it(monkeypatch):
    """키를 쿼리에 두면 requests 오류 문구(…for url: …?key=…)에 그대로 찍힌다 — 머리글로 보내고 오류엔 상태·문구만."""
    seen = {}

    class Resp:
        status_code = 403
        text = '{"error": {"message": "API key not valid. Please pass a valid API key."}}'

        def json(self):
            return {"error": {"message": "API key not valid. Please pass a valid API key."}}

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.update(url=url, params=params, headers=headers)
        return Resp()

    monkeypatch.setattr(cv.requests, "get", fake_get)
    with pytest.raises(cv.VoiceListError) as ei:
        cv.list_voices("AIzaSECRET")
    assert "AIzaSECRET" not in str(ei.value) and "403" in str(ei.value) and "not valid" in str(ei.value)
    assert "key" not in seen["params"] and seen["headers"] == {"X-Goog-Api-Key": "AIzaSECRET"}

    def boom(*a, **k):
        raise cv.requests.ConnectionError("Max retries exceeded with url: /v1/voices?key=AIzaSECRET")

    monkeypatch.setattr(cv.requests, "get", boom)
    with pytest.raises(cv.VoiceListError) as ei:
        cv.list_voices("AIzaSECRET")
    assert "AIzaSECRET" not in str(ei.value)


def test_cache_key_follows_what_is_actually_sent():
    """정규화(숫자 읽기 등)가 같은 SSML 을 만들면 같은 키, 화자·말속도가 다르면 다른 키."""
    k = cv.cache_key("v", 1.06, "16년 동안.")
    assert k == cv.cache_key("v", 1.06, "16년 동안.")
    assert k != cv.cache_key("v", 1.0, "16년 동안.") and k != cv.cache_key("w", 1.06, "16년 동안.")


def test_context_must_be_positive():
    with pytest.raises(SystemExit):
        cv.main(["--dry-run", "--context", "0"])
    with pytest.raises(SystemExit):
        cv.main(["--dry-run", "--scenes", "20-30"])          # 16장면 원고 밖


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")
def test_scene_subset_still_gets_the_current_video(tmp_path, monkeypatch):
    """--scenes 로 일부만 읽어도 지금 영상의 자막은 원고 전체와 맞춘 뒤 그 장면만 잘라 쓴다. 칩은 원고의 장면 번호."""
    scenes = cv.load_scenes(cv.DEFAULT_DRAFT)
    sentences = cv.scene_sentences(scenes)
    cues, t = [], 0.0
    for sc in sentences:
        for s in sc:
            cues.append((t, t + 1.0, s))
            t += 1.7
        t += 1.0
    total = round((t + 1.0) * cv.RATE)
    # 문장 구간마다 소리, 나머지는 무음 — 지금 영상 흉내
    buf = bytearray(total * 2)
    tone = _voiced(118, 1.0)
    for st, _, _ in cues:
        a = round(st * cv.RATE) * 2
        buf[a:a + len(tone)] = tone
    ref = bytes(buf)
    fetched = []
    monkeypatch.setattr(cv, "fetch_reference", lambda job: (fetched.append(job), (ref, cues))[1])
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    monkeypatch.setattr(cv, "list_voices", lambda key: [{"name": "ko-KR-Chirp3-HD-Iapetus", "gender": "MALE"}])
    monkeypatch.setattr(cv.tts, "synthesize", lambda text, voice, rate=None: str(len(text)).encode())
    monkeypatch.setattr(cv, "decode_mp3", lambda d: _voiced(110, max(0.5, int(d) * 0.05)))
    monkeypatch.setattr(cv, "OUT_ROOT", tmp_path / "root")
    out = tmp_path / "out"
    assert cv.main(["--voices", "iapetus", "--scenes", "3-5", "--out", str(out)]) == 0
    assert fetched == [cv.DEFAULT_JOB]
    page = (out / "index.html").read_text(encoding="utf-8")
    assert 'class="ref"' in page and "맞지 않아" not in page                     # 참조 카드가 있다
    assert "4→5" in page and "5→6" in page and "1→2" not in page            # 원고 장면 번호(3·4·5 → 사람 번호 4·5·6)
    assert (out / "current_boundaries.mp3").exists()
