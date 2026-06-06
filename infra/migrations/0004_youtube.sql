-- 가족 구성원의 YouTube 채널 연결(암호화된 refresh token) 저장.

CREATE TABLE youtube_connections (
  sub           TEXT PRIMARY KEY REFERENCES users(sub) ON DELETE CASCADE,
  channel_id    TEXT,
  channel_title TEXT,
  refresh_token TEXT NOT NULL,
  connected_at  INTEGER NOT NULL
);
