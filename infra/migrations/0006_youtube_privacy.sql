-- content_jobs 에 YouTube 업로드 공개범위(public|unlisted|private) 저장.
ALTER TABLE content_jobs ADD COLUMN youtube_privacy TEXT;
