-- content_jobs 에 YouTube 업로드 상태 추적 컬럼 추가.
ALTER TABLE content_jobs ADD COLUMN youtube_status TEXT;
ALTER TABLE content_jobs ADD COLUMN youtube_video_id TEXT;
ALTER TABLE content_jobs ADD COLUMN youtube_error TEXT;
