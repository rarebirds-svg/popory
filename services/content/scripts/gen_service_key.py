# ES256 서비스 키 1회 생성 — keyfile(JSON) 저장 + D1 등록용 public_jwk 출력.
import json
import sys
from datetime import date
from pathlib import Path

from jwcrypto import jwk


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("secrets/content_service_key.json")
    kid = f"services-content-{date.today().isoformat()}"
    key = jwk.JWK.generate(kty="EC", crv="P-256")
    public_jwk = json.loads(key.export_public())
    public_jwk.update({"kid": kid, "alg": "ES256", "use": "sig"})
    private_pem = key.export_to_pem(private_key=True, password=None).decode("ascii")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"kid": kid, "public_jwk": public_jwk, "private_pem": private_pem}, ensure_ascii=False, indent=2), encoding="utf-8")
    out.chmod(0o600)
    print(f"keyfile: {out}")
    print("아래 public_jwk 를 portal D1 signing_keys 에 status='grace' 로 INSERT 하세요.")
    print(json.dumps(public_jwk, ensure_ascii=False))


if __name__ == "__main__":
    main()
