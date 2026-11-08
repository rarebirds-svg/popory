# design_voice.py — 설계 음성 재생성 도구의 요청 본문·드라이런·생성(미리듣기·만료 출력)·목록·오류 처리 검증.
# HTTP 는 모두 가짜로 바꾼다 — 생성은 실제 요금이 들고, 테스트가 Gemini 에 닿으면 안 된다.
import base64
import importlib.util
from pathlib import Path

import pytest
import requests

from popory_content.options import VOICE

_spec = importlib.util.spec_from_file_location(
    "design_voice", Path(__file__).resolve().parent.parent / "tools" / "design_voice.py"
)
dv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dv)

KEY = "test-key-never-printed"
PERSONA = ("A calm, warm Korean man in his forties who narrates book reviews to a single listener. "
           "Natural conversational pace, gentle and trustworthy, never like a news announcer.")


class _Resp:
    def __init__(self, status: int, data=None, text: str = ""):
        self.status_code = status
        self._data = data
        self.text = text

    def json(self):
        return self._data


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)


def _no_http(monkeypatch, why: str) -> None:
    monkeypatch.setattr(dv.requests, "post", lambda *a, **k: pytest.fail(why))
    monkeypatch.setattr(dv.requests, "get", lambda *a, **k: pytest.fail(why))


def test_build_request_matches_current_voice():
    body = dv.build_request()
    v = body["voice"]
    assert body["store"] is True
    assert (v["model"], v["type"], v["gender"], v["language_code"], v["display_name"]) == (
        "gemini-3.8-flash-tts", "prompted", "male", "ko-KR", "popory-narrator-v1")
    assert v["prompted"]["input"].startswith("A calm, warm Korean man in his forties")
    assert v["prompted"]["input"] == dv.PERSONA == PERSONA   # 설계 문서의 페르소나 그대로 — 바뀌면 목소리가 바뀐다
    assert VOICE["male"].partition("/")[0] == v["model"]     # 운영 음성과 같은 모델로 만든다


def test_dry_run_sends_nothing(monkeypatch, capsys):
    _no_http(monkeypatch, "요청하면 안 된다")
    assert dv.main([]) == 0
    assert "popory-narrator-v1" in capsys.readouterr().out


def test_create_saves_preview_and_prints_expiry(monkeypatch, tmp_path, capsys, key):
    wav = b"RIFF\x24\x00\x00\x00WAVEfmt "
    sent = {}

    def post(url, **kw):
        sent.update(url=url, **kw)
        return _Resp(200, {"id": "voice_new", "expire_time": "2028-11-08T00:00:00Z",
                           "sample_audio": {"mime_type": "audio/wav", "data": base64.b64encode(wav).decode()}})

    monkeypatch.setattr(dv.requests, "post", post)
    monkeypatch.setattr(dv, "PREVIEW_DIR", tmp_path)
    assert dv.main(["--yes"]) == 0
    assert (tmp_path / "voice_new.wav").read_bytes() == wav
    out = capsys.readouterr()
    assert "voice_new" in out.out and "2028-11-08" in out.out
    assert sent["url"] == "https://generativelanguage.googleapis.com/v1beta/voices"
    assert sent["headers"] == {"x-goog-api-key": KEY} and sent["json"] == dv.build_request()
    assert KEY not in out.out + out.err                      # 키는 어디에도 찍지 않는다
    # 다음 조치 — options.py 에 그대로 붙일 두 값과 다시 잴 도구
    assert "gemini-3.8-flash-tts/voice_new" in out.out and 'datetime.date(2028, 11, 8)' in out.out
    assert "voice_ab.py" in out.out


def test_create_without_key_sends_nothing(monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    _no_http(monkeypatch, "키 없이 요청하면 안 된다")
    assert dv.main(["--yes"]) == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err


@pytest.mark.parametrize("data", [
    {"voices": [{"id": "voice_a", "display_name": "popory-narrator-v1", "expire_time": "2027-11-08T09:03:08Z"},
                {"id": "voice_b", "display_name": "other", "expire_time": "2028-01-02T00:00:00Z"}]},
    # 목록 응답의 최상위 키 이름은 확인되지 않았다 — voices 가 없으면 리스트로 보이는 값을 쓴다
    {"prompted_voices": [{"id": "voice_a", "display_name": "popory-narrator-v1", "expire_time": "2027-11-08T09:03:08Z"},
                         {"id": "voice_b", "display_name": "other", "expire_time": "2028-01-02T00:00:00Z"}],
     "next_page_token": ""},
])
def test_list_prints_one_line_per_voice(monkeypatch, capsys, key, data):
    got = {}

    def get(url, **kw):
        got.update(url=url, **kw)
        return _Resp(200, data)

    monkeypatch.setattr(dv.requests, "get", get)
    monkeypatch.setattr(dv.requests, "post", lambda *a, **k: pytest.fail("목록 조회는 음성을 만들지 않는다"))
    assert dv.main(["--list"]) == 0
    assert got["url"] == "https://generativelanguage.googleapis.com/v1beta/voices"
    assert got["params"] == {"type": "prompted", "language_code": "ko-KR"}
    assert got["headers"] == {"x-goog-api-key": KEY}
    out = capsys.readouterr()
    lines = [ln for ln in out.out.splitlines() if "voice_" in ln]
    assert len(lines) == 2
    assert all(s in lines[0] for s in ("voice_a", "popory-narrator-v1", "2027-11-08"))
    assert all(s in lines[1] for s in ("voice_b", "other", "2028-01-02"))
    assert KEY not in out.out + out.err


@pytest.mark.parametrize("args, method", [(["--yes"], "post"), (["--list"], "get")])
def test_http_error_prints_status_and_body_head(monkeypatch, capsys, key, args, method):
    body = "가" * 300 + "잘려야할꼬리"
    monkeypatch.setattr(dv.requests, method, lambda *a, **k: _Resp(403, text=body))
    assert dv.main(args) == 1
    out = capsys.readouterr()
    shown = out.out + out.err
    assert "403" in shown and "가" * 300 in shown and "잘려야할꼬리" not in shown
    assert KEY not in shown


def test_create_network_error_points_to_list(monkeypatch, capsys, key):
    def post(*a, **k):
        raise requests.ReadTimeout("read timed out")

    monkeypatch.setattr(dv.requests, "post", post)
    assert dv.main(["--yes"]) == 1
    err = capsys.readouterr().err
    assert "read timed out" in err and "--list" in err      # 서버에선 만들어졌을 수 있다 — 다시 만들기 전에 목록부터
