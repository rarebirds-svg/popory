# compare_voices.py — Gemini-TTS 요청 본문·모델 ID 재시도·비용 추정·후보 구성·실패 표시 검증.
# ffmpeg·네트워크 없이 돌도록 오디오 헬퍼와 HTTP 는 모두 가짜로 바꾼다.
import argparse
import base64
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "compare_voices", Path(__file__).resolve().parent.parent / "scripts" / "compare_voices.py"
)
cv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cv)


class _Resp:
    def __init__(self, status: int, text: str = "", audio: bytes = b"\x00\x01" * 10):
        self.status_code = status
        self.text = text
        self._audio = audio

    def json(self):
        return {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/L16;codec=pcm;rate=24000", "data": base64.b64encode(self._audio).decode()}}]}}]}


@pytest.fixture
def no_audio_tools(monkeypatch):
    """ffmpeg 없이 돌게 PCM→MP3 변환·후처리·길이 측정을 가짜로 바꾸고, 모델 ID 기억도 비운다."""
    ffmpeg_calls = []

    def fake_run(cmd, check=False):
        ffmpeg_calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"MP3")

    monkeypatch.setattr(cv.subprocess, "run", fake_run)
    monkeypatch.setattr(cv, "_deepen_voice", lambda p: p)
    monkeypatch.setattr(cv, "_duration", lambda p: 40.0)
    monkeypatch.setattr(cv, "_gemini_resolved", {})
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return ffmpeg_calls


def _args(**kw) -> argparse.Namespace:
    base = {"all": False, "voices": None, "with_qwen": False, "no_qwen": False}
    base.update(kw)
    return argparse.Namespace(**base)


def test_gemini_payload_is_generate_content_audio_request():
    body = cv.gemini_payload("수익률은 29.2%였습니다.", "Orus", "calm")
    prompt = body["contents"][0]["parts"][0]["text"]
    assert prompt.startswith("### DIRECTOR'S NOTES\ncalm")  # 연출 지시와 대본을 머리표로 나눈다
    assert "#### TRANSCRIPT\n" in prompt
    assert "이십구점이퍼센트" in prompt                      # tts.py 숫자 정규화는 그대로 적용
    assert "<speak>" not in prompt                          # SSML 아님
    cfg = body["generationConfig"]
    assert cfg["responseModalities"] == ["AUDIO"]
    assert cfg["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Orus"


def test_gemini_key_prefers_ai_studio_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "cloud")
    monkeypatch.setenv("GEMINI_API_KEY", "studio")
    assert cv._gemini_key() == "studio"
    monkeypatch.delenv("GEMINI_API_KEY")
    assert cv._gemini_key() == "cloud"
    monkeypatch.delenv("GOOGLE_TTS_API_KEY")
    with pytest.raises(cv.SynthError):
        cv._gemini_key()


def test_pcm_rate_from_mime():
    assert cv._pcm_rate("audio/L16;codec=pcm;rate=24000") == 24000
    assert cv._pcm_rate("audio/L16;rate=16000") == 16000
    assert cv._pcm_rate("") == 24000


def test_gemini_cost_uses_audio_seconds():
    # 40초 × 25토큰/초 × $9/1M
    assert cv.gemini_cost_usd(40, "flash") == pytest.approx(0.009)
    assert cv.gemini_cost_usd(40, "lite") == pytest.approx(0.006)


def test_candidates_are_well_formed():
    assert {e for _, e, _ in cv.CANDIDATES.values()} == {"cloud", "gemini", "qwen"}
    for alias in cv.DEFAULT_PICKS + cv.QWEN_PICKS:
        assert alias in cv.CANDIDATES
    for _, engine, spec in cv.CANDIDATES.values():
        if engine == "gemini":
            assert spec[0] in cv.GEMINI_MODEL_IDS and spec[0] in cv.GEMINI_OUT_PRICE
        if engine == "qwen":
            assert spec[0] in ("design", "clone", "custom")
    assert {cv.CANDIDATES[a][1] for a in cv.DEFAULT_PICKS} == {"cloud", "gemini"}


def test_sample_exercises_question_and_haeyo_endings():
    # 어미 다양화 규칙의 효과를 들어 보는 원고다 — 의문문·해요체가 빠지면 비교 의미가 줄어든다
    assert "?" in cv.SAMPLE and "죠." in cv.SAMPLE


def _model_of(url: str) -> str:
    return url.split("/models/")[1].split(":")[0]


def test_gemini_falls_back_to_next_model_id_and_remembers_it(monkeypatch, tmp_path, no_audio_tools):
    calls = []

    def post(url, params=None, json=None, timeout=None):
        calls.append(_model_of(url))
        assert url.endswith(":generateContent") and params == {"key": "k"}
        if _model_of(url).endswith("-preview"):
            return _Resp(200)
        return _Resp(404, "Model not found")

    monkeypatch.setattr(cv.requests, "post", post)
    row = cv.synth_gemini("문장입니다.", "x", ("flash", "Orus"), "s", tmp_path, 1)
    assert calls == ["gemini-3.8-flash-tts", "gemini-3.8-flash-tts-preview"]
    assert row["voice"] == "gemini-3.8-flash-tts-preview / Orus"
    assert (tmp_path / row["file"]).read_bytes() == b"MP3"
    cmd = no_audio_tools[0]                           # 머리 없는 PCM 을 16비트·24kHz·모노로 읽어 MP3 로
    assert cmd[cmd.index("-f") + 1] == "s16le" and cmd[cmd.index("-ar") + 1] == "24000"
    assert not list(tmp_path.glob("_gemini_*.pcm"))   # 중간 PCM 은 지운다
    # 같은 계열의 다음 후보는 통한 이름으로 바로 간다(헛호출 없음)
    cv.synth_gemini("문장입니다.", "y", ("flash", "Iapetus"), "s", tmp_path, 2)
    assert calls[-1] == "gemini-3.8-flash-tts-preview" and len(calls) == 3


