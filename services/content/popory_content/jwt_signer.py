# services/content 전용 ES256 키로 portal-호환 단명 JWT를 자가 서명한다.
# iss/aud는 F0 AreaTokenClaimsSchema 강제값(popory-portal)을 따른다.
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jwcrypto import jwk, jwt


@dataclass(frozen=True)
class KeyMaterial:
    kid: str
    public_jwk: dict[str, Any]
    private_pem: str

    @classmethod
    def load(cls, path: Path) -> "KeyMaterial":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        top_kid = data["kid"]
        inner_kid = data["public_jwk"].get("kid")
        if top_kid != inner_kid:
            raise ValueError(
                f"keyfile kid mismatch: top-level {top_kid!r} vs public_jwk.kid {inner_kid!r}"
            )
        return cls(
            kid=data["kid"],
            public_jwk=data["public_jwk"],
            private_pem=data["private_pem"],
        )


def sign_for_portal(material: KeyMaterial, *, area: str, ttl_seconds: int = 60) -> str:
    """단명 ES256 JWT 한 장 발급. portal verify가 통과하는 형태."""
    now = int(time.time())
    claims = {
        "iss": "popory-portal",
        "aud": "popory-portal",
        "sub": "services-content",
        "email": "services-content@popory.local",
        "area": area,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    key = jwk.JWK.from_pem(material.private_pem.encode("ascii"))
    token = jwt.JWT(
        header={"alg": "ES256", "kid": material.kid, "typ": "JWT"},
        claims=claims,
    )
    token.make_signed_token(key)
    return token.serialize()
