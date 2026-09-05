# claude CLI 재시도·지수 백오프(일시 실패 내성) 단위 테스트.
import subprocess

import pytest

from popory_content import generate
from popory_content.generate import run_claude_cli, GenerateError


@pytest.fixture(autouse=True)
def _reset_usage_limit(monkeypatch):
    """한도 쿨다운은 모듈 전역이라 테스트 사이에 새면 뒤 테스트가 통째로 건너뛴다."""
    monkeypatch.setattr(generate, "_usage_limit_until", 0.0)


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


def test_normalizes_author_names_before_parse(harness):
    # 인명 교정은 parse 앞에 걸려야 한다 — 계약 파서가 이미 고쳐진 문자열을 본다.
    harness["install"]([(0, "보도 새퍼의 돈", "")])
    assert run_claude_cli(system_prompt="s", user_msg="u", parse=lambda x: x.strip()) == "보도 섀퍼의 돈"


def test_is_usage_limit_matches_real_message_but_not_transient_errors():
    # 2026-09-05 맥미니 실측 문구.
    assert generate.is_usage_limit("You've hit your session limit · resets 11pm (Asia/Seoul)")
    assert generate.is_usage_limit("You've hit your weekly limit")
    assert generate.is_usage_limit("Usage limit reached")
    # 재시도로 풀리는 일시 오류는 한도가 아니다(기존 백오프가 처리해야 한다).
    assert not generate.is_usage_limit("429 Too Many Requests")
    assert not generate.is_usage_limit("connection reset by peer")
    assert not generate.is_usage_limit("")


def test_usage_limit_fails_fast_without_burning_retries(harness):
    """한도는 백오프 60초로 못 넘는다 — 남은 시도를 태우지 않고 즉시 포기하고 쿨다운을 건다."""
    harness["install"]([(1, "", "You've hit your session limit · resets 11pm (Asia/Seoul)")])
    assert not generate.usage_limited()
    with pytest.raises(GenerateError) as e:
        run_claude_cli(system_prompt="s", user_msg="u", parse=lambda x: x, max_attempts=4)
    assert "사용량 한도" in str(e.value)
    assert harness["calls"]["n"] == 1      # 4회가 아니라 1회
    assert harness["sleeps"] == []
    assert generate.usage_limited()        # 이후 워커가 생성·발행을 건너뛴다


def test_usage_limited_expires_after_cooldown(monkeypatch):
    monkeypatch.setattr(generate, "USAGE_LIMIT_COOLDOWN_SECONDS", 1800)
    now = [1000.0]
    monkeypatch.setattr(generate.time, "monotonic", lambda: now[0])
    generate.note_usage_limit()
    assert generate.usage_limited()
    now[0] += 1799
    assert generate.usage_limited()
    now[0] += 2
    assert not generate.usage_limited()    # 쿨다운이 지나면 저절로 풀린다
