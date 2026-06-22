-- 워커 하트비트 저장 — 콘텐츠 생성 readiness(워커 생존·CF 무료한도·로컬 imagegen) 단일 행.
CREATE TABLE worker_heartbeat (
  id                 TEXT PRIMARY KEY,
  reported_at        INTEGER NOT NULL,
  cf_image_exhausted INTEGER NOT NULL DEFAULT 0,
  cf_reset_date      TEXT,
  imagegen_ok        INTEGER NOT NULL DEFAULT 0
);
