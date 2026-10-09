# 자막-음성 싱크 점검 — 발화 시작 찾기, cue 와의 어긋남, 요약(밀림 포함), 나쁜 결과 기록.
import math
from array import array

from popory_content import sync_check as sc
from popory_content import worker


def _speech(parts, rate=8000):
    """(시작 초, 길이 초) 구간에만 소리가 있는 PCM."""
    total = max(st + ln for st, ln in parts) + 0.5
    a = array("h", [0] * int(total * rate))
    for st, ln in parts:
        for t in range(int(st * rate), int((st + ln) * rate)):
            a[t] = int(6000 * math.sin(2 * math.pi * 200 * t / rate))
    return a.tobytes()


def test_onsets_find_speech_after_silence_including_the_first():
    pcm = _speech([(0.0, 1.0), (1.5, 0.8), (2.4, 0.5)])     # 마지막은 100ms 쉼 뒤라 새 발화가 아니다
    got = sc.onsets(pcm)
    assert [round(x, 2) for x in got] == [0.0, 1.5]


def test_compare_measures_signed_deviation_and_skips_far_cues():
    devs = sc.compare([0.0, 1.45, 10.0], [0.0, 1.5])
    assert devs[0] == 0.0 and round(devs[1], 2) == 0.05 and devs[2] is None


def test_summarize_reports_drift_when_audio_falls_behind():
    devs = [0.0, 0.01, 0.0, 0.1, 0.2, 0.3, 0.4, 0.45]      # 뒤로 갈수록 소리가 늦어진다
    s = sc.summarize(devs)
    assert s["judged"] and s["drift_ms"] >= 400 and s["max_ms"] == 450 and s["bad"] == 2
    assert sc.summarize([None, 0.1])["judged"] is False


def test_bad_sync_is_logged_for_admin_errors(monkeypatch):
    logged = []
    monkeypatch.setattr(worker, "append_log", lambda d, rec: logged.append(rec))
    worker._log_sync("j1", {"tts": {"sync": {"judged": True, "median_ms": 200, "p95_ms": 480, "max_ms": 600,
                                             "drift_ms": 450, "bad": 9, "matched": 120}}})
    worker._log_sync("j2", {"tts": {"sync": {"judged": True, "median_ms": 5, "p95_ms": 20, "max_ms": 40,
                                             "drift_ms": 0, "bad": 0, "matched": 120}}})
    worker._log_sync("j3", {"tts": {}})
    assert [r["job"] for r in logged] == ["j1"] and logged[0]["status"] == "sync_check_failed"
    assert "밀림 450ms" in logged[0]["error"]
