-- instagram_connections 테이블 + content_jobs instagram 업로드 컬럼 추가

CREATE TABLE instagram_connections (
  sub          TEXT    PRIMARY KEY REFERENCES users(sub) ON DELETE CASCADE,
  ig_user_id   TEXT    NOT NULL,
  username     TEXT    NOT NULL,
  enc_token    TEXT    NOT NULL,
  connected_at INTEGER NOT NULL
);

ALTER TABLE content_jobs ADD COLUMN instagram_status   TEXT;
ALTER TABLE content_jobs ADD COLUMN instagram_media_id TEXT;
ALTER TABLE content_jobs ADD COLUMN instagram_error    TEXT;
