-- popory 컨텐츠 관리 Slice 1 — content_jobs·content_sources·style_profiles 테이블

CREATE TABLE content_jobs (
  id               TEXT PRIMARY KEY,
  owner_sub        TEXT NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  topic            TEXT NOT NULL,
  platform         TEXT NOT NULL DEFAULT 'naver-blog',
  status           TEXT NOT NULL CHECK (status IN ('queued','running','review','done','failed')),
  style_profile_id TEXT,
  params_json      TEXT,
  draft_r2_key     TEXT,
  meta_json        TEXT,
  error            TEXT,
  created_at       INTEGER NOT NULL,
  updated_at       INTEGER NOT NULL
);
CREATE INDEX idx_content_jobs_status ON content_jobs(status, created_at);
CREATE INDEX idx_content_jobs_owner ON content_jobs(owner_sub, created_at DESC);

CREATE TABLE content_sources (
  id         TEXT PRIMARY KEY,
  job_id     TEXT NOT NULL REFERENCES content_jobs(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL CHECK (kind IN ('auto','manual')),
  url        TEXT,
  title      TEXT,
  note       TEXT,
  added_by   TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_content_sources_job ON content_sources(job_id);

CREATE TABLE style_profiles (
  id           TEXT PRIMARY KEY,
  owner_sub    TEXT NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  platform     TEXT NOT NULL DEFAULT 'naver-blog',
  guide_r2_key TEXT,
  sample_count INTEGER NOT NULL DEFAULT 0,
  created_at   INTEGER NOT NULL
);
CREATE INDEX idx_style_profiles_owner ON style_profiles(owner_sub);
