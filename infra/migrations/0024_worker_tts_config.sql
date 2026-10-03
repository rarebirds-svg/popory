-- worker_heartbeat 에 워커가 보고한 TTS 설정 스냅샷(JSON)을 둔다. 어드민 TTS 화면이 읽는다.
-- 맥미니 env 로 덮어쓴 값까지 보여야 해서 코드 상수를 포털에 복제하지 않고 워커가 직접 보고한다.
-- 스냅샷은 프로세스 수명 동안 안 변하므로 하트비트마다 싣지 않는다 → upsert 는 NULL 이면 기존 값을 유지한다.
ALTER TABLE worker_heartbeat ADD COLUMN tts_json TEXT;
-- 스냅샷이 마지막으로 도착한 시각. 하트비트(reported_at)와 별개다 — 워커가 살아 있어도 스냅샷은 오래됐을 수 있다.
ALTER TABLE worker_heartbeat ADD COLUMN tts_reported_at INTEGER;
