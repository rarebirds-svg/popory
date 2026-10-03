# 롱폼 첫 장면 프리후크 검수 — 판정 파싱, 교체 문장 검증, 적용 범위, fail-open 을 고정한다.
import json

import pytest

from popory_content import hook_check as hc
from popory_content import video
from popory_content.generate import GenerateError


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setattr(hc, "ENABLED", True)


def _verdict(**kw):
    base = {"pass": False, "kind": "intro_person", "reason": "인물 소개로 시작", "replace_count": 2,
            "rewrite": ["죽음을 생각하던 한 남자가 몇 년 뒤 수천만 독자의 스승이 됐습니다.", "그를 바꾼 건 단 한 번의 깨달음이었죠."]}
    base.update(kw)
    return f"잡담 <hook_verdict>{json.dumps(base, ensure_ascii=False)}</hook_verdict>"


def _runner(stdout=None, error=None):
    calls = []

    def run(*, system_prompt, user_msg, parse, **kw):
        calls.append({"system_prompt": system_prompt, "user_msg": user_msg, **kw})
        if error:
            raise error
        try:
            return parse(stdout)
        except (ValueError, json.JSONDecodeError) as e:     # run_claude_cli 는 파싱 실패를 재시도 끝에 GenerateError 로 바꾼다
            raise GenerateError(f"parse: {e}") from e
    run.calls = calls
    return run


def _scenes():
    return [
        {"caption": "죽음의 문턱", "image_prompt": "x",
         "narration": "서른을 앞둔 어느 날, 죽음을 생각하던 한 남자가 있었습니다. 몇 년 뒤 그는 전 세계 수천만 독자의 마음을 바꾼 영적 스승이 되어 있었죠. 그의 이름은 에크하르트 톨레입니다."},
        {"caption": "깨달음", "image_prompt": "y", "narration": "그날 밤 그는 단 한 번의 깨달음을 얻었습니다. 3년 동안 공원 벤치에서 살았습니다."},
    ]


META = {"title": "죽음을 생각한 남자의 반전 — 지금 이 순간의 힘", "description": "요약"}


def test_parse_verdict_reads_tag_and_defaults():
    v = hc._parse_verdict(_verdict())
    assert v["pass"] is False and v["kind"] == "intro_person" and len(v["rewrite"]) == 2 and v["replace_count"] == 2
    v = hc._parse_verdict('<hook_verdict>{"pass": true}</hook_verdict>')
    assert v == {"pass": True, "kind": "none", "reason": "", "replace_count": 2, "rewrite": []}


@pytest.mark.parametrize("bad", ["태그 없음", '<hook_verdict>{"kind":"x"}</hook_verdict>',
                                 '<hook_verdict>{"pass": "yes"}</hook_verdict>',
                                 '<hook_verdict>{"pass": false, "rewrite": "문장"}</hook_verdict>'])
def test_parse_verdict_rejects_malformed(bad):
    with pytest.raises(ValueError):
        hc._parse_verdict(bad)


def test_pass_leaves_script_untouched():
    scenes = _scenes()
    before = scenes[0]["narration"]
    out = hc.check_hook(scenes, META, split=video._split_sentences, runner=_runner(
        '<hook_verdict>{"pass": true, "kind": "none", "reason": "결과로 시작"}</hook_verdict>'))
    assert out["status"] == "passed" and scenes[0]["narration"] == before
    assert len(out["before"]) == 3


def test_violation_rewrites_only_the_leading_sentences_and_keeps_the_rest():
    scenes = _scenes()
    out = hc.check_hook(scenes, META, split=video._split_sentences, runner=_runner(_verdict()))
    assert out["status"] == "rewritten" and out["kind"] == "intro_person"
    new = scenes[0]["narration"]
    assert new.startswith("죽음을 생각하던 한 남자가 몇 년 뒤 수천만 독자의 스승이 됐습니다.")
    assert new.endswith("그의 이름은 에크하르트 톨레입니다.")          # 셋째 문장은 그대로
    assert "한 남자가 있었습니다" not in new
    assert scenes[1]["narration"].startswith("그날 밤")                  # 다른 장면은 건드리지 않는다
    assert out["after"][0].startswith("죽음을 생각하던") and out["before"][0].startswith("서른을 앞둔")


def test_replace_count_one_keeps_second_sentence():
    scenes = _scenes()
    out = hc.check_hook(scenes, META, split=video._split_sentences, runner=_runner(
        _verdict(replace_count=1, rewrite=["죽음을 생각하던 남자가 수천만 독자의 스승이 됐습니다."])))
    assert out["status"] == "rewritten"
    assert "영적 스승이 되어 있었죠." in scenes[0]["narration"]          # 원문 둘째 문장 유지


