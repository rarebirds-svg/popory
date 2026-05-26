-- popory 포털의 핵심 도메인 테이블 초기 정의 (spec 섹션 9 + 서명 키 보관).

CREATE TABLE users (
  sub          TEXT PRIMARY KEY,
  email        TEXT NOT NULL UNIQUE,
  display_name TEXT,
  picture_url  TEXT,
  role         TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('member', 'admin')),
  blocked_at   INTEGER,
  created_at   INTEGER NOT NULL,
  last_seen_at INTEGER
);

CREATE TABLE allowed_emails (
  email      TEXT PRIMARY KEY,
  invited_by TEXT REFERENCES users(sub),
  note       TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE area_subscriptions (
  sub        TEXT NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  area       TEXT NOT NULL,
  enabled_at INTEGER NOT NULL,
  PRIMARY KEY (sub, area)
);

CREATE TABLE published_items (
  id           TEXT PRIMARY KEY,
  area         TEXT NOT NULL,
  author_sub   TEXT REFERENCES users(sub),
  title        TEXT NOT NULL,
  summary      TEXT,
  body_r2_key  TEXT,
  published_at INTEGER NOT NULL,
  tags         TEXT
);
CREATE INDEX idx_published_area_time ON published_items(area, published_at DESC);

CREATE TABLE audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_sub  TEXT,
  action     TEXT NOT NULL,
  target     TEXT,
  meta       TEXT,
  created_at INTEGER NOT NULL
);

-- 영역 진입 토큰 + 세션 JWT의 서명에 쓰는 ES256 키 페어.
-- 활성/grace 키를 함께 두어 회전 가능.
CREATE TABLE signing_keys (
  kid          TEXT PRIMARY KEY,
  alg          TEXT NOT NULL DEFAULT 'ES256',
  public_jwk   TEXT NOT NULL,
  private_jwk  TEXT NOT NULL,
  status       TEXT NOT NULL CHECK (status IN ('active', 'grace', 'retired')),
  created_at   INTEGER NOT NULL,
  retired_at   INTEGER
);
CREATE INDEX idx_signing_keys_status ON signing_keys(status);
