-- worker_heartbeat 에 Claude 플랜 사용량(session·weekly) JSON 컬럼을 추가한다.
ALTER TABLE worker_heartbeat ADD COLUMN usage_json TEXT;
