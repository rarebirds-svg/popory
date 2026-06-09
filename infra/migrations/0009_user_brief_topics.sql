-- 사용자별 커스텀 브리핑 주제 테이블
CREATE TABLE user_brief_topics (
  id         TEXT    PRIMARY KEY,
  sub        TEXT    NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  name       TEXT    NOT NULL,
  slug       TEXT    NOT NULL UNIQUE,
  enabled    INTEGER NOT NULL DEFAULT 1,
  pending_at INTEGER,
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_user_brief_topics_sub ON user_brief_topics(sub);
