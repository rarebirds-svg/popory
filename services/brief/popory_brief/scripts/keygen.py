# 1회성: services/brief 전용 ES256 키페어를 만들어 한 파일에 저장한다.
# 사용법.
#   .venv/bin/python -m popory_brief.scripts.keygen --kid services-brief-2026-05 \
#       --out secrets/brief_signing_key.json
# 산출.
#   { "kid": "...", "public_jwk": {...}, "private_pem": "..." }
# public_jwk는 portal D1 signing_keys에 INSERT 한다.
import argparse
import json
from pathlib import Path

from jwcrypto import jwk


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--kid", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    key = jwk.JWK.generate(kty="EC", crv="P-256")
    public = json.loads(key.export_public())
    public["kid"] = args.kid
    public["alg"] = "ES256"
    public["use"] = "sig"
    private_pem = key.export_to_pem(private_key=True, password=None).decode("ascii")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "kid": args.kid,
        "public_jwk": public,
        "private_pem": private_pem,
    }, ensure_ascii=False, indent=2))
    print(json.dumps({"status": "ok", "kid": args.kid, "out": str(out_path),
                      "public_jwk": public}, ensure_ascii=False))


if __name__ == "__main__":
    main()
