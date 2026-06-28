-- content_jobs에 자동 업로드 플래그 추가(영상·쇼츠 자동 유튜브 업로드 대상 표시)
ALTER TABLE content_jobs ADD COLUMN auto_upload INTEGER NOT NULL DEFAULT 0;
