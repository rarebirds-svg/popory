-- signing_keys.private_jwk를 NULLABLE로 완화한다. 외부 영역(services/brief 등)의
-- public-only 키를 dummy 빈 문자열 없이 등록할 수 있게 하기 위함이다.
-- D1은 ALTER COLUMN을 지원하지 않으므로 rename+rebuild 패턴을 쓴다.
ALTER TABLE signing_keys RENAME TO signing_keys_old;

CREATE TABLE signing_keys (
  kid          TEXT PRIMARY KEY,
  alg          TEXT NOT NULL DEFAULT 'ES256',
  public_jwk   TEXT NOT NULL,
  private_jwk  TEXT,
  status       TEXT NOT NULL CHECK (status IN ('active', 'grace', 'retired')),
  created_at   INTEGER NOT NULL,
  retired_at   INTEGER
);

INSERT INTO signing_keys (kid, alg, public_jwk, private_jwk, status, created_at, retired_at)
  SELECT kid, alg, public_jwk, private_jwk, status, created_at, retired_at FROM signing_keys_old;

DROP TABLE signing_keys_old;
CREATE INDEX idx_signing_keys_status ON signing_keys(status);
