-- 블로그(네이버·티스토리)·유튜브 커뮤니티 비공개 등록 — 사용자별 발행 설정 + 작업별 발행 상태.
-- 발행은 API 가 아니라 맥미니 워커가 aside 브라우저 스킬로 수행한다(네이버·티스토리는 공식 글쓰기 API 가
-- 없거나 폐쇄적이다). 유튜브 업로드와 같은 requested → publishing → done/failed/skipped 흐름이다.
CREATE TABLE content_publish_settings (
  owner_sub         TEXT PRIMARY KEY REFERENCES users(sub) ON DELETE CASCADE,
  blog_platform     TEXT CHECK (blog_platform IN ('naver','tistory')),
  blog_url          TEXT,
  youtube_community INTEGER NOT NULL DEFAULT 0,
  auto_publish      INTEGER NOT NULL DEFAULT 1,
  updated_at        INTEGER NOT NULL
);
ALTER TABLE content_jobs ADD COLUMN publish_status TEXT;
ALTER TABLE content_jobs ADD COLUMN publish_url TEXT;
ALTER TABLE content_jobs ADD COLUMN publish_error TEXT;
-- 워커 claim 폴링용. 대부분 NULL 이라 부분 인덱스로 D1 row read 를 줄인다.
CREATE INDEX idx_content_jobs_publish ON content_jobs(publish_status, updated_at) WHERE publish_status IS NOT NULL;
