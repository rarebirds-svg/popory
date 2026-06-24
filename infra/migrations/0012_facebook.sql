-- facebook_connections 테이블 + content_jobs 페이스북 릴스 업로드 컬럼 추가

CREATE TABLE facebook_connections (
  sub          TEXT    PRIMARY KEY REFERENCES users(sub) ON DELETE CASCADE,
  page_id      TEXT    NOT NULL,
  page_name    TEXT    NOT NULL,
  enc_token    TEXT    NOT NULL,
  connected_at INTEGER NOT NULL
);

ALTER TABLE content_jobs ADD COLUMN facebook_status   TEXT;
ALTER TABLE content_jobs ADD COLUMN facebook_video_id TEXT;
ALTER TABLE content_jobs ADD COLUMN facebook_error    TEXT;
