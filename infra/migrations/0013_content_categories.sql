-- content_categories 테이블 + topics·jobs·recommendations 카테고리 분류 컬럼
CREATE TABLE content_categories (
  id            TEXT PRIMARY KEY,
  owner_sub     TEXT NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  slug          TEXT NOT NULL,
  icon          TEXT,
  sort_order    INTEGER NOT NULL DEFAULT 0,
  youtube_channel_id     TEXT,
  youtube_channel_title  TEXT,
  instagram_account_id   TEXT,
  instagram_username     TEXT,
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL
);
CREATE UNIQUE INDEX idx_content_cat_owner_slug ON content_categories(owner_sub, slug);

ALTER TABLE content_topics          ADD COLUMN category_id TEXT REFERENCES content_categories(id);
ALTER TABLE content_jobs            ADD COLUMN category_id TEXT REFERENCES content_categories(id);
ALTER TABLE content_recommendations ADD COLUMN category_id TEXT REFERENCES content_categories(id);
CREATE INDEX idx_content_topics_cat ON content_topics(category_id, created_at DESC);
CREATE INDEX idx_content_jobs_cat   ON content_jobs(category_id, created_at DESC);
CREATE INDEX idx_content_rec_cat    ON content_recommendations(category_id, status);
