-- 카테고리별 유튜브 refresh_token(암호화) 저장 테이블
CREATE TABLE category_youtube_tokens (
  category_id   TEXT PRIMARY KEY REFERENCES content_categories(id) ON DELETE CASCADE,
  refresh_token TEXT NOT NULL,
  connected_at  INTEGER NOT NULL
);
