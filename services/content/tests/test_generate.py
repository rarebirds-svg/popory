# claude CLI 재시도·지수 백오프(일시 실패 내성) 단위 테스트.
import subprocess

import pytest

from popory_content import generate
from popory_content.generate import run_claude_cli, GenerateError


@pytest.fixture
def harness(monkeypatch):
    """claude 바이너리 존재·time.sleep·subprocess.run 을 가짜로 대체."""
    monkeypatch.setattr(generate.Path, "exists", lambda self: True)
    sleeps: list = []
    monkeypatch.setattr(generate.time, "sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def install(side_effects):
        def fake_run(cmd, **kw):
            i = calls["n"]
            calls["n"] += 1
            eff = side_effects[min(i, len(side_effects) - 1)]
            if isinstance(eff, Exception):
                raise eff
            rc, out, err = eff
            return subprocess.CompletedProcess(cmd, rc, out, err)

        monkeypatch.setattr(generate.subprocess, "run", fake_run)

    return {"install": install, "calls": calls, "sleeps": sleeps}


def test_succeeds_first_try_no_sleep(harness):
    harness["install"]([(0, "hello", "")])
    assert run_claude_cli(system_prompt="s", user_msg="u", parse=lambda x: x.strip()) == "hello"
    assert harness["calls"]["n"] == 1
    assert harness["sleeps"] == []


def test_retries_transient_nonzero_then_succeeds(harness):
    harness["install"]([(1, "", "rate limited"), (0, "ok", "")])
    assert run_claude_cli(system_prompt="s", user_msg="u", parse=lambda x: x.strip()) == "ok"
    assert harness["calls"]["n"] == 2
    assert len(harness["sleeps"]) == 1


def test_retries_on_timeout_then_succeeds(harness):
    harness["install"]([subprocess.TimeoutExpired(cmd="claude", timeout=1), (0, "ok", "")])
    assert run_claude_cli(system_prompt="s", user_msg="u", parse=lambda x: x.strip()) == "ok"
    assert harness["calls"]["n"] == 2


def test_retries_on_parse_failure_then_succeeds(harness):
    harness["install"]([(0, "data", "")])
    pc = {"n": 0}

    def parse(s):
        pc["n"] += 1
        if pc["n"] == 1:
            raise ValueError("bad parse")
        return "parsed-" + s

    assert run_claude_cli(system_prompt="s", user_msg="u", parse=parse) == "parsed-data"
    assert harness["calls"]["n"] == 2


def test_exhausts_all_attempts_raises(harness):
    harness["install"]([(1, "", "boom")])
    with pytest.raises(GenerateError):
        run_claude_cli(system_prompt="s", user_msg="u", parse=lambda x: x)
    assert harness["calls"]["n"] == generate.MAX_ATTEMPTS


def test_default_attempts_at_least_three(harness):
    # 일시 실패 내성: 단일 재시도(2)보다 많아야 한다.
    assert generate.MAX_ATTEMPTS >= 3


def test_exponential_backoff_sequence(harness, monkeypatch):
    monkeypatch.setattr(generate, "MAX_ATTEMPTS", 4)
    monkeypatch.setattr(generate, "RETRY_BACKOFF_BASE", 10)
    monkeypatch.setattr(generate, "RETRY_BACKOFF_CAP", 60)
    harness["install"]([(1, "", "always fail")])
    with pytest.raises(GenerateError):
        run_claude_cli(system_prompt="s", user_msg="u", parse=lambda x: x)
    # 4회 시도 사이 3회 백오프: 10, 20, 40 (상한 60 미만)
    assert harness["sleeps"] == [10, 20, 40]


def test_backoff_respects_cap(harness, monkeypatch):
    monkeypatch.setattr(generate, "MAX_ATTEMPTS", 6)
    monkeypatch.setattr(generate, "RETRY_BACKOFF_BASE", 10)
    monkeypatch.setattr(generate, "RETRY_BACKOFF_CAP", 60)
    harness["install"]([(1, "", "fail")])
    with pytest.raises(GenerateError):
        run_claude_cli(system_prompt="s", user_msg="u", parse=lambda x: x)
    # 10, 20, 40, 60(상한), 60(상한)
    assert harness["sleeps"] == [10, 20, 40, 60, 60]


def test_generate_youtube_post_wires_prompt_and_parser(monkeypatch):
    captured = {}

    def fake_run(*, system_prompt, user_msg, parse, job_id, model):
        captured["system_prompt"] = system_prompt
        captured["user_msg"] = user_msg
        captured["parse"] = parse
        return ("게시물 본문", {"quote_verified": False, "book": "책", "author": None})

    monkeypatch.setattr(generate, "run_claude_cli", fake_run)
    draft, meta = generate.generate_youtube_post(topic="책 - 저자", job_id="j1")
    assert draft == "게시물 본문"
    assert meta["book"] == "책"
    assert captured["parse"] is generate.parse_youtube_post
    assert "책 - 저자" in captured["user_msg"]
    assert "post_markdown" in captured["system_prompt"]
