-- content_topics 신규 테이블 + content_jobs idle 상태·topic_id 추가

CREATE TABLE content_topics (
  id         TEXT    PRIMARY KEY,
  owner_sub  TEXT    NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  topic      TEXT    NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_content_topics_owner ON content_topics(owner_sub, created_at DESC);

-- content_jobs 재생성: status CHECK에 idle 추가, topic_id 컬럼 추가
-- SQLite는 CHECK 제약 ALTER를 지원하지 않으므로 테이블 재생성 필요
-- D1은 FK 기본 비활성화(SQLite default)라 DROP TABLE이 자식 테이블에 영향 없음

CREATE TABLE content_jobs_new (
  id               TEXT    PRIMARY KEY,
  owner_sub        TEXT    NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  topic            TEXT    NOT NULL,
  platform         TEXT    NOT NULL DEFAULT 'naver-blog',
  status           TEXT    NOT NULL CHECK (status IN ('idle','queued','running','review','done','failed')),
  style_profile_id TEXT,
  params_json      TEXT,
  draft_r2_key     TEXT,
  meta_json        TEXT,
  error            TEXT,
  created_at       INTEGER NOT NULL,
  updated_at       INTEGER NOT NULL,
  youtube_status   TEXT,
  youtube_video_id TEXT,
  youtube_error    TEXT,
  youtube_privacy  TEXT,
  topic_id         TEXT    REFERENCES content_topics(id)
);

INSERT INTO content_jobs_new
  SELECT id, owner_sub, topic, platform, status, style_profile_id, params_json,
         draft_r2_key, meta_json, error, created_at, updated_at,
         youtube_status, youtube_video_id, youtube_error, youtube_privacy, NULL
  FROM content_jobs;

DROP TABLE content_jobs;
ALTER TABLE content_jobs_new RENAME TO content_jobs;

CREATE INDEX idx_content_jobs_status ON content_jobs(status, created_at);
CREATE INDEX idx_content_jobs_owner  ON content_jobs(owner_sub, created_at DESC);
CREATE INDEX idx_content_jobs_topic  ON content_jobs(topic_id);
