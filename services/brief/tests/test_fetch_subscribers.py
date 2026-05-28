# fetch_subscribers.py: portal에 service-auth GET → stdout JSON
import json
import sys
from pathlib import Path

import responses

BRIEF_DIR = Path(__file__).resolve().parent.parent


def _make_key_env(tmp_path: Path) -> dict[str, str]:
    # 테스트용 키페어를 만들고 환경변수로 fetch_subscribers에 주입
    from jwcrypto import jwk
    key = jwk.JWK.generate(kty="EC", crv="P-256")
    public = json.loads(key.export_public())
    public["kid"] = "test-kid"; public["alg"] = "ES256"; public["use"] = "sig"
    pem = key.export_to_pem(private_key=True, password=None).decode("ascii")
    keyfile = tmp_path / "key.json"
    keyfile.write_text(json.dumps({"kid": "test-kid", "public_jwk": public, "private_pem": pem}))
    return {
        "POPORY_BRIEF_KEY_FILE": str(keyfile),
        "POPORY_PORTAL_API_BASE": "https://api.popory.test",
    }


@responses.activate
def test_cli_prints_subscribers_json(tmp_path: Path, monkeypatch):
    responses.add(
        responses.GET,
        "https://api.popory.test/api/areas/brief/subscribers",
        json={"subscribers": [{"email": "a@x", "display_name": "A"}]},
        status=200,
    )
    env = _make_key_env(tmp_path)
    monkeypatch.setenv("POPORY_BRIEF_KEY_FILE", env["POPORY_BRIEF_KEY_FILE"])
    monkeypatch.setenv("POPORY_PORTAL_API_BASE", env["POPORY_PORTAL_API_BASE"])

    sys.path.insert(0, str(BRIEF_DIR))
    from importlib import reload
    import fetch_subscribers
    reload(fetch_subscribers)

    out = fetch_subscribers.fetch(area="brief")
    assert out == {"subscribers": [{"email": "a@x", "display_name": "A"}]}
