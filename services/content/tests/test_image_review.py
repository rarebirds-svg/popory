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

def test_review_disabled_passes_but_marks_unavailable(monkeypatch):
    monkeypatch.setattr(ir, "ENABLED", False)
    ok, reason = ir.review_image(b"PNG", "j1")
    assert ok is True and ir.is_unavailable(reason)


def test_review_empty_bytes_passes_but_marks_unavailable():
    ok, reason = ir.review_image(b"", "j1")
    assert ok is True and ir.is_unavailable(reason)


def test_review_cli_failure_passes_but_marks_unavailable(monkeypatch):
    """CLI 가 죽어도 통과시키되(fail-open), 판정을 못 했다는 사실은 남겨야 한다 —
    구분이 없으면 인증 만료된 날 전량이 조용히 통과하는데 아무도 모른다."""
    monkeypatch.setattr(ir, "ENABLED", True)
    monkeypatch.setattr(ir, "run_claude_cli", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    ok, reason = ir.review_image(b"PNG", "j1")
    assert ok is True
    assert ir.is_unavailable(reason) and "boom" in reason


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
    assert calls[0].startswith("A man reading")
    assert ir.SAFE_PEOPLE_SUFFIX in calls[0], "0라운드부터 인물 정책이 붙는다"
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


def test_normal_verdicts_are_not_marked_unavailable():
    """정상 판정과 fail-open 이 섞이면 집계가 무의미해진다."""
    assert not ir.is_unavailable("")
    assert not ir.is_unavailable("얼굴 기형")
    assert ir.is_unavailable(f"{ir.UNAVAILABLE_PREFIX}: RuntimeError: boom")


def test_worker_logs_when_review_unavailable(monkeypatch):
    """검수를 못 한 통과는 image_review_error 로 드러나야 한다."""
    logged = []
    monkeypatch.setattr(w, "_generate_image", lambda c, p, job_id="?": b"IMG")
    monkeypatch.setattr(w, "review_image",
                        lambda img, job_id="?": (True, f"{ir.UNAVAILABLE_PREFIX}: 죽음"))
    monkeypatch.setattr(w, "append_log", lambda d, rec: logged.append(rec))
    assert w._safe_image(None, "p", "j1") == b"IMG"
    assert any(r.get("status") == "image_review_error" for r in logged)


def test_worker_does_not_log_error_on_normal_pass(monkeypatch):
    logged = []
    monkeypatch.setattr(w, "_generate_image", lambda c, p, job_id="?": b"IMG")
    monkeypatch.setattr(w, "review_image", lambda img, job_id="?": (True, ""))
    monkeypatch.setattr(w, "append_log", lambda d, rec: logged.append(rec))
    w._safe_image(None, "p", "j1")
    assert not any(r.get("status") == "image_review_error" for r in logged)


# --- 판정 기준(SYSTEM_PROMPT) ---
# 실제로 통과해버린 두 장을 기준 삼아 회귀를 막는다.
#  - 머리 없는 몸통 + 피부톤 튀는 손 (팔짱 포즈)
#  - 두 팔이 한 소매로 융합 + 한쪽 손 소실 (턱 괴기 포즈)
# 둘 다 얼굴은 멀쩡해서, 얼굴·눈 위주 기준으로는 걸리지 않았다.

def test_system_prompt_traces_limbs_not_gestalt():
    """게슈탈트 판정이 아니라 어깨→손 사슬을 적게 강제해야 한다."""
    p = ir.SYSTEM_PROMPT
    assert "어깨 → 상완 → 팔꿈치 → 전완 → 손목 → 손" in p
    assert "모든 인물" in p


def test_system_prompt_rejects_missing_and_fused_parts():
    p = ir.SYSTEM_PROMPT
    assert "[결손]" in p and "[융합·분기]" in p
    # 프레임 밖 크롭과 구분하는 기준이 있어야 과잉 차단이 안 난다
    assert "프레임 밖으로 잘린 것과 구분" in p
    # 머리 없는 몸통이 "얼굴 안 보이는 인물"로 새지 않게 못 박는다
    assert "머리 자체가 없는 몸통은 여기 해당하지 않습니다" in p
    # 애매하면 ok 의 예외
    assert "결손·융합은 예외" in p


def test_system_prompt_covers_skin_tone_and_ignores_text():
    p = ir.SYSTEM_PROMPT
    assert "[색·재질]" in p
    assert "글자가 뭉개진 것은 ok" in p


def test_retry_hint_bans_folded_arm_poses():
    """재생성 힌트가 팔짱·턱 괴기를 명시적으로 막아야 한다."""
    r0 = ir.harden_prompt("A woman at a desk", 0)
    assert "no crossed arms" in r0
    assert "no chin resting on a hand" in r0


# --- 생성 프롬프트 인물 정책 ---

@pytest.mark.parametrize("prompt", [
    "A man reading by a window",
    "Two students at a desk",
    "A quiet cafe with people talking",
    "Her hands on an open book",
])
def test_person_prompts_get_safe_composition(prompt):
    """사람을 지우면 장면이 죽으므로 대신 실패 표면(크고 선명한 인체)을 없앤다."""
    out = ir.apply_people_policy(prompt)
    assert ir.SAFE_PEOPLE_SUFFIX in out
    assert ir.NO_PEOPLE_SUFFIX not in out
    assert "out of focus" in out and "no visible hands" in out


@pytest.mark.parametrize("prompt", [
    "An empty library at dusk, warm lamplight",
    "A worn paperback on a wooden table",
    "Rain on a window, blurred street lights",
])
def test_peopleless_prompts_get_no_people(prompt):
    """모델이 멋대로 인물을 그려 넣는 걸 막는다 — 사람이 없으면 기형도 없다."""
    out = ir.apply_people_policy(prompt)
    assert ir.NO_PEOPLE_SUFFIX in out
    assert ir.SAFE_PEOPLE_SUFFIX not in out


def test_people_policy_keeps_original_prompt():
    out = ir.apply_people_policy("A worn paperback on a table.")
    assert out.startswith("A worn paperback on a table.")


def test_people_policy_never_stacks_both_suffixes():
    """두 접미사가 겹치면 '이렇게 그려라'와 '빼라'가 한 프롬프트에서 충돌한다."""
    for prompt in ("A man reading", "An empty room"):
        out = ir.apply_people_policy(prompt)
        assert (ir.SAFE_PEOPLE_SUFFIX in out) != (ir.NO_PEOPLE_SUFFIX in out)


def test_safe_image_does_not_stack_policy_on_retry(monkeypatch):
    """재생성 라운드엔 harden_prompt 만 붙는다 — 정책과 겹치면 지시가 모순된다."""
    calls = _stub(monkeypatch, [b"A", b"B"], [(False, "기형"), (True, "")])
    w._safe_image(None, "A man reading", "j1")
    assert ir.SAFE_PEOPLE_SUFFIX not in calls[1]
    assert ir.NO_PEOPLE_SUFFIX not in calls[1]


# --- has_person 단어 경계 ---
# 부분일치로 짜면 "the "⊃"he ", "this "⊃"his ", "many"⊃"man" 이라 사실상 전량이
# 사람 있음으로 분류되고 "사람 그리지 마라" 분기가 통째로 죽는다. 회귀를 고정한다.

@pytest.mark.parametrize("prompt", [
    "A worn paperback on the table",
    "Rain on the window, blurred lights",
    "A quiet room in this old house",
    "A manuscript and many letters",
    "A wooden surface under warm light",
    "Sunlight over the other shelf",
    "A German edition bound in leather",
])
def test_has_person_false_on_lookalike_words(prompt):
    assert ir.has_person(prompt) is False, f"오탐: {prompt}"


@pytest.mark.parametrize("prompt", [
    "A man reading by a window",
    "Two students at a desk",
    "Her hands on an open book",
    "A crowd on the street",
    "People talking in a cafe",
    "A child near the shelf",
    "Readers waiting in line",
])
def test_has_person_true_on_real_people(prompt):
    assert ir.has_person(prompt) is True, f"미탐: {prompt}"
