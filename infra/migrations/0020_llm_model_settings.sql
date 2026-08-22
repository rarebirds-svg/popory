-- 기능별 LLM 모델 선택. 행이 없는 기능은 코드 기본값(POPORY_CLAUDE_MODEL)을 쓴다.
CREATE TABLE llm_model_settings (
  feature    TEXT PRIMARY KEY,
  model      TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  updated_by TEXT
);
