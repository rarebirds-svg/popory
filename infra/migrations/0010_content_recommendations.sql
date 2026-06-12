-- 계정별 추천 컨텐츠(주제 후보) 테이블
CREATE TABLE content_recommendations (
  id          TEXT    PRIMARY KEY,
  owner_sub   TEXT    NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  title       TEXT    NOT NULL,
  author      TEXT,
  recommender TEXT    NOT NULL,
  status      TEXT    NOT NULL DEFAULT 'pending',
  note        TEXT,
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL
);
CREATE INDEX idx_content_rec_owner ON content_recommendations(owner_sub, status);
CREATE UNIQUE INDEX idx_content_rec_owner_title ON content_recommendations(owner_sub, title);
