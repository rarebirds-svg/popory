# 이미지 이상 검수(image_review)와 worker._safe_image 의 재생성 루프를 검증한다.
# 실제 claude CLI 호출은 하지 않는다 — 판정 파서·fail-open·라운드 제어가 검증 대상.
import pytest

from popory_content import image_review as ir
from popory_content import worker as w


# --- 판정 파싱 ---

def test_parse_ok():
    assert ir._parse("<image_review>ok</image_review>") == (True, "")


def test_parse_ok_with_surrounding_text():
    assert ir._parse("살펴봤습니다.\n<image_review>ok</image_review>\n")[0] is True


def test_parse_reject_with_reason():
    ok, reason = ir._parse("<image_review>reject: 눈동자 방향이 어긋남</image_review>")
    assert ok is False and "눈동자" in reason


def test_parse_reject_without_reason():
    ok, reason = ir._parse("<image_review>reject</image_review>")
    assert ok is False and reason == "사유 미기재"


@pytest.mark.parametrize("bad", ["판정 불가", "<image_review>maybe</image_review>", ""])
def test_parse_malformed_raises(bad):
    """파싱 실패는 run_claude_cli 의 재시도 대상이라 예외를 던져야 한다."""
    with pytest.raises(ir.ReviewError):
        ir._parse(bad)


# --- fail-open ---

def test_review_disabled_passes(monkeypatch):
    monkeypatch.setattr(ir, "ENABLED", False)
    assert ir.review_image(b"PNG", "j1") == (True, "")


def test_review_empty_bytes_passes():
    assert ir.review_image(b"", "j1") == (True, "")


def test_review_cli_failure_passes(monkeypatch):
    """CLI 가 죽어도 통과시켜야 한다 — 검수 실패로 배치가 멈추면 안 된다."""
    monkeypatch.setattr(ir, "ENABLED", True)
    monkeypatch.setattr(ir, "run_claude_cli", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    assert ir.review_image(b"PNG", "j1") == (True, "")


def test_review_passes_read_tool_and_temp_path(monkeypatch):
    """Read 툴을 허용해야 claude 가 이미지를 볼 수 있고, 경로가 메시지에 담겨야 한다."""
    monkeypatch.setattr(ir, "ENABLED", True)
    seen = {}

    def fake_cli(**kw):
        seen.update(kw)
        return (True, "")

    monkeypatch.setattr(ir, "run_claude_cli", fake_cli)
    ir.review_image(b"PNG", "job7")
    assert seen["allowed_tools"] == ("Read",)
    assert ".png" in seen["user_msg"] and "job7" in seen["user_msg"]


def test_review_temp_file_is_cleaned(monkeypatch, tmp_path):
    """임시 PNG 가 남으면 매일 24장씩 쌓인다."""
    monkeypatch.setattr(ir, "ENABLED", True)
    captured = {}

    def fake_cli(**kw):
        captured["path"] = kw["user_msg"].split(": ", 1)[1]
        return (True, "")

    monkeypatch.setattr(ir, "run_claude_cli", fake_cli)
    ir.review_image(b"PNG", "j1")
    import pathlib
    assert not pathlib.Path(captured["path"]).exists()


# --- 프롬프트 강화 ---

def test_harden_prompt_escalates_then_saturates():
    base = "A man reading by a window, photorealistic, cinematic"
    r0 = ir.harden_prompt(base, 0)
    r1 = ir.harden_prompt(base, 1)
    assert "behind or in silhouette" in r0
    assert "No people at all" in r1
    # 라운드가 더 늘어도 마지막 단계(인물 제거)를 유지한다
    assert ir.harden_prompt(base, 9) == r1
    assert base.rstrip(".") in r0


# --- _safe_image 재생성 루프 ---

def _stub(monkeypatch, gen_results, review_results):
    """_generate_image·review_image 를 순서대로 소비하는 스텁으로 바꾼다."""
    gens, revs, calls = list(gen_results), list(review_results), []

    def fake_gen(client, prompt, job_id="?"):
        calls.append(prompt)
        return gens.pop(0) if gens else None

    monkeypatch.setattr(w, "_generate_image", fake_gen)
    monkeypatch.setattr(w, "review_image", lambda img, job_id="?": revs.pop(0) if revs else (True, ""))
    monkeypatch.setattr(w, "append_log", lambda *a, **k: None)
    return calls


def test_safe_image_returns_first_when_review_passes(monkeypatch):
    calls = _stub(monkeypatch, [b"IMG1"], [(True, "")])
    assert w._safe_image(None, "prompt", "j1") == b"IMG1"
    assert len(calls) == 1, "검수 통과면 재생성하지 않는다"


def test_safe_image_regenerates_with_hardened_prompt_on_reject(monkeypatch):
    calls = _stub(monkeypatch, [b"BAD", b"GOOD"], [(False, "얼굴 기형"), (True, "")])
    assert w._safe_image(None, "A man reading", "j1") == b"GOOD"
    assert len(calls) == 2
    assert calls[0] == "A man reading"
    assert "silhouette" in calls[1], "재생성은 인물 위험을 낮춘 프롬프트로 해야 한다"


def test_safe_image_uses_last_image_when_all_rejected(monkeypatch):
    """끝까지 탈락해도 단색 배경(None)보다 마지막 이미지가 낫다."""
    monkeypatch.setattr(w, "IMAGE_REVIEW_ROUNDS", 2)
    calls = _stub(monkeypatch, [b"A", b"B", b"C"], [(False, "x"), (False, "y"), (False, "z")])
    assert w._safe_image(None, "p", "j1") == b"C"
    assert len(calls) == 3, "1회 생성 + 2라운드 재생성"


def test_safe_image_returns_none_when_generation_fails(monkeypatch):
    """생성 자체가 실패하면 재생성해도 소용없으니 즉시 중단한다."""
    calls = _stub(monkeypatch, [None], [])
    assert w._safe_image(None, "p", "j1") is None
    assert len(calls) == 1


def test_safe_image_rounds_zero_disables_regeneration(monkeypatch):
    monkeypatch.setattr(w, "IMAGE_REVIEW_ROUNDS", 0)
    calls = _stub(monkeypatch, [b"BAD"], [(False, "기형")])
    assert w._safe_image(None, "p", "j1") == b"BAD"
    assert len(calls) == 1, "라운드 0 이면 검수만 하고 재생성은 안 한다"
