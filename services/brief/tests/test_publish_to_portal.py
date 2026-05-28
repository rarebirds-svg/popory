# publish_to_portal: meta.json + body.md를 portal POST 페이로드로 매핑
import json
import sys
from pathlib import Path

import responses

BRIEF_DIR = Path(__file__).resolve().parent.parent


def _setup_env(monkeypatch, tmp_path: Path):
    from jwcrypto import jwk
    key = jwk.JWK.generate(kty="EC", crv="P-256")
    pub = json.loads(key.export_public())
    pub["kid"] = "test-kid"; pub["alg"] = "ES256"; pub["use"] = "sig"
    pem = key.export_to_pem(private_key=True, password=None).decode("ascii")
    keyfile = tmp_path / "key.json"
    keyfile.write_text(json.dumps({"kid": "test-kid", "public_jwk": pub, "private_pem": pem}))
    monkeypatch.setenv("POPORY_BRIEF_KEY_FILE", str(keyfile))
    monkeypatch.setenv("POPORY_PORTAL_API_BASE", "https://api.popory.test")


@responses.activate
def test_publish_maps_meta_and_body(monkeypatch, tmp_path: Path):
    _setup_env(monkeypatch, tmp_path)
    body_path = tmp_path / "body.md"
    body_path.write_text("# skip\n\n안녕\n", encoding="utf-8")
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(json.dumps({
        "title": "오늘", "summary": "요약",
        "tags": ["t1", "t2"], "published_at": 1748400000,
    }), encoding="utf-8")

    captured = {}
    def _capture(request):
        captured["json"] = json.loads(request.body)
        return (201, {}, json.dumps({"id": "01HXY"}))

    responses.add_callback(
        responses.POST,
        "https://api.popory.test/api/published_items",
        callback=_capture,
        content_type="application/json",
    )

    sys.path.insert(0, str(BRIEF_DIR))
    from importlib import reload
    import publish_to_portal
    reload(publish_to_portal)

    result = publish_to_portal.publish(area="brief", meta_file=meta_path, body_file=body_path)
    assert result == {"id": "01HXY"}
    sent = captured["json"]
    assert sent["area"] == "brief"
    assert sent["title"] == "오늘"
    assert sent["summary"] == "요약"
    assert sent["tags"] == ["t1", "t2"]
    assert sent["published_at"] == 1748400000
    assert sent["body"].startswith("# skip")
