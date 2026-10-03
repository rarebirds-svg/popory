# 어드민 TTS 화면용 스냅샷 — 라이브 모듈 값을 반영하고, 화면과의 키 계약·비밀 비노출을 지킨다.
import json

import pytest

from popory_content import names, options, pronunciation, tts, tts_config, video


@pytest.fixture(autouse=True)
def _no_git_network(monkeypatch):
    """build_tts_config 는 runtime_snapshot 으로 git ls-remote(네트워크)를 부른다 — 단위 테스트가 원격에 기대면 느리고 불안정하다."""
    monkeypatch.setattr(tts_config.runtime_info, "runtime_snapshot",
                        lambda: {"loaded_commit": "abc1234", "head_commit": "abc1234", "branch": "main", "started_at": 1,
                                 "loaded_subject": "x", "pulled_not_restarted": False,
                                 "behind": {"state": "up_to_date", "count": 0}})


def test_snapshot_carries_the_worker_runtime_version():
    c = tts_config.build_tts_config()
    assert c["runtime"]["loaded_commit"] == "abc1234" and c["runtime"]["behind"]["state"] == "up_to_date"


def test_snapshot_reflects_live_module_values(monkeypatch):
    monkeypatch.setattr(tts, "SPEAKING_RATE", 1.06)
    monkeypatch.setattr(tts, "COMMA_BREAK_MS", 250)
    monkeypatch.setattr(video, "QUESTION_GAP", 1.5)
    monkeypatch.setenv("POPORY_TTS_SPEAKING_RATE", "1.06")
    c = tts_config.build_tts_config()
    assert c["speed"]["speaking_rate"]["current"] == 1.06
    assert c["speed"]["speaking_rate"]["overridden"] is True       # 기본 1.0 과 다르다
    assert c["pauses"]["comma_break_ms"]["current"] == 250
    assert c["pauses"]["question_gap_s"]["current"] == 1.5
    assert c["pauses"]["sentence_gap_s"]["current"] == video.SENTENCE_GAP
    assert c["pauses"]["chapter_gap_s"]["current"] == video.CHAPTER_GAP


def test_voices_defaults_and_lengths_come_from_options():
    c = tts_config.build_tts_config()
    assert {v["key"]: v["name"] for v in c["voices"]} == options.VOICE
    assert {v["key"]: v["family"] for v in c["voices"]}["male"] == "Neural2"
    assert {v["key"]: v["family"] for v in c["voices"]}["female-calm"] == "Chirp3-HD"
    assert c["defaults"]["longform"]["voice"] == options.DEFAULTS["voice"]
    assert "upload_targets" not in c["defaults"]["shorts"]            # TTS 와 무관한 값은 싣지 않는다
    assert {x["seconds"] for x in c["lengths"]["shorts"]} == set(options.SHORT_SCENE_COUNT)


def test_normalization_examples_are_computed_not_hand_written():
    """예시 결과는 실제 spoken_text 출력이어야 한다 — 규칙을 고치면 화면이 같이 바뀌어야 문서가 안 썩는다."""
    c = tts_config.build_tts_config()
    assert c["normalization"], "예시가 비면 화면에 규칙 표가 없다"
    for row in c["normalization"]:
        assert row["spoken"] == tts.spoken_text(row["input"])
        assert row["spoken"].strip()
    by = {r["label"]: r["spoken"] for r in c["normalization"]}
    assert "이십구점이" in by["소수 → 붙인 한글"]
    assert "천칠백" in by["천 단위 콤마 제거 + 한자어 수사"]
    assert "퍼센트" in by["퍼센트 기호 → '퍼센트'"]


def test_name_fixes_mirror_names_module_and_dictionary_mirrors_pronunciation_module():
    c = tts_config.build_tts_config()
    assert {f["wrong"]: f["right"] for f in c["name_fixes"]} == names._NAME_FIXES
    d = c["pronunciation_dictionary"]
    assert d["exists"] is True
    assert {e["term"]: e["reading"] for e in d["entries"]} == pronunciation.PRONUNCIATIONS
    assert {e["term"] for e in d["entries"] if e["ignore_case"]} == pronunciation.IGNORE_CASE


def test_api_key_is_never_included(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "AIza-SECRET-VALUE")
    c = tts_config.build_tts_config()
    assert c["engine"]["api_key_set"] is True
    assert "AIza-SECRET-VALUE" not in json.dumps(c, ensure_ascii=False)


def test_snapshot_is_small_json_serialisable():
    raw = json.dumps(tts_config.build_tts_config(), ensure_ascii=False)
    assert len(raw.encode()) < 16 * 1024     # API 의 수용 한도(20KB) 안쪽
