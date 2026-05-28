# popory_brief.jwt_signer: jwcrypto 기반 ES256 자가 서명 + portal verify와 동일 형태 검증
import base64
import json
from pathlib import Path

from jwcrypto import jwk, jwt

from popory_brief.jwt_signer import sign_for_portal, KeyMaterial


def _gen_keyfile(tmp_path: Path) -> Path:
    key = jwk.JWK.generate(kty="EC", crv="P-256")
    public = json.loads(key.export_public())
    public["kid"] = "test-kid-1"
    public["alg"] = "ES256"
    public["use"] = "sig"
    private_pem = key.export_to_pem(private_key=True, password=None).decode("ascii")
    keyfile = tmp_path / "key.json"
    keyfile.write_text(json.dumps({
        "kid": "test-kid-1",
        "public_jwk": public,
        "private_pem": private_pem,
    }))
    return keyfile


def test_sign_emits_valid_es256_with_kid(tmp_path: Path):
    keyfile = _gen_keyfile(tmp_path)
    material = KeyMaterial.load(keyfile)
    token = sign_for_portal(material, area="brief", ttl_seconds=60)
    # portal verify와 동일하게 — kid로 public 찾고 검증
    public = jwk.JWK.from_json(json.dumps(material.public_jwk))
    verified = jwt.JWT(jwt=token, key=public, check_claims={
        "iss": "popory-portal",
        "aud": "popory-portal",
    })
    claims = json.loads(verified.claims)
    assert claims["sub"] == "services-brief"
    assert claims["area"] == "brief"
    assert claims["email"] == "services-brief@popory.local"
    assert "exp" in claims and "iat" in claims


def test_sign_includes_kid_in_header(tmp_path: Path):
    keyfile = _gen_keyfile(tmp_path)
    material = KeyMaterial.load(keyfile)
    token = sign_for_portal(material, area="brief")
    header_b64 = token.split(".")[0]
    # base64url decode without padding fix
    pad = "=" * (-len(header_b64) % 4)
    header = json.loads(base64.urlsafe_b64decode(header_b64 + pad))
    assert header["alg"] == "ES256"
    assert header["kid"] == "test-kid-1"


def test_keyfile_with_mismatched_kid_rejected(tmp_path: Path):
    # 키파일 top-level kid와 public_jwk.kid가 다르면 load에서 거절
    import pytest as _pytest
    key = jwk.JWK.generate(kty="EC", crv="P-256")
    public = json.loads(key.export_public())
    public["kid"] = "inner-kid"
    public["alg"] = "ES256"
    public["use"] = "sig"
    pem = key.export_to_pem(private_key=True, password=None).decode("ascii")
    keyfile = tmp_path / "key.json"
    keyfile.write_text(json.dumps({
        "kid": "top-kid",
        "public_jwk": public,
        "private_pem": pem,
    }))
    with _pytest.raises(ValueError, match="kid mismatch"):
        KeyMaterial.load(keyfile)
