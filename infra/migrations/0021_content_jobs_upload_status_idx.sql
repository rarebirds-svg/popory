-- 업로드 claim 폴링(워커 20초 주기)이 content_jobs 를 풀스캔해 D1 무료 티어
-- 일일 row read 한도를 소진한 사고(2026-09-01)의 재발 방지 인덱스.
-- (youtube|instagram)_status 필터 + updated_at 정렬(claim)·범위(리스 회수)를
-- 한 인덱스로 커버한다. 대부분 행은 상태가 NULL(업로드 무관)이라 partial 로
-- 작게 유지한다 — '=' 조건은 IS NOT NULL 을 함의하므로 기존 쿼리 그대로 탄다.
CREATE INDEX idx_content_jobs_youtube ON content_jobs(youtube_status, updated_at)
  WHERE youtube_status IS NOT NULL;
CREATE INDEX idx_content_jobs_instagram ON content_jobs(instagram_status, updated_at)
  WHERE instagram_status IS NOT NULL;