def test_gemini_reports_all_tried_ids_when_none_work(monkeypatch, tmp_path, no_audio_tools):
    monkeypatch.setattr(cv.requests, "post", lambda *a, **k: _Resp(404, "Model not found"))
    with pytest.raises(cv.SynthError) as e:
        cv.synth_gemini("문장입니다.", "x", ("lite", "Orus"), "s", tmp_path, 1)
    msg = str(e.value)
    assert "gemini-3.8-flash-lite-tts →" in msg and "gemini-3.8-flash-lite-tts-preview →" in msg
    assert "POPORY_GEMINI_TTS_LITE" in msg          # 고치는 방법까지 보여준다


def test_gemini_permission_error_is_not_retried(monkeypatch, tmp_path, no_audio_tools):
    calls = []
    monkeypatch.setattr(cv.requests, "post",
                        lambda *a, **k: calls.append(1) or _Resp(403, "PERMISSION_DENIED"))
    with pytest.raises(cv.SynthError) as e:
        cv.synth_gemini("문장입니다.", "x", ("flash", "Orus"), "s", tmp_path, 1)
    assert len(calls) == 1                           # 이름을 바꿔도 같은 오류라 재시도하지 않는다
    assert "PERMISSION_DENIED" in str(e.value) and "GEMINI_API_KEY" in str(e.value)


def test_gemini_model_id_env_override(monkeypatch):
    monkeypatch.setenv("POPORY_GEMINI_TTS_FLASH", "gemini-x-tts")
    assert cv._model_ids("POPORY_GEMINI_TTS_FLASH", "a", "b") == ["gemini-x-tts"]
    monkeypatch.delenv("POPORY_GEMINI_TTS_FLASH")
    assert cv._model_ids("POPORY_GEMINI_TTS_FLASH", "a", "b") == ["a", "b"]


def test_qwen_missing_mlx_audio_becomes_visible_failure(monkeypatch, tmp_path):
    def no_mlx(*a, **k):
        raise ImportError("mlx_audio")

    runner = cv.QwenRunner(tmp_path)
    monkeypatch.setattr(runner, "synth", no_mlx)
    with pytest.raises(cv.SynthError) as e:
        cv.synth_qwen(runner, "문장입니다.", "x", ("design", None), tmp_path, 1)
    assert "pip install mlx-audio" in str(e.value)


def test_default_picks_include_qwen_only_when_mlx_audio_installed(monkeypatch):
    monkeypatch.setattr(cv, "mlx_audio_installed", lambda: True)
    picks, notes = cv.choose_picks(_args())
    assert picks == cv.DEFAULT_PICKS + cv.QWEN_PICKS and not notes

    monkeypatch.setattr(cv, "mlx_audio_installed", lambda: False)
    picks, notes = cv.choose_picks(_args())
    assert picks == cv.DEFAULT_PICKS
    assert any("mlx-audio" in n for n in notes)       # 왜 빠졌는지 페이지·터미널에 알린다

    picks, _ = cv.choose_picks(_args(with_qwen=True))
    assert picks[-2:] == cv.QWEN_PICKS
    picks, notes = cv.choose_picks(_args(no_qwen=True))
    assert picks == cv.DEFAULT_PICKS and any("--no-qwen" in n for n in notes)


def test_explicit_voices_without_new_engines_leave_a_note():
    picks, notes = cv.choose_picks(_args(voices="male,orus,aoede"))
    assert picks == ["male", "orus", "aoede"]
    assert any("--voices" in n for n in notes)


def test_failed_candidates_are_listed_on_the_page(monkeypatch, tmp_path, no_audio_tools):
    monkeypatch.setattr(cv.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(cv, "mlx_audio_installed", lambda: False)
    monkeypatch.setattr(cv, "synth_cloud", lambda text, label, voice, out_dir, i: {
        "label": label, "voice": voice, "file": f"{i}.mp3", "seconds": 1.0, "mode": "문장별", "cost": "1자"})

    def gemini_fail(*a, **k):
        raise cv.SynthError("gemini-3.8-flash-tts → 403 <PERMISSION_DENIED>")

    monkeypatch.setattr(cv, "synth_gemini", gemini_fail)
    monkeypatch.setattr("sys.argv", ["compare_voices.py"])
    cv.main()
    page = next(tmp_path.glob("Downloads/popory_voice_ab/*/index.html")).read_text(encoding="utf-8")
    assert "만들지 못한 후보" in page and "Gemini 3.8 Flash · Orus" in page
    assert "&lt;PERMISSION_DENIED&gt;" in page        # 오류 본문은 이스케이프해 싣는다
    assert "Gemini 3.8 TTS" in page                   # 이번 실행 엔진 표시
    assert "mlx-audio" in page                        # Qwen 이 빠진 이유


def test_qwen_only_run_does_not_need_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_TTS_API_KEY", raising=False)
    monkeypatch.setattr(cv.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(cv, "synth_qwen", lambda *a, **k: {
        "label": "q", "voice": "m", "file": "q.mp3", "seconds": 1.0, "mode": "원고 한 번에", "cost": "$0"})
    monkeypatch.setattr("sys.argv", ["compare_voices.py", "--voices", "qwen-design"])
    cv.main()
    assert list(tmp_path.glob("Downloads/popory_voice_ab/*/index.html"))
