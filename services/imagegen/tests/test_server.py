# 서버 핸들러를 가짜 ModelManager로 검증(실모델 없이).
import json
import threading
from http.client import HTTPConnection

import pytest

from popory_imagegen.server import make_server


class FakeManager:
    loaded = True

    def generate(self, prompt, **kw):
        if not prompt:
            raise ValueError("empty")
        return b"\x89PNG-bytes-" + prompt.encode()


@pytest.fixture
def server():
    httpd = make_server(FakeManager(), host="127.0.0.1", port=0)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield port
    httpd.shutdown()


def _post(port, path, body):
    c = HTTPConnection("127.0.0.1", port)
    c.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json"})
    return c.getresponse()


def test_generate_returns_png(server):
    r = _post(server, "/generate", {"prompt": "mountain"})
    assert r.status == 200
    assert r.getheader("Content-Type") == "image/png"
    assert r.read().startswith(b"\x89PNG")


def test_generate_empty_prompt_400(server):
    r = _post(server, "/generate", {"prompt": ""})
    assert r.status == 400


def test_health_ok(server):
    c = HTTPConnection("127.0.0.1", server)
    c.request("GET", "/health")
    r = c.getresponse()
    assert r.status == 200
    body = json.loads(r.read())
    assert body["loaded"] is True
