-- 로컬 파이썬 잡(content·brief)의 실패 로그를 admin 화면에서 조회하기 위한 적재 테이블.
CREATE TABLE job_logs (
  id         TEXT PRIMARY KEY,
  service    TEXT NOT NULL,
  cli        TEXT NOT NULL,
  status     TEXT NOT NULL,
  job_id     TEXT,
  owner_sub  TEXT,
  detail     TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_job_logs_created ON job_logs(created_at DESC);
