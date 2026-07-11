-- 유튜브 시청자 댓글과 답글 초안·승인 상태를 담는 테이블.
CREATE TABLE youtube_comments (
  id TEXT PRIMARY KEY,
  comment_id TEXT NOT NULL UNIQUE,
  category_id TEXT NOT NULL,
  video_id TEXT NOT NULL,
  author_name TEXT,
  text TEXT NOT NULL,
  published_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('pending','posted','dismissed','failed')),
  draft_reply TEXT,
  reply_id TEXT,
  error TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX idx_youtube_comments_status ON youtube_comments(status, created_at);