@pytest.mark.parametrize("rewrite,count,why", [
    ([], 2, "비어"),
    (["그는 3000만 명의 스승이 됐습니다.", "또 다른 문장입니다."], 2, "숫자"),                 # 대본에 없는 숫자
    (["왜 그는 죽음을 생각했을까요?", "이유가 있었습니다."], 2, "질문"),
    (["안녕하세요, 오늘은 한 남자의 이야기를 해 보겠습니다.", "시작합니다."], 2, "인사"),
    (["가" * 90 + "입니다.", "둘째입니다."], 2, "길이"),
    (["죽음을 생각하던 남자가 스승이 됐습니다."], 9, "범위"),                                  # replace_count 가 문장 수 밖
    (["서른을 앞둔 어느 날, 죽음을 생각하던 한 남자가 있었습니다.", "몇 년 뒤 그는 전 세계 수천만 독자의 마음을 바꾼 영적 스승이 되어 있었죠."], 2, "같음"),
])
def test_invalid_rewrites_are_rejected_and_script_is_kept(rewrite, count, why):
    scenes = _scenes()
    before = scenes[0]["narration"]
    out = hc.check_hook(scenes, META, split=video._split_sentences,
                        runner=_runner(_verdict(rewrite=rewrite, replace_count=count)))
    assert out["status"] == "rejected", why
    assert scenes[0]["narration"] == before
    assert out["rejected_because"]


def test_numbers_already_in_the_script_are_allowed():
    scenes = _scenes()
    out = hc.check_hook(scenes, META, split=video._split_sentences, runner=_runner(
        _verdict(rewrite=["그는 공원 벤치에서 3년을 살았고, 수천만 독자의 스승이 됐습니다.", "시작은 단 한 번의 깨달음이었죠."])))
    assert out["status"] == "rewritten"             # '3' 은 장면 2 에 있다


def test_runner_failure_is_fail_open():
    scenes = _scenes()
    before = scenes[0]["narration"]
    out = hc.check_hook(scenes, META, split=video._split_sentences,
                        runner=_runner(error=GenerateError("claude CLI 사용량 한도")))
    assert out["status"] == "unavailable" and "사용량 한도" in out["error"]
    assert scenes[0]["narration"] == before


def test_unparsable_answer_is_unavailable_not_a_crash():
    out = hc.check_hook(_scenes(), META, split=video._split_sentences, runner=_runner("판정 못 하겠음"))
    assert out["status"] == "unavailable"


def test_disabled_and_empty_scene(monkeypatch):
    monkeypatch.setattr(hc, "ENABLED", False)
    assert hc.check_hook(_scenes(), META, split=video._split_sentences, runner=lambda **k: 1 / 0)["status"] == "disabled"
    monkeypatch.setattr(hc, "ENABLED", True)
    assert hc.check_hook([], META, split=video._split_sentences, runner=lambda **k: 1 / 0)["status"] == "skipped"
    assert hc.check_hook([{"caption": "a", "narration": "  "}], META, split=video._split_sentences,
                         runner=lambda **k: 1 / 0)["status"] == "skipped"


def test_judge_sees_first_scene_sentences_and_whole_script_without_tools():
    r = _runner(_verdict())
    hc.check_hook(_scenes(), META, split=video._split_sentences, runner=r)
    call = r.calls[0]
    assert "1. 서른을 앞둔 어느 날" in call["user_msg"]
    assert "(장면 2 · 깨달음)" in call["user_msg"]                  # 결과를 가져올 뒷부분 대본
    assert call["allowed_tools"] == ()                             # 판정에 웹 검색은 필요 없다
    assert "intro_person" in call["system_prompt"] and "질문" in call["system_prompt"]


def test_make_video_checks_hook_for_longform_only_and_before_script_review(monkeypatch):
    order = []
    scenes = [{"caption": "a", "narration": "첫 문장입니다.", "image_prompt": "x"}]
    monkeypatch.setattr(video, "generate_scenes", lambda **kw: (scenes, {"title": "t"}))
    monkeypatch.setattr(video, "check_hook", lambda sc, meta, **kw: order.append("hook") or {"status": "passed"})
    monkeypatch.setattr(video, "review_script", lambda sc, meta, **kw: order.append("review") or {"status": "ok"})
    monkeypatch.setattr(video, "render_video", lambda sc, **kw: (None, 0, 1, []))
    _, _, meta, *_ = video.make_video(topic="t", sources=[], style_samples=[], job_id="j")
    assert order == ["hook", "review"] and meta["hook_check"]["status"] == "passed"
    order.clear()
    _, _, meta, *_ = video.make_video(topic="t", sources=[], style_samples=[], job_id="j", portrait=True)
    assert order == ["review"] and "hook_check" not in meta        # 쇼츠는 대상이 아니다
