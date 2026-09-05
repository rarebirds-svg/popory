# 대본 오탈자·고유명사 검수 — 치환 목록만 받아 보수적으로 적용하고, 검수기 실패는 fail-open.
from popory_content import script_review as sr
from popory_content.generate import GenerateError


def _scenes():
    return [
        {"caption": "범트의 청소부", "narration": "미국 범트의 작은 마을에 주유소 직원이 살았습니다. 그는 구제욱가게에서 옷을 샀죠.",
         "image_prompt": "x", "card": {"type": "quote", "text": "불은 보이지 않는다", "source": "모건 하우절"}},
        {"caption": "결론", "narration": "불을 지키는 건 태도입니다.", "image_prompt": "y"},
    ]


def test_parse_fixes_reads_tag_and_drops_noise():
    out = sr._parse_fixes('잡담 <script_fixes>[{"from":"범트","to":"버몬트","reason":"지명"},{"from":"","to":"x"},{"from":"a","to":"a"},"bad"]</script_fixes>')
    assert out == [{"from": "범트", "to": "버몬트", "reason": "지명"}]


def test_apply_fixes_touches_scenes_meta_and_cards_but_ignores_unknown_strings():
    scenes, meta = _scenes(), {"title": "범트 청소부의 비밀 — 돈의 심리학", "tags": ["범트", "돈"], "description": "범트 이야기"}
    applied = sr.apply_fixes(scenes, meta, [
        {"from": "범트", "to": "버몬트", "reason": ""},
        {"from": "구제욱가게", "to": "구제 옷가게", "reason": ""},
        {"from": "불", "to": "부", "reason": ""},          # 1글자 — 너무 짧아 버린다
        {"from": "하버드", "to": "예일", "reason": ""},     # 대본에 없음 — 무시
    ])
    assert [a["from"] for a in applied] == ["범트", "구제욱가게"]
    assert scenes[0]["caption"] == "버몬트의 청소부"
    assert "버몬트" in scenes[0]["narration"] and "구제 옷가게" in scenes[0]["narration"]
    assert meta["title"].startswith("버몬트") and meta["tags"] == ["버몬트", "돈"] and "버몬트" in meta["description"]
    assert scenes[0]["card"]["text"] == "불은 보이지 않는다"   # 1글자 치환은 적용 안 됨


def test_review_script_applies_runner_fixes(monkeypatch):
    monkeypatch.setattr(sr, "ENABLED", True)
    seen = {}

    def runner(*, system_prompt, user_msg, parse, **kw):
        seen["tools"] = kw.get("allowed_tools")
        assert "범트" in user_msg and "[장면 1 카드]" in user_msg
        return parse('<script_fixes>[{"from":"범트","to":"버몬트","reason":"지명"}]</script_fixes>')
    scenes, meta = _scenes(), {"title": "범트", "tags": []}
    result = sr.review_script(scenes, meta, job_id="j1", runner=runner)
    assert result["status"] == "ok" and result["fixes"][0]["to"] == "버몬트"
    assert scenes[0]["caption"] == "버몬트의 청소부" and meta["title"] == "버몬트"
    assert "WebSearch" in seen["tools"]   # 출판 표기 확인용


def test_review_script_fail_open(monkeypatch):
    monkeypatch.setattr(sr, "ENABLED", True)

    def boom(**kw):
        raise GenerateError("cli down")
    scenes, meta = _scenes(), {"title": "범트"}
    result = sr.review_script(scenes, meta, runner=boom)
    assert result["status"] == "unavailable" and "cli down" in result["error"]
    assert scenes[0]["caption"] == "범트의 청소부"   # 원문 보존


def test_review_script_disabled(monkeypatch):
    monkeypatch.setattr(sr, "ENABLED", False)
    assert sr.review_script(_scenes(), {}, runner=lambda **kw: 1/0)["status"] == "disabled"
