# ModelManager의 lazy-load·직렬화·유휴 언로드를 가짜 pipe로 검증.
from popory_imagegen.model import ModelManager


class FakePipe:
    def __init__(self):
        self.gen_calls = 0
        self.closed = False

    def generate(self, prompt, **kw):
        self.gen_calls += 1
        return b"PNG:" + prompt.encode()

    def close(self):
        self.closed = True


def make_manager(idle=600):
    state = {"loads": 0, "now": 1000.0, "pipe": None}

    def loader():
        state["loads"] += 1
        p = FakePipe()
        state["pipe"] = p
        return p

    mgr = ModelManager(loader=loader, idle_seconds=idle, clock=lambda: state["now"])
    return mgr, state


def test_lazy_loads_once_and_generates():
    mgr, state = make_manager()
    assert state["loads"] == 0
    assert mgr.generate("a") == b"PNG:a"
    assert mgr.generate("b") == b"PNG:b"
    assert state["loads"] == 1


def test_idle_unload_after_timeout():
    mgr, state = make_manager(idle=600)
    mgr.generate("a")
    pipe = state["pipe"]
    state["now"] = 1000.0 + 599
    mgr.maybe_unload()
    assert pipe.closed is False
    state["now"] = 1000.0 + 600
    mgr.maybe_unload()
    assert pipe.closed is True


def test_reload_after_unload():
    mgr, state = make_manager(idle=10)
    mgr.generate("a")
    state["now"] += 10
    mgr.maybe_unload()
    state["now"] += 1
    mgr.generate("c")
    assert state["loads"] == 2


def test_maybe_unload_when_not_loaded_is_noop():
    mgr, state = make_manager()
    mgr.maybe_unload()
    assert state["loads"] == 0


# --- guidance / negative_prompt 실효성 ---

def test_negative_active_only_above_one():
    """diffusers 는 guidance_scale > 1 에서만 CFG 를 켠다 — 0.0 이면 NEGATIVE_DEFAULT 가 무효다."""
    from popory_imagegen.model import negative_active
    assert negative_active(0.0) is False
    assert negative_active(1.0) is False
    assert negative_active(1.5) is True


def test_guidance_reads_env(monkeypatch):
    import importlib
    from popory_imagegen import model as m
    monkeypatch.setenv("POPORY_IMAGEGEN_GUIDANCE", "1.8")
    importlib.reload(m)
    try:
        assert m.GUIDANCE == 1.8
        assert m.negative_active(m.GUIDANCE) is True
    finally:
        monkeypatch.delenv("POPORY_IMAGEGEN_GUIDANCE")
        importlib.reload(m)
