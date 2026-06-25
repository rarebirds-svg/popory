# 한국어 문장 1:1 다국어 번역(claude CLI) 검증 — runner 스텁 주입.
from popory_content import translate
from popory_content.generate import GenerateError


def test_translate_aligns_each_language():
    def fake_runner(*, system_prompt, user_msg, parse, job_id):
        return parse('{"en":["a","b"],"zh":["甲","乙"],"ja":["あ","い"]}')
    out = translate.translate_lines(["가", "나"], runner=fake_runner)
    assert out == {"en": ["a", "b"], "zh": ["甲", "乙"], "ja": ["あ", "い"]}


def test_translate_length_mismatch_returns_none():
    # run_claude_cli는 parse 실패를 재시도 후 GenerateError로 감싼다 → None.
    def bad_runner(*, system_prompt, user_msg, parse, job_id):
        raise GenerateError("length mismatch")
    assert translate.translate_lines(["가", "나"], runner=bad_runner) is None


def test_translate_empty_returns_empty_arrays():
    assert translate.translate_lines([]) == {"en": [], "zh": [], "ja": []}


def test_parse_rejects_wrong_length():
    import pytest
    captured = {}
    def runner(*, system_prompt, user_msg, parse, job_id):
        captured["parse"] = parse
        return parse('{"en":["only-one"],"zh":["甲","乙"],"ja":["あ","い"]}')
    # en 길이 1 != 입력 2 → parse 가 ValueError
    with pytest.raises(ValueError):
        translate.translate_lines(["가", "나"], runner=runner)
