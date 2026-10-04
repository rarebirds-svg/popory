# compare_voices.py — Gemini-TTS 요청 본문·비용 추정·엔진별 후보 구성·Qwen 지연 로드 검증.
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "compare_voices", Path(__file__).resolve().parent.parent / "scripts" / "compare_voices.py"
)
cv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cv)


def test_gemini_payload_sends_plain_normalized_text_not_ssml():
    body = cv.gemini_payload("수익률은 29.2%였습니다.", "gemini-3.8-flash-tts", "Orus", "calm")
    assert "ssml" not in body["input"]                      # Gemini-TTS 는 SSML 을 받지 않는다
    assert body["input"]["prompt"] == "calm"
    assert "이십구점이퍼센트" in body["input"]["text"]       # tts.py 숫자 정규화는 그대로 적용
    assert body["voice"] == {"languageCode": "ko-KR", "name": "Orus", "modelName": "gemini-3.8-flash-tts"}
    assert body["audioConfig"] == {"audioEncoding": "MP3"}


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
            assert spec[0] in cv.GEMINI_MODELS and spec[0] in cv.GEMINI_OUT_PRICE
        if engine == "qwen":
            assert spec[0] in ("design", "clone", "custom")
    # 기본 목록은 키 하나로 바로 돌아가야 한다 — 맥 전용 Qwen 은 --with-qwen 일 때만
    assert all(cv.CANDIDATES[a][1] != "qwen" for a in cv.DEFAULT_PICKS)


def test_sample_exercises_question_and_haeyo_endings():
    # 어미 다양화 규칙의 효과를 들어 보는 원고다 — 의문문·해요체가 빠지면 비교 의미가 줄어든다
    assert "?" in cv.SAMPLE and "죠." in cv.SAMPLE


def test_synth_gemini_reports_error_body(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")

    class Resp:
        status_code = 404
        text = "Model gemini-3.8-flash-tts not found"

    monkeypatch.setattr(cv.requests, "post", lambda *a, **k: Resp())
    assert cv.synth_gemini("문장입니다.", "x", ("flash", "Orus"), "s", tmp_path, 1) is None
    assert "not found" in capsys.readouterr().err   # 모델명이 틀리면 env 로 고칠 수 있게 이유를 보여준다


def test_qwen_skipped_when_mlx_audio_missing(monkeypatch, tmp_path, capsys):
    def no_mlx(*a, **k):
        raise ImportError("mlx_audio")

    runner = cv.QwenRunner(tmp_path)
    monkeypatch.setattr(runner, "synth", no_mlx)
    assert cv.synth_qwen(runner, "문장입니다.", "x", ("design", None), tmp_path, 1) is None
    assert "mlx-audio" in capsys.readouterr().err


def test_qwen_only_run_does_not_need_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_TTS_API_KEY", raising=False)
    monkeypatch.setattr(cv.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(cv, "synth_qwen", lambda *a, **k: {
        "label": "q", "voice": "m", "file": "q.mp3", "seconds": 1.0, "mode": "원고 한 번에", "cost": "$0"})
    monkeypatch.setattr("sys.argv", ["compare_voices.py", "--voices", "qwen-design"])
    cv.main()
    assert list(tmp_path.glob("Downloads/popory_voice_ab/*/index.html"))
